"""Score a pulled arm result against the planted truth (LOCAL only; truth never leaves this machine).
Usage: python analyze.py results/<arm_dir> <arm_label>  -> results/<arm_dir>/score.json
Needs in <arm_dir>: x0_draws.npy, seizing_draws.npy, summary.csv, diag.json, optima.json
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

WORK = Path(__file__).resolve().parent
X0_CRIT = -2.06   # 2D Epileptor bifurcation (isolated node): x0 above this has no resting fixed point


def main(d, label):
    d = Path(d)
    truth = json.load(open(WORK / "syn_p1_truth.json"))
    ez, pz = truth["ez"], truth["pz"]
    x0 = np.load(d / "x0_draws.npy")                     # [draws, nn]
    seiz = np.load(d / "seizing_draws.npy")
    summ = pd.read_csv(d / "summary.csv", index_col=0)
    diag = json.load(open(d / "diag.json"))
    opt = json.load(open(d / "optima.json"))
    nn = x0.shape[1]
    mean = x0.mean(0)
    order = np.argsort(mean)[::-1]
    rank = {int(r): int(np.where(order == r)[0][0]) + 1 for r in range(nn)}
    draw_top = x0.argmax(1)
    p_rank1 = {int(r): float((draw_top == r).mean()) for r in set(ez + pz) | set(order[:5].tolist())}
    p_exc = (x0 > X0_CRIT).mean(0)
    p_seiz = seiz.mean(0)
    est_ez = [int(i) for i in np.where(p_exc > 0.5)[0]]
    fp_exc = [i for i in est_ez if i not in ez + pz]
    fp_exc_strict = [i for i in est_ez if i not in ez]
    rows = [f"x0[{i + 1}]" for i in range(nn)]
    rhat_col = "R_hat" if "R_hat" in summ.columns else [c for c in summ.columns if "hat" in c.lower()][0]
    ess_b = [c for c in summ.columns if "ESS_bulk" in c or c == "N_Eff"][0]
    ess_t = [c for c in summ.columns if "ESS_tail" in c]
    rh = summ.loc[rows, rhat_col].astype(float)
    globals_ = {k: summ.loc[k, ["Mean", "5%", "95%", rhat_col, ess_b]].astype(float).round(4).tolist()
                for k in ("K", "tau0", "amp", "sigma", "phi", "resid_lag1_ac") if k in summ.index}
    names = json.load(open(WORK.parents[1] / "artifacts/A0007-PatientCase/payload.json"))["anatomy"]["region_names"]
    top10 = [{"region": int(r), "name": names[r], "rank": i + 1, "x0_mean": round(float(mean[r]), 3),
              "x0_q05_q95": [round(float(np.quantile(x0[:, r], q)), 3) for q in (0.05, 0.95)],
              "P_x0_gt_crit": round(float(p_exc[r]), 3), "P_seizing": round(float(p_seiz[r]), 3),
              "rhat": round(float(rh.iloc[r]), 4), "truth": "EZ" if r in ez else ("PZ" if r in pz else "healthy")}
             for i, r in enumerate(order[:10])]
    out = {
        "arm": label, "n_draws": int(x0.shape[0]),
        "planted_ez": ez, "planted_pz": pz,
        "ez_rank_by_posterior_mean_x0": {int(r): rank[r] for r in ez},
        "pz_ranks": {int(r): rank[r] for r in pz},
        "P_rank1": p_rank1,
        "max_x0_rhat": float(rh.max()), "n_x0_rhat_ge_1.05": int((rh >= 1.05).sum()),
        "min_x0_ess_bulk": float(summ.loc[rows, ess_b].min()),
        "min_x0_ess_tail": float(summ.loc[rows, ess_t[0]].min()) if ess_t else None,
        "max_rhat_all_params": float(summ[rhat_col].replace([np.inf], np.nan).max()),
        "divergences_per_chain": diag["divergent_per_chain"], "divergences_total": int(sum(diag["divergent_per_chain"])),
        "treedepth_max": diag["treedepth_max"], "treedepth_hits_per_chain": diag["treedepth_hits_max_per_chain"],
        "n_leapfrog_mean": diag["n_leapfrog_mean"], "stepsize_per_chain": diag["stepsize_per_chain"],
        "estimated_ez_set_P(x0>-2.06)>0.5": est_ez,
        "false_positives_excluding_ez_and_pz": fp_exc, "false_positives_excluding_ez_only": fp_exc_strict,
        "regions_P_seizing_gt_0.5": [int(i) for i in np.where(p_seiz > 0.5)[0]],
        "globals_mean_q05_q95_rhat_ess": globals_, "top10": top10,
        "optim": {"t_opt_s": opt["t_opt_s"], "n_runs": len(opt["opts"]),
                  "lp": [round(o["lp"], 1) for o in opt["opts"]],
                  "top_region_per_run": [int(np.argmax(o["x0"])) if "x0" in o else None for o in opt["opts"]],
                  "ez_rank_per_run": [int(np.where(np.argsort(o["x0"])[::-1] == ez[0])[0][0]) + 1 if "x0" in o else None
                                      for o in opt["opts"]]},
        "t_opt_s": diag["t_opt_s"], "t_nuts_s": diag["t_nuts_s"],
    }
    out["pass_arm_criteria"] = {"ez_rank1": out["ez_rank_by_posterior_mean_x0"][ez[0]] == 1,
                                "all_x0_rhat_lt_1.05": out["max_x0_rhat"] < 1.05,
                                "no_divergences": out["divergences_total"] == 0}
    json.dump(out, open(d / "score.json", "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("arm", "ez_rank_by_posterior_mean_x0", "pz_ranks", "P_rank1", "max_x0_rhat",
                                          "min_x0_ess_bulk", "divergences_total", "treedepth_max",
                                          "false_positives_excluding_ez_and_pz", "pass_arm_criteria", "t_nuts_s")}, indent=1))
    for t in top10[:6]:
        print(t)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
