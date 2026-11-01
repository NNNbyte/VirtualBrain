"""R5 T0008: independent reproduction of P1/P2 case facts (A0007-A0010) from the checksummed npz files.
Run from project root with .venv-model/Scripts/python.exe. Reads only data/wang-5367ef4 (non-reserved npz + LUT)."""
import hashlib, json, csv, re, sys
import numpy as np
from scipy import signal

ROOT = "data/wang-5367ef4/"
man = {r[0]: (int(r[1]), r[2]) for r in csv.reader(open("data/wang-5367ef4-manifest.csv")) if len(r) == 3 and r[1].isdigit()}
out = {"checksums": {}}
FILES = {"P1": ["data/dataSim/Patient1/P1_SEEG_SEEG_fit.npz", "data/dataSim/Patient1/P1_TI_SEEG_fit.npz"],
         "P2": ["data/dataSim/Patient2/P2_SEEG_ts_fit.npz", "data/dataSim/Patient2/P2_TI_SEEG_ts_fit.npz"]}
for f in FILES["P1"] + FILES["P2"] + ["data/VepMrtrixLut.txt"]:
    b = open(ROOT + f, "rb").read()
    h = hashlib.sha256(b).hexdigest()
    out["checksums"][f] = {"sha256": h, "bytes": len(b), "manifest_match": man.get(f) == (len(b), h)}

lut = [l.split() for l in open(ROOT + "data/VepMrtrixLut.txt").read().splitlines() if l.strip()]
roi = [x[1] for x in lut][1:]
out["lut"] = {"n_entries": len(lut), "first": lut[0][:2], "last": lut[-1][:2], "n_regions": len(roi)}


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def movavg(x, n):
    return np.convolve(x, np.ones(n) / n, mode="same")


def runs(mask):
    r, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            r.append([start, i - 1]); start = None
    if start is not None:
        r.append([start, len(mask) - 1])
    return r


def electrodes(names):
    e = {}
    for n in names:
        m = re.match(r"^([A-Za-z]+'?)(\d+)-(\d+)$", n)
        assert m, n
        e.setdefault(m.group(1), []).append((int(m.group(2)), int(m.group(3))))
    adj = all(b == a + 1 for v in e.values() for a, b in v)
    return {k: len(v) for k, v in e.items()}, adj


for pid, files in FILES.items():
    P = out[pid] = {"sessions": {}}
    loaded = [np.load(ROOT + f, allow_pickle=False) for f in files]
    for f, d in zip(files, loaded):
        s = d["seeg"]; t = d["time_steps"]; dt = np.diff(t)
        fs = 1000.0 / dt[0]
        stds = s.std(1); means = s.mean(1)
        names = [str(x) for x in d["ch_names"]]
        di = np.diff(s, axis=1)
        step_idx = np.unravel_index(np.argmax(np.abs(di)), di.shape)
        n_at_ext = [int(max((row == row.max()).sum(), (row == row.min()).sum())) for row in s]
        md = np.abs(di).mean(0)
        sm = movavg(md, 20)
        base = np.median(md[:30])
        sess = {
            "keys": {k: [list(d[k].shape), str(d[k].dtype)] for k in d.files},
            "t_first_last": [float(t[0]), float(t[-1])], "dt_unique": sorted(set(np.round(dt, 9).tolist())),
            "fs_assuming_ms": fs, "n_ch": len(names), "n_samples": int(s.shape[1]),
            "nan": int(np.isnan(s).sum()), "inf": int(np.isinf(s).sum()),
            "mean_range": [float(means.min()), float(means.max())], "value_range": [float(s.min()), float(s.max())],
            "median_std": float(np.median(stds)), "min_std": float(stds.min()),
            "lowest_std_ch": [[names[i], float(stds[i])] for i in np.argsort(stds)[:5]],
            "n_std_lt_1e-6": int((stds < 1e-6).sum()), "n_std_lt_1pct_median": int((stds < 0.01 * np.median(stds)).sum()),
            "max_samples_at_extreme": max(n_at_ext), "consecutive_equal_samples": int((di == 0).sum()),
            "frames_equal_prev": int((np.abs(di).max(0) == 0).sum()),
            "largest_step": [float(np.abs(di).max()), names[step_idx[0]], int(step_idx[1]) + 1, float(di[step_idx])],
            "baseline_median_absdiff_first30": float(base),
            "runs_gt10x": runs(sm > 10 * base), "runs_gt3x": runs(sm > 3 * base),
            "md_ratio_examples": {},
        }
        for sec in (2.5, 5, 6):
            n = int(sec * fs)
            sess[f"tail_{sec}s_mean_absdiff"] = float(np.abs(di[:, -n:]).mean())
        P["sessions"][f] = sess
        P["names"] = names
        P.setdefault("md", {})[f] = md
        P.setdefault("sig", {})[f] = (s, fs)
    a, b = loaded
    P["identical_across_sessions"] = {k: bool(np.array_equal(a[k], b[k])) for k in ("SC", "gain", "ch_names")}
    SC = a["SC"]; G = a["gain"]
    off = ~np.eye(SC.shape[0], dtype=bool)
    st = SC.sum(1)
    P["SC"] = {"shape": list(SC.shape), "symmetric": bool(np.array_equal(SC, SC.T)), "diag_zero": bool((np.diag(SC) == 0).all()),
               "min": float(SC.min()), "max": float(SC.max()), "nan": int(np.isnan(SC).sum()),
               "density_offdiag": float((SC[off] != 0).mean()), "density_full": float((SC != 0).mean()),
               "strength_min_max": [float(st.min()), float(st.max())], "isolated": [int(i) for i in np.where(st == 0)[0]],
               "sha256": sha(SC)}
    P["gain"] = {"shape": list(G.shape), "min": float(G.min()), "max": float(G.max()), "n_negative": int((G < 0).sum()),
                 "nan": int(np.isnan(G).sum()), "zero_cols": [int(i) for i in np.where((G == 0).all(0))[0]],
                 "zero_rows": int((G == 0).all(1).sum()), "sha256": sha(G)}
    P["electrodes"], P["all_adjacent"] = electrodes(P["names"])
    P["unique_names"] = len(set(P["names"])) == len(P["names"])
    L, R = slice(0, 81), slice(81, 162)
    offL = off[L, L]
    P["order_checks"] = {
        "SC_intra_vs_inter_hemi_mean": [float(np.r_[SC[L, L][offL], SC[R, R][offL]].mean()), float(SC[L, R].mean())],
        "SC_homolog_corr_LL_vs_RR": float(np.corrcoef(SC[L, L][offL], SC[R, R][offL])[0, 1]),
        "SC_homolog_pairs_mean_vs_LR_mean": [float(np.mean([SC[i, i + 81] for i in range(81)])), float(SC[L, R].mean())],
        "gain_cereb_cols_80_161": {"col80_ptp": float(np.ptp(G[:, 80])), "col161_ptp": float(np.ptp(G[:, 161])),
                                   "col80_max": float(G[:, 80].max()), "col161_max": float(G[:, 161].max()),
                                   "global_min": float(G.min()),
                                   "eq_global_min": bool(G[:, 80].max() == G.min() and G[:, 161].max() == G.min())},
    }
    prim = np.array(["'" in n for n in P["names"]])
    am = G.argmax(1)
    P["order_checks"]["primed_channel_argmax_region_left"] = [int(((am < 81) & prim).sum()), int(prim.sum())]
    P["order_checks"]["unprimed_channel_argmax_region_right"] = [int(((am >= 81) & ~prim).sum()), int((~prim).sum())]
    abe = {}
    for e in P["electrodes"]:
        idx = [i for i, n in enumerate(P["names"]) if re.match("^" + re.escape(e) + r"\d", n)]
        regs = {}
        for i in idx:
            regs[roi[am[i]]] = regs.get(roi[am[i]], 0) + 1
        abe[e] = sorted(regs.items(), key=lambda x: -x[1])[:4]
    P["order_checks"]["argmax_region_by_electrode"] = abe
    A = np.abs(G); gmax = A.max()
    rows = []
    for r in range(162):
        col = A[:, r]; mx = col.max()
        rows.append({"i": r, "region": roi[r], "max_abs_gain": round(float(mx), 4),
                     "n_gt25_global": int((col > 0.25 * gmax).sum()), "n_gt25_own": int((col > 0.25 * mx).sum()),
                     "top3": [P["names"][j] for j in np.argsort(-col)[:3]]})
    P["coverage"] = {"rows": rows, "global_max": float(gmax),
                     "n_any_gt25_global": sum(r["n_gt25_global"] > 0 for r in rows),
                     "n_ge3_gt25_global": sum(r["n_gt25_global"] >= 3 for r in rows),
                     "left_mean": round(float(np.mean([r["max_abs_gain"] for r in rows[:81]])), 3),
                     "right_mean": round(float(np.mean([r["max_abs_gain"] for r in rows[81:]])), 3)}
    P["n_primed_electrodes"] = sum("'" in e for e in P["electrodes"])

# keep arrays for interactive follow-up when imported
_cache = {p: (out[p].pop("md"), out[p].pop("sig"), out[p].pop("names")) for p in ("P1", "P2")}
if __name__ == "__main__":
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    print("ok")
