"""Build Stan data for SYN-P1 arms from the synthetic SEEG (raw-like) via features.compute_feature.

Arm A: P1 SC (generating connectome). Arm B: P2 SC (mismatched connectome; only the 'SC' key of
P2_SEEG_ts_fit.npz is read). Gain is P1's in both arms (same implant). Priors are data-centred and use only
the synthetic signal, the gain and fixed constants - never the planted truth.
Usage: python prep_data.py   -> data_A.json, data_B.json, prior_settings.json
"""
import json
from pathlib import Path
import numpy as np
import features as F

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(__file__).resolve().parent
P1 = ROOT / "data/wang-5367ef4/data/dataSim/Patient1/P1_SEEG_SEEG_fit.npz"
P2 = ROOT / "data/wang-5367ef4/data/dataSim/Patient2/P2_SEEG_ts_fit.npz"
NB_S = 5.0       # baseline = first 5 s of features
DX_SEIZURE = 2.4  # 2D Epileptor x excursion resting branch (~-1.9) -> seizure branch (~+0.5)


def build(target_hz=2.0, ar1=1):
    d = np.load(WORK / "syn_p1_seeg.npz")
    y, t, fs = F.compute_feature(d["seeg"], d["time_steps"], target_hz=target_hz)
    gain = np.load(P1)["gain"]
    sc_a = np.load(P1)["SC"]
    with np.load(P2) as z2:
        sc_b = z2["SC"]                                   # only the SC matrix of P2 is read
    NB = int(round(NB_S * target_hz))
    base = np.median(y[:NB], 0)
    rng_ch = (y - base).max(0)
    logamp_mu = float(np.log(np.quantile(rng_ch, 0.99) / (DX_SEIZURE * gain.max())))
    logsig_mu = float(np.log(np.median(y[:NB].std(0))))
    common = dict(nn=162, nt=int(y.shape[0]), ns=int(y.shape[1]), Obs=y.tolist(), gain=gain.tolist(),
                  dt=0.1, nsub=int(round(4.0 / target_hz)), I1=3.1, x0_mu=-2.5, x0_sd=0.5,
                  x0_cap=-2.12, cap_k=20.0, z0_sd=0.2,
                  logK_mu=0.0, logK_sd=1.0, logtau_mu=float(np.log(10.0)), logtau_sd=0.6,
                  logamp_mu=logamp_mu, logamp_sd=1.0, u_mu=base.tolist(), u_sd=0.5,
                  logsig_mu=logsig_mu, logsig_sd=1.0, ar1=ar1)
    info = dict(fs_from_time_steps=fs, target_hz=target_hz, nt=int(y.shape[0]), ns=int(y.shape[1]),
                t_first_last_s=[float(t[0]), float(t[-1])], baseline_samples=NB,
                logamp_mu=logamp_mu, amp_prior_median=float(np.exp(logamp_mu)), logsig_mu=logsig_mu,
                sigma_prior_median=float(np.exp(logsig_mu)), q99_channel_range=float(np.quantile(rng_ch, 0.99)),
                feature_lag1_ac_baseline_median=float(np.median(
                    ((y[1:NB] - y[:NB].mean(0)) * (y[:NB - 1] - y[:NB].mean(0))).sum(0) /
                    ((y[:NB] - y[:NB].mean(0)) ** 2).sum(0))))
    return common, sc_a, sc_b, info


if __name__ == "__main__":
    common, sc_a, sc_b, info = build()
    for arm, sc in (("A", sc_a), ("B", sc_b)):
        json.dump({**common, "SC": sc.tolist()}, open(WORK / f"data_{arm}.json", "w"))
    json.dump(info, open(WORK / "prior_settings.json", "w"), indent=1)
    print(json.dumps(info, indent=1))
