"""SYN-P1 synthetic qualification case: plant an EZ + small PZ on Wang P1 SC/gain, simulate raw-like SEEG.

Forward model (generator) = 6D Epileptor network (Jirsa et al. 2014; TVB `Epileptor` equations, slow
permittivity coupling on z as in the VEP papers), stochastic Heun, dt = 0.05 ms, 100 Hz temporal-average
monitor (P1 rate, read from the P1 file time_steps), source signal x2 - x1 projected through P1's
gain, plus coloured (AR(1)) + white sensor noise. NB the inversion uses the 2D Epileptor, so the benchmark
includes generator/inverter model mismatch on purpose.

Writes:
  syn_p1_truth.json   planted generating parameter map (stays LOCAL; never pushed)
  syn_p1_seeg.npz     seeg [ns x nt], time_steps (ms), ch_names  (synthetic data, no truth)
Usage: python sim_syn_p1.py [--seed 20261101] [--probe]
"""
import argparse, hashlib, json, sys, time
from pathlib import Path
import numpy as np
import numba

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(__file__).resolve().parent
P1 = ROOT / "data/wang-5367ef4/data/dataSim/Patient1/P1_SEEG_SEEG_fit.npz"
WELL_SAMPLED = [58, 141, 67, 44, 56, 59]   # A0007 coverage table: >=3 contacts > 25% global max gain

# Epileptor constants (TVB defaults)
IEXT1, IEXT2, TAU2, R, SLOPE = 3.1, 0.45, 10.0, 0.00004, 0.0   # r lowered from TVB 0.00035 so a seizure lasts ~7 s at ms time units
X0_EZ, X0_PZ, Z0_EZ, X0_BURN, BURN_MS = -1.8, -2.25, 4.2, -2.3, 5000.0


@numba.njit(cache=True)
def dfun(x1, y1, z, x2, y2, g, x0, K, SC, SCrow, out):
    n = x1.shape[0]
    cx = SC @ x1 - SCrow * x1          # diffusive coupling sum_j SC_ij (x1_j - x1_i)
    for i in range(n):
        if x1[i] < 0.0:
            f1 = x1[i] ** 3 - 3.0 * x1[i] ** 2
        else:
            f1 = (SLOPE - x2[i] + 0.6 * (z[i] - 4.0) ** 2) * x1[i]
        out[0, i] = y1[i] - f1 - z[i] + IEXT1
        out[1, i] = 1.0 - 5.0 * x1[i] ** 2 - y1[i]
        out[2, i] = R * (4.0 * (x1[i] - x0[i]) - z[i] - K * cx[i])
        f2 = 0.0 if x2[i] < -0.25 else 6.0 * (x2[i] + 0.25)
        out[3, i] = -y2[i] + x2[i] - x2[i] ** 3 + IEXT2 + 2.0 * g[i] - 0.3 * (z[i] - 3.5)
        out[4, i] = (-y2[i] + f2) / TAU2
        out[5, i] = -0.01 * (g[i] - 0.1 * x1[i])


@numba.njit(cache=True)
def simulate(state0, x0, K, SC, dt, n_steps, avg, nsig, seed):
    np.random.seed(seed)
    n = x0.shape[0]
    S = state0.copy()
    SCrow = SC.sum(axis=1)
    k1 = np.empty((6, n)); k2 = np.empty((6, n)); Sp = np.empty((6, n))
    n_out = n_steps // avg
    out = np.zeros((n_out, n)); zout = np.zeros((n_out, n))
    acc = np.zeros(n); accz = np.zeros(n)
    sq = np.sqrt(2.0 * nsig * dt)       # TVB convention: noise amplitude sqrt(2 D dt)
    for t in range(n_steps):
        dfun(S[0], S[1], S[2], S[3], S[4], S[5], x0, K, SC, SCrow, k1)
        noise = np.empty((6, n))
        for v in range(6):
            for i in range(n):
                noise[v, i] = sq[v] * np.random.randn()
        for v in range(6):
            for i in range(n):
                Sp[v, i] = S[v, i] + dt * k1[v, i] + noise[v, i]
        dfun(Sp[0], Sp[1], Sp[2], Sp[3], Sp[4], Sp[5], x0, K, SC, SCrow, k2)
        for v in range(6):
            for i in range(n):
                S[v, i] = S[v, i] + 0.5 * dt * (k1[v, i] + k2[v, i]) + noise[v, i]
        for i in range(n):
            acc[i] += S[3, i] - S[0, i]          # lfp = x2 - x1 (TVB Epileptor lfp)
            accz[i] += S[2, i]
        if (t + 1) % avg == 0:
            k = (t + 1) // avg - 1
            out[k] = acc / avg; zout[k] = accz / avg
            acc[:] = 0.0; accz[:] = 0.0
    return out, zout


def plant(seed):
    d = np.load(P1)
    SC, gain = d["SC"], d["gain"]
    rng = np.random.default_rng(seed)
    nn = SC.shape[0]
    ez = int(rng.choice(WELL_SAMPLED))
    nb = [int(j) for j in np.argsort(SC[ez])[::-1] if j != ez]
    pz = nb[:2]                                  # small PZ: the 2 strongest SC neighbours of the EZ
    x0 = np.round(rng.uniform(-2.60, -2.40, nn), 4)   # healthy background
    x0[ez] = X0_EZ
    for j in pz:
        x0[j] = X0_PZ
    return SC, gain, d, ez, pz, x0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--K", type=float, default=3.0)
    ap.add_argument("--T", type=float, default=21000.0)   # ms
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    SC, gain, d, ez, pz, x0 = plant(a.seed)
    nn = SC.shape[0]
    step_ms = float(np.diff(d["time_steps"]).mean())      # 10 ms -> 100 Hz (read from the P1 file)
    fs = 1000.0 / step_ms
    dt = 0.05
    avg = int(round(step_ms / dt))
    n_steps = int(a.T / dt)
    # burn-in (5 s, EZ/PZ held at x0=-2.3) from a generic state, then EZ slow variable set to z=4.2 (post-ictal
    # level) so that the seizure starts after a preictal baseline of ~8 s
    state0 = np.zeros((6, nn))
    state0[0] = -1.8; state0[1] = -15.0; state0[2] = 3.6; state0[3] = -0.9; state0[4] = 0.0; state0[5] = -0.18
    nsig = np.array([0.0, 0.0, 0.0, 2.5e-4, 2.5e-4, 0.0])   # background noise on the 2nd population
    xb = x0.copy(); xb[[ez] + pz] = X0_BURN
    t0 = time.time()
    _, zb = simulate(state0, xb, a.K, SC, dt, int(BURN_MS / dt), avg, nsig, a.seed)
    state1 = state0.copy(); state1[2] = zb[-1]; state1[2, ez] = Z0_EZ
    src, zsrc = simulate(state1, x0, a.K, SC, dt, n_steps, avg, nsig, a.seed + 2)
    el = time.time() - t0
    from scipy.signal import butter, filtfilt
    b, aa = butter(3, 2 * 10 / fs, "highpass")
    hp = filtfilt(b, aa, src, axis=0)
    pw = np.array([np.convolve(hp[:, i] ** 2, np.ones(int(fs)) / fs, "same") for i in range(nn)]).T
    base = np.median(pw[: int(3 * fs)])
    ratio = pw.max(0) / base
    onset = {}
    for i in np.argsort(ratio)[::-1][:8]:
        above = np.where(pw[:, i] > 30 * base)[0]
        onset[int(i)] = (round(float(10 * np.log10(ratio[i])), 1), float(above[0] / fs) if len(above) else None)
    print(f"sim {el:.1f}s  EZ {ez} PZ {pz}  top regions by source HP-power (max dB vs baseline, first time >30x baseline s): {onset}")
    if a.probe:
        return
    rng = np.random.default_rng(a.seed + 1)
    seeg_clean = (gain @ src.T)                    # [ns x nt]
    base_sd = np.median(seeg_clean[:, : int(3 * fs)].std(1))
    nt = seeg_clean.shape[1]
    # sensor noise: AR(1) coloured (phi 0.9) + white, scaled to the median channel baseline SD
    phi = 0.9
    e = rng.standard_normal((gain.shape[0], nt))
    col = np.zeros_like(e)
    for t in range(1, nt):
        col[:, t] = phi * col[:, t - 1] + np.sqrt(1 - phi ** 2) * e[:, t]
    noise = 1.0 * base_sd * col + 0.5 * base_sd * rng.standard_normal(e.shape)
    seeg = seeg_clean + noise
    time_steps = step_ms * np.arange(1, nt + 1) - step_ms / 2
    np.savez(WORK / "syn_p1_seeg.npz", seeg=seeg, time_steps=time_steps, ch_names=d["ch_names"])
    names = json.load(open(ROOT / "studies/study-002/artifacts/A0007-PatientCase/payload.json"))["anatomy"]["region_names"]
    truth = {
        "case": "SYN-P1 (synthetic, derived from Wang P1 SC + gain)", "seed": a.seed, "noise_seed": a.seed + 1,
        "ez": [ez], "ez_names": [names[ez]], "pz": pz, "pz_names": [names[j] for j in pz],
        "x0": x0.tolist(), "x0_ez": X0_EZ, "x0_pz": X0_PZ, "x0_healthy": "U(-2.60,-2.40) per region (rng seed)",
        "init": f"burn-in {BURN_MS} ms with EZ/PZ x0={X0_BURN} (noise seed {a.seed}), then z_EZ={Z0_EZ}; main run noise seed {a.seed + 2}",
        "generator": "6D Epileptor network, Heun stochastic dt=0.05, slow diffusive coupling on z, K=%g" % a.K,
        "K": a.K, "Iext1": IEXT1, "Iext2": IEXT2, "tau2": TAU2, "r": R, "dt": dt, "T_ms": a.T,
        "state0_burnin": "x1=-1.8,y1=-15,z=3.6,x2=-0.9,y2=0,g=-0.18 all nodes", "source_noise_D": nsig.tolist(),
        "monitor": f"temporal average over {avg} steps -> {fs:g} Hz; lfp = x2 - x1",
        "sensor": "seeg = gain @ lfp + 1.0*base_sd*AR1(phi=0.9) + 0.5*base_sd*white; base_sd=%.6g" % base_sd,
        "seizure_power_ratio_top8": onset, "sim_seconds": el,
        "seeg_sha256": hashlib.sha256(seeg.tobytes()).hexdigest(),
    }
    json.dump(truth, open(WORK / "syn_p1_truth.json", "w"), indent=1)
    print(json.dumps({k: truth[k] for k in ("ez", "ez_names", "pz", "pz_names", "seeg_sha256")}))


if __name__ == "__main__":
    main()
