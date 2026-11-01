"""T0011 remote runner (fit_config run2: distinct-optima + jitter inits) (GCP VM, pinned env). Stages:
  python run_fit.py compile
  python run_fit.py lpcheck <data.json>                       # numpy vs Stan log density
  python run_fit.py fit <arm> <data.json> --nopt 16 --chains 8 --warmup 1000 --samples 1000 --seed S [--tag t]
fit = multi-start L-BFGS (nopt runs, Stan default random inits, seeds S+i) -> NUTS chains initialised at the
top-`chains` optima by log density (one optimum per chain) -> outputs in out_<arm><tag>/.
"""
import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import cmdstanpy

HERE = Path(__file__).resolve().parent
STAN = HERE / "vep_ar1.stan"


def compile_model():
    t = time.time()
    # NB: no stanc --O1: the O1-optimised build returned log densities that disagree with both the
    # unoptimised build and the numpy re-implementation (T0011 lp check), so O0 (default) is used.
    m = cmdstanpy.CmdStanModel(stan_file=str(STAN), force_compile=True)
    print(json.dumps({"exe": m.exe_file, "compile_s": time.time() - t, "cmdstan": cmdstanpy.utils.cmdstan_version(),
                      "cmdstanpy": cmdstanpy.__version__}))
    return m


def fit(a):
    m = cmdstanpy.CmdStanModel(stan_file=str(STAN))
    out = HERE / f"out_{a.arm}{a.tag}"
    out.mkdir(exist_ok=True)
    d = json.load(open(a.data))
    t0 = time.time()

    def opt(i):
        s = a.seed + i
        try:
            r = m.optimize(data=a.data, seed=s, algorithm="lbfgs", iter=20000, tol_param=1e-10,
                           output_dir=str(out / f"opt_{i:02d}"), show_console=False, require_converged=False)
            v = r.optimized_params_dict
            return {"run": i, "seed": s, "lp": float(v["lp__"]), "converged": bool(r.converged),
                    "params": {k: (r.stan_variable(k).tolist() if np.ndim(r.stan_variable(k)) else float(r.stan_variable(k)))
                               for k in ("x0_star", "z_init_star", "logK_star", "logtau_star", "logamp_star",
                                         "u_star", "logsig_star", "phi_raw")},
                    "x0": r.stan_variable("x0").tolist(), "K": float(v["K"]), "tau0": float(v["tau0"]),
                    "amp": float(v["amp"]), "sigma": float(v["sigma"]), "phi": float(v["phi"])}
        except Exception as e:  # noqa
            return {"run": i, "seed": s, "lp": -np.inf, "error": str(e)[:300]}

    with ThreadPoolExecutor(a.nopt) as ex:
        opts = list(ex.map(opt, range(a.nopt)))
    t_opt = time.time() - t0
    opts.sort(key=lambda o: -o["lp"])
    json.dump({"t_opt_s": t_opt, "opts": [{k: v for k, v in o.items() if k != "params"} for o in opts]},
              open(out / "optima.json", "w"))
    good = [o for o in opts if np.isfinite(o["lp"])]
    # run2 (LEAD decision 14:3x UTC): chains spread across DISTINCT optima (lp differing by > 0.5), top first,
    # cycling if fewer distinct optima than chains, plus N(0, jitter) on every unconstrained parameter
    distinct = []
    for o in good:
        if all(abs(o["lp"] - q["lp"]) > 0.5 for q in distinct):
            distinct.append(o)
    rng = np.random.default_rng(a.seed)
    inits, init_src = [], []
    for c in range(a.chains):
        src = distinct[c % len(distinct)]
        p = {}
        for k, v in src["params"].items():
            v = np.asarray(v, float) + rng.normal(0, a.jitter, np.shape(v))
            if k == "phi_raw":
                v = np.clip(v, -0.99, 0.99)
            p[k] = v.tolist() if np.ndim(v) else float(v)
        inits.append(p); init_src.append({"chain": c + 1, "opt_run": src["run"], "opt_lp": src["lp"]})
    json.dump({"n_distinct_optima": len(distinct), "jitter_sd": a.jitter, "init_sources": init_src},
              open(out / "inits_used.json", "w"), indent=1)
    print(f"optim done {t_opt:.0f}s; top lp {[round(o['lp'], 1) for o in good[:a.chains]]}", flush=True)
    for o in good[:8]:
        print(o["run"], round(o["lp"], 1), "K %.2f tau %.2f amp %.3f phi %.2f" % (o["K"], o["tau0"], o["amp"], o["phi"]),
              "top x0:", [(int(i), round(o["x0"][i], 2)) for i in np.argsort(o["x0"])[::-1][:5]], flush=True)
    if a.opt_only:
        return
    t1 = time.time()
    fitn = m.sample(data=a.data, chains=a.chains, parallel_chains=a.chains, seed=a.seed, inits=inits,
                    iter_warmup=a.warmup, iter_sampling=a.samples, adapt_delta=a.adapt_delta,
                    max_treedepth=a.max_depth, output_dir=str(out / "nuts"), show_progress=False,
                    show_console=True, refresh=50)
    t_nuts = time.time() - t1
    x0 = fitn.stan_variable("x0")                       # [draws x nn]
    np.save(out / "x0_draws.npy", x0)
    seiz = fitn.stan_variable("seizing")
    np.save(out / "seizing_draws.npy", seiz)
    sc = fitn.method_variables()
    summ = fitn.summary(percentiles=(5, 50, 95))
    summ.to_csv(out / "summary.csv")
    diag = {"divergent_per_chain": np.asarray(sc["divergent__"]).sum(0).tolist(),
            "treedepth_max": int(np.asarray(sc["treedepth__"]).max()),
            "treedepth_hits_max_per_chain": (np.asarray(sc["treedepth__"]) >= a.max_depth).sum(0).tolist(),
            "stepsize_per_chain": np.asarray(sc["stepsize__"])[0].tolist(),
            "n_leapfrog_mean": float(np.asarray(sc["n_leapfrog__"]).mean()),
            "diagnose": fitn.diagnose()[-3000:], "t_opt_s": t_opt, "t_nuts_s": t_nuts,
            "settings": vars(a)}
    json.dump(diag, open(out / "diag.json", "w"), indent=1, default=str)
    print(f"nuts done {t_nuts:.0f}s; divergences {diag['divergent_per_chain']}; max treedepth {diag['treedepth_max']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("arm", nargs="?")
    ap.add_argument("data", nargs="?")
    ap.add_argument("--nopt", type=int, default=16)
    ap.add_argument("--chains", type=int, default=8)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--samples", type=int, default=1000)
    ap.add_argument("--adapt_delta", type=float, default=0.95)
    ap.add_argument("--max_depth", type=int, default=10)
    ap.add_argument("--seed", type=int, default=11011)
    ap.add_argument("--tag", default="")
    ap.add_argument("--opt_only", action="store_true")
    ap.add_argument("--jitter", type=float, default=0.05)
    a = ap.parse_args()
    if a.stage == "compile":
        compile_model()
    elif a.stage == "lpcheck":
        m = compile_model()
        os.system(f"{sys.executable} lp_numpy.py {m.exe_file} {a.arm}")
    elif a.stage == "fit":
        fit(a)
