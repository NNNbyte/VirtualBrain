"""Independent numpy re-implementation of the vep_ar1.stan log density (with the Jacobian of the phi_raw
bound transform), checked against CmdStan's log_prob at random parameter points.

Written from the model equations (2D Epileptor, explicit Euler, diffusive coupling; AR(1) Gaussian residuals;
standard-normal non-centred priors) without calling Stan code.
Usage: python lp_numpy.py <compiled-exe-dir-or-stanfile> data_A.json  -> lp_check.json
"""
import json, sys
from pathlib import Path
import numpy as np


def norm_lpdf(x, mu, sd):
    x = np.asarray(x, float)
    return float(np.sum(-0.5 * ((x - mu) / sd) ** 2 - np.log(sd) - 0.5 * np.log(2 * np.pi)))


def x_rest(z, I1):
    zk = I1 + 1.0 - 32.0 / 27.0
    x = np.empty_like(z)
    for i, zi in enumerate(z):
        if zi <= zk + 1e-3:
            x[i] = -4.0 / 3.0
        else:
            # independent root finder (not Newton): numpy polynomial roots, pick the real root < -4/3
            r = np.roots([1.0, 2.0, 0.0, zi - (I1 + 1.0)])
            r = r[np.abs(r.imag) < 1e-9].real
            x[i] = r[r < -4.0 / 3.0].max()
    return x


def z_eq(x0s, I1):
    # independent: real root of the monotone cubic via numpy.roots
    out = np.empty_like(x0s)
    for i, a in enumerate(x0s):
        r = np.roots([1.0, 2.0, 4.0, -4.0 * a - (I1 + 1.0)])
        xr = r[np.abs(r.imag) < 1e-9].real[0]
        out[i] = 4.0 * (xr - a)
    return out


def softmin(x, cap, k):
    return -np.logaddexp(-k * x, -k * cap) / k


def simulate(x0, z_init, K, tau0, SC, dt, nsub, nt, I1):
    SCrow = SC.sum(1)
    x = x_rest(z_init, I1); z = z_init.copy()
    X = np.empty((len(x0), nt)); X[:, 0] = x
    for t in range(1, nt):
        for _ in range(nsub):
            gx = SC @ x - SCrow * x
            dx = 1.0 - x ** 3 - 2.0 * x ** 2 - z + I1
            dz = (4.0 * (x - x0) - z - K * gx) / tau0
            x = x + dt * dx; z = z + dt * dz
        X[:, t] = x
    return X


def log_density(p, d):
    """p: dict of constrained parameter values (stars, phi_raw). Returns lp incl. Jacobian of phi_raw."""
    Obs = np.array(d["Obs"]); SC = np.array(d["SC"]); G = np.array(d["gain"])
    nt = d["nt"]
    x0 = d["x0_mu"] + d["x0_sd"] * np.asarray(p["x0_star"])
    zi = z_eq(softmin(x0, d["x0_cap"], d["cap_k"]), d["I1"]) + d["z0_sd"] * np.asarray(p["z_init_star"])
    K = np.exp(d["logK_mu"] + d["logK_sd"] * p["logK_star"])
    tau0 = np.exp(d["logtau_mu"] + d["logtau_sd"] * p["logtau_star"])
    amp = np.exp(d["logamp_mu"] + d["logamp_sd"] * p["logamp_star"])
    u = np.asarray(d["u_mu"]) + d["u_sd"] * np.asarray(p["u_star"])
    sig = np.exp(d["logsig_mu"] + d["logsig_sd"] * p["logsig_star"])
    phi = p["phi_raw"] if d["ar1"] == 1 else 0.0
    X = simulate(x0, zi, K, tau0, SC, d["dt"], d["nsub"], nt, d["I1"])
    mu = (amp * (G @ (X - X[:, [0]]))).T + u[None, :]
    r = Obs - mu
    lp = 0.0
    for k in ("x0_star", "z_init_star", "logK_star", "logtau_star", "logamp_star", "u_star", "logsig_star"):
        lp += norm_lpdf(p[k], 0, 1)
    lp += norm_lpdf(r[0], 0, sig / np.sqrt(1 - phi ** 2))
    lp += norm_lpdf(r[1:], phi * r[:-1], sig)
    pr = p["phi_raw"]
    lp += np.log((pr + 1) * (1 - pr) / 2.0)     # Jacobian of phi_raw = -1 + 2 inv_logit(v)
    return lp


if __name__ == "__main__":
    import cmdstanpy
    exe, data_file = sys.argv[1], sys.argv[2]
    d = json.load(open(data_file))
    model = cmdstanpy.CmdStanModel(exe_file=exe)
    rng = np.random.default_rng(7)
    out = []
    for k in range(6):
        p = {"x0_star": rng.normal(0, 1, d["nn"]).tolist(), "z_init_star": rng.normal(0, 1, d["nn"]).tolist(),
             "logK_star": float(rng.normal()), "logtau_star": float(rng.normal()), "logamp_star": float(rng.normal()),
             "u_star": rng.normal(0, 1, d["ns"]).tolist(), "logsig_star": float(rng.normal()),
             "phi_raw": float(rng.uniform(-0.95, 0.95))}
        if k == 0:   # include a strongly seizing point
            p["x0_star"] = (np.array(p["x0_star"]) + 1.5).tolist()
        lp_np = log_density(p, d)
        res = model.log_prob(params=p, data=data_file, jacobian=True)
        lp_stan = float(res["lp__"].iloc[0])
        out.append({"point": k, "lp_numpy": lp_np, "lp_stan": lp_stan, "abs_diff": abs(lp_np - lp_stan),
                    "rel_diff": abs(lp_np - lp_stan) / abs(lp_stan)})
        print(out[-1])
    json.dump({"data": data_file, "points": out, "max_abs_diff": max(o["abs_diff"] for o in out)},
              open(Path(data_file).with_name(Path(data_file).stem + "_lp_check.json"), "w"), indent=1)
