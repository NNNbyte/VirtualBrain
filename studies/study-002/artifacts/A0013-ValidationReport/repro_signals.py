"""R5 T0008: follow-up signal checks (tails, spectra, P2 epoch boundaries, MAD jump counts)."""
import json, sys
import numpy as np
from scipy import signal

ROOT = "data/wang-5367ef4/data/dataSim/"
res = {}


def load(f):
    d = np.load(ROOT + f, allow_pickle=False)
    return d["seeg"], d["time_steps"], [str(x) for x in d["ch_names"]]


def peak(x, fs, lo=1.0):
    x = x - x.mean(1, keepdims=True)
    f, p = signal.welch(x, fs=fs, nperseg=min(256, x.shape[1]), axis=1)
    pm = p.mean(0); sel = f > lo
    return round(float(f[sel][np.argmax(pm[sel])]), 2)


def tails(s, fs):
    di = np.abs(np.diff(s, axis=1))
    o = {}
    for sec in (1, 2.5, 4, 5, 6):
        n = int(sec * fs)
        o[f"{sec}s"] = {"mean": float(di[:, -n:].mean()), "median": float(np.median(di[:, -n:])),
                        "mean_of_chanmean_signal": float(np.abs(np.diff(s.mean(0)))[-n:].mean())}
    return o


def mad_jumps(s, t, epochs_ms):
    d = np.diff(s, axis=1)
    med = np.median(d, axis=1, keepdims=True)
    mad = np.median(np.abs(d - med), axis=1, keepdims=True)
    flag = np.abs(d - med) > 20 * mad
    tt = t[1:]
    inside = np.zeros_like(tt, dtype=bool)
    for a, b in epochs_ms:
        inside |= (tt >= a) & (tt <= b)
    out_idx = np.where(flag[:, ~inside].any(0))[0]
    return {"n_flagged": int(flag.sum()), "n_outside": int(flag[:, ~inside].sum()),
            "outside_t_range_ms": [float(tt[~inside][out_idx].min()), float(tt[~inside][out_idx].max())] if len(out_idx) else None}


# P1
for f, segs in [("Patient1/P1_SEEG_SEEG_fit.npz", {"stim": (41, 358), "post": (360, 830), "tail": (830, 1500)}),
                ("Patient1/P1_TI_SEEG_fit.npz", {"stim": (40, 660), "post": (773, 1010), "tail": (1010, 1650)})]:
    s, t, n = load(f); fs = 1000.0 / (t[1] - t[0])
    r = {"tails": tails(s, fs), "peaks": {k: peak(s[:, a:b], fs) for k, (a, b) in segs.items() if k != "tail"}}
    a, b = segs["post"]
    # strongest channels in post-stim episode
    sd = s[:, a:b].std(1)
    r["post_top_std_channels"] = [n[i] for i in np.argsort(-sd)[:8]]
    a, b = segs["stim"]
    sd = np.abs(np.diff(s[:, a:b], axis=1)).mean(1)
    r["stim_top_absdiff_channels"] = [n[i] for i in np.argsort(-sd)[:8]]
    res[f] = r

# P2
s, t, n = load("Patient2/P2_SEEG_ts_fit.npz"); fs = 1000.0 / (t[1] - t[0])
md = np.abs(np.diff(s, axis=1)).mean(0); tt = t[1:]
base = np.median(md[(tt > 250) & (tt < 480)])
win = lambda a, b: [[float(x), round(float(y / base), 1)] for x, y in zip(tt[(tt >= a) & (tt <= b)], md[(tt >= a) & (tt <= b)])]
r = {"base_250_480ms": float(base), "around_onset": win(480, 530), "around_offset": win(3480, 3560),
     "ratio_stim_median": float(np.median(md[(tt > 520) & (tt < 3480)]) / base),
     "first_25_ratio": [round(float(x / base), 1) for x in md[:30]],
     "peaks": {"stim": peak(s[:, 63:437], fs), "post": peak(s[:, 443:925], fs)},
     "tails": tails(s, fs),
     "mad": mad_jumps(s, t, [(8, 200), (504, 3504), (3540, 7400)])}
# large slow deflection ~7000-7400 ms: channel-mean signal around then
cm = s.mean(0) - s.mean(0)[(t > 7500)].mean()
r["chanmean_dev_6500_7600"] = [[float(x), float(y)] for x, y in zip(t[(t >= 6500) & (t <= 7600)][::5], cm[(t >= 6500) & (t <= 7600)][::5])]
md_post = md[(tt > 3540) & (tt < 7400)]
r["post_vs_quiescent_ratio"] = [float(np.median(md_post) / base), float(np.median(md[tt > 7500]) / base)]
res["Patient2/P2_SEEG_ts_fit.npz"] = r

s, t, n = load("Patient2/P2_TI_SEEG_ts_fit.npz"); fs = 1000.0 / (t[1] - t[0])
md = np.abs(np.diff(s, axis=1)).mean(0); tt = t[1:]
base = np.median(md[(tt > 600) & (tt < 1000)])
win = lambda a, b: [[float(x), round(float(y / base), 1)] for x, y in zip(tt[(tt >= a) & (tt <= b)], md[(tt >= a) & (tt <= b)])]
cm = s.mean(0)
ac_seg = s[:, 110:290] - s[:, 110:290].mean(1, keepdims=True)
acf = np.mean([np.correlate(x, x, "full")[len(x) - 1:] / (x @ x) for x in ac_seg], 0)
r = {"base_600_1000ms": float(base), "first_ratio": [[float(a), round(float(b / base), 1)] for a, b in zip(tt[:50:2], md[:50:2])],
     "around_onset": win(980, 1040), "around_offset": win(2960, 3040),
     "acf_peak_lag_ms": float((np.argmax(acf[10:40]) + 10) * 10),
     "peaks": {"stim": peak(s[:, 101:299], fs)},
     "post_ratio_3100_9000_median": float(np.median(md[tt > 3100]) / base),
     "post_max_ratio": float(md[tt > 3100].max() / base),
     "tails": tails(s, fs),
     "mad": mad_jumps(s, t, [(10, 450), (1010, 3000)])}
res["Patient2/P2_TI_SEEG_ts_fit.npz"] = r
json.dump(res, open(sys.argv[1], "w"), indent=1)
print(json.dumps(res, indent=None)[:20000])
