"""R2 case-curation QC worker for ds004100 (BIDS iEEG, EDF).

Usage (from project root):
  python studies/study-001/work/T0023/qc_case.py --case HUP157 \
      --bids-root data/ds004100-1.1.3 \
      --manifest studies/study-001/work/T0015/retrieval_manifest.csv \
      --out studies/study-001/work/T0023

Read-only on raw data. Writes into --out:
  qc_summary_<case>.json   full machine-readable QC record
  qc_channels_<case>.csv   per-run x per-channel signal metrics
Does not open participants.tsv or any outcome source.
"""
import argparse, csv, glob, hashlib, io, json, os, re, sys, warnings
import numpy as np
import pandas as pd
from scipy.signal import welch

import mne
import mne_bids

MNI_BOX = {"x": (-80, 80), "y": (-120, 90), "z": (-70, 90)}  # mm, generous brain box
NON_NEURAL_RE = re.compile(r"^(EKG|ECG|EMG|EOG|RESP|RR$|RATE$|DC\d|ROC|LOC|C3$|C4$|CZ$|FZ$|PZ$|O1$|O2$|F3$|F4$|P3$|P4$|T3$|T4$|T5$|T6$|FP1$|FP2$|A1$|A2$)", re.I)



def norm_name(n):
    """Strip recording-system decorations ('EEG ', 'POL ', '-Ref', spaces): 'EEG LG 12-Ref' -> 'LG12'."""
    n = re.sub(r"^(EEG|POL|SEEG|ECOG)\s+", "", n.strip(), flags=re.I)
    n = re.sub(r"-(Ref|REF|ref)$", "", n)
    return n.replace(" ", "")


def is_nonneural(n):
    return bool(NON_NEURAL_RE.match(norm_name(n)))


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def edf_header(path):
    """Minimal EDF/EDF+ header parse (no data)."""
    with open(path, "rb") as f:
        h = f.read(256)
        ns = int(h[252:256].decode("ascii").strip())
        s = f.read(ns * 256)
    def field(off_per, width):
        start = sum(off_per)
        return [s[ns * start + i * width: ns * start + (i + 1) * width].decode("latin-1").strip() for i in range(ns)]
    widths = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
    names = ["label", "transducer", "phys_dim", "phys_min", "phys_max", "dig_min", "dig_max", "prefilter", "n_samp", "reserved"]
    out = {}
    off = 0
    for n, w in zip(names, widths):
        out[n] = [s[off + i * w: off + (i + 1) * w].decode("latin-1").strip() for i in range(ns)]
        off += ns * w
    return {
        "version": h[0:8].decode("latin-1").strip(),
        "reserved44": h[192:236].decode("latin-1").strip(),
        "n_records": int(h[236:244].decode("ascii").strip()),
        "record_duration_s": float(h[244:252].decode("ascii").strip()),
        "n_signals": ns,
        "labels": out["label"],
        "phys_dim": out["phys_dim"],
        "phys_min": [float(x) for x in out["phys_min"]],
        "phys_max": [float(x) for x in out["phys_max"]],
        "dig_min": [int(float(x)) for x in out["dig_min"]],
        "dig_max": [int(float(x)) for x in out["dig_max"]],
        "n_samp_per_record": [int(x) for x in out["n_samp"]],
        "prefilter": out["prefilter"],
    }


def robust_z(x):
    x = np.asarray(x, float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med)) * 1.4826
    if not np.isfinite(mad) or mad == 0:
        return np.zeros_like(x)
    return (x - med) / mad


def runs_of_true(mask, min_len):
    """Return list of (start, length) runs of True with length >= min_len."""
    if mask.size == 0:
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    return [(int(s), int(e - s)) for s, e in zip(starts, ends) if e - s >= min_len]


def qc_run(edf_path, ch_tsv, ev_tsv, case, bids_root, ents):
    rec = {"edf": os.path.relpath(edf_path, bids_root).replace("\\", "/"), "entities": ents}
    hdr = edf_header(edf_path)
    fs_set = sorted({n / hdr["record_duration_s"] for n in hdr["n_samp_per_record"]})
    rec["edf_header"] = {k: hdr[k] for k in ("version", "reserved44", "n_records", "record_duration_s", "n_signals")}
    rec["edf_header"]["phys_dim_values"] = sorted(set(hdr["phys_dim"]))
    rec["edf_header"]["sampling_rates_hz"] = fs_set
    rec["edf_type"] = "EDF+D (discontinuous)" if hdr["reserved44"].startswith("EDF+D") else ("EDF+C" if hdr["reserved44"].startswith("EDF+C") else "EDF (plain)")

    # sidecar
    sidecar_path = edf_path.replace("_ieeg.edf", "_ieeg.json")
    side = json.load(open(sidecar_path, encoding="utf-8")) if os.path.exists(sidecar_path) else None
    rec["sidecar"] = side

    # mne-bids read (metadata coherence; captures warnings)
    bp = mne_bids.BIDSPath(root=bids_root, subject=case, session=ents.get("ses"), task=ents.get("task"),
                           acquisition=ents.get("acq"), run=ents.get("run"), datatype="ieeg", suffix="ieeg", extension=".edf")
    mb = {}
    with warnings.catch_warnings(record=True) as wl:
        warnings.simplefilter("always")
        try:
            rb = mne_bids.read_raw_bids(bp, verbose="ERROR")
            mb["ok"] = True
            mb["n_channels"] = len(rb.ch_names)
            mb["bads"] = list(rb.info["bads"])
            mb["n_annotations"] = len(rb.annotations)
            mb["annotation_descriptions"] = sorted(set(rb.annotations.description))
            mb["ch_types"] = dict(pd.Series(rb.get_channel_types()).value_counts().astype(int))
            dig = rb.info.get("dig") or []
            mb["n_dig_points"] = len(dig)
            if dig:
                xyz = np.array([d["r"] for d in dig])
                mb["dig_coord_frame"] = int(dig[0]["coord_frame"])
                mb["dig_abs_max_internal_units"] = float(np.nanmax(np.abs(xyz)))
            del rb
        except Exception as e:  # recorded, not hidden
            mb["ok"] = False
            mb["error"] = f"{type(e).__name__}: {e}"
    mb["warnings"] = sorted({str(w.message)[:300] for w in wl})
    rec["mne_bids_read"] = mb

    # data read
    raw = mne.io.read_raw_edf(edf_path, preload=True, verbose="ERROR")
    fs = float(raw.info["sfreq"])
    rec["sfreq_hz"] = fs
    rec["n_samples"] = int(raw.n_times)
    rec["duration_s"] = raw.n_times / fs
    rec["n_channels_edf"] = len(raw.ch_names)
    rec["edf_annotations"] = [{"onset": float(a["onset"]), "duration": float(a["duration"]), "description": a["description"]} for a in raw.annotations]
    data = (raw.get_data() * 1e6).astype(np.float32)  # V -> uV (EDF phys_dim scaled by mne)
    names = list(raw.ch_names)
    del raw

    # channels.tsv
    ch = pd.read_csv(ch_tsv, sep="\t", dtype=str, keep_default_na=False, encoding="utf-8")
    rec["channels_tsv"] = os.path.relpath(ch_tsv, bids_root).replace("\\", "/")
    rec["channels_tsv_names_match_edf"] = list(ch["name"]) == names
    rec["channels_only_in_tsv"] = sorted(set(ch["name"]) - set(names))
    rec["channels_only_in_edf"] = sorted(set(names) - set(ch["name"]))
    sd = ch["status_description"].str.lower()
    rec["soz"] = list(ch.loc[sd.str.contains(r"\bsoz\b"), "name"])
    rec["resect"] = list(ch.loc[sd.str.contains(r"\bresect\b"), "name"])
    rec["status_description_values"] = dict(ch["status_description"].value_counts().astype(int))
    rec["type_counts"] = dict(ch["type"].value_counts().astype(int))
    rec["status_counts"] = dict(ch["status"].value_counts().astype(int))
    rec["tsv_units"] = sorted(set(ch["units"]))
    rec["tsv_sampling_frequency"] = sorted(set(ch["sampling_frequency"]))
    rec["bad_in_tsv"] = list(ch.loc[ch["status"] == "bad", "name"])
    rec["non_neural_named_channels"] = [n for n in ch["name"] if is_nonneural(n)]
    rec["non_neural_typed_as_neural"] = [n for n, t in zip(ch["name"], ch["type"]) if is_nonneural(n) and t.upper() in ("SEEG", "ECOG")]

    # per-channel signal metrics
    good_mask = np.array([(n not in rec["bad_in_tsv"]) and not is_nonneural(n) for n in names])
    std = data.std(axis=1).astype(float)
    ptp = (data.max(axis=1) - data.min(axis=1)).astype(float)
    dif = np.diff(data, axis=1)
    zero_diff_frac = (dif == 0).mean(axis=1).astype(float)
    nan_count = np.isnan(data).sum(axis=1).astype(int)
    # clipping vs EDF physical range
    hidx = [hdr["labels"].index(n) if n in hdr["labels"] else None for n in names]  # map by label (skips 'EDF Annotations')
    pmin = np.array([hdr["phys_min"][j] if j is not None else np.nan for j in hidx], float)
    pmax = np.array([hdr["phys_max"][j] if j is not None else np.nan for j in hidx], float)
    dims = [hdr["phys_dim"][j] if j is not None else "" for j in hidx]
    rec["edf_phys_range_uv"] = sorted({(float(a), float(b)) for a, b in zip(pmin, pmax) if np.isfinite(a)})
    scale = np.array([1.0 if d.lower() in ("uv", "µv", "\xb5v") else (1e3 if d.lower() == "mv" else (1e6 if d.lower() == "v" else np.nan)) for d in dims])
    lo = pmin * scale; hi = pmax * scale
    tol = (hi - lo) / 65535.0 * 1.5
    clip_frac = np.array([((data[i] <= lo[i] + tol[i]) | (data[i] >= hi[i] - tol[i])).mean() if np.isfinite(lo[i]) else np.nan for i in range(len(names))], float)
    # line noise (60 Hz)
    seg = data[:, : int(min(data.shape[1], 120 * fs))]
    f, P = welch(seg, fs=fs, nperseg=int(2 * fs), axis=1)
    def band(lo_, hi_):
        return (f >= lo_) & (f <= hi_)
    ref = band(50, 57) | band(63, 70)
    line = band(59, 61)
    line_ratio = (P[:, line].mean(axis=1) / np.median(P[:, ref], axis=1)).astype(float)
    h120 = band(119, 121)
    ref120 = band(110, 117) | band(123, 130)
    line_ratio_120 = (P[:, h120].mean(axis=1) / np.median(P[:, ref120], axis=1)).astype(float) if fs > 260 else np.full(len(names), np.nan)
    hf = (P[:, band(80, 200)].sum(axis=1) / P[:, band(1, 200)].sum(axis=1)).astype(float)
    del seg, P

    flat = (std < 0.5) | (zero_diff_frac > 0.5)
    lz = np.full(len(names), np.nan); lz[good_mask] = robust_z(np.log10(std[good_mask] + 1e-6))
    lnz = np.full(len(names), np.nan); lnz[good_mask] = robust_z(np.log10(line_ratio[good_mask] + 1e-9))
    hfz = np.full(len(names), np.nan); hfz[good_mask] = robust_z(hf[good_mask])
    high_var = lz > 5
    low_var = lz < -5
    line_outlier = (lnz > 5) & (line_ratio > 10)
    hf_outlier = hfz > 5
    clipping = clip_frac > 0.001

    # discontinuities: simultaneous all-good-channel flat stretches and simultaneous steps
    g = dif[good_mask] if good_mask.any() else dif
    all_flat = (g == 0).all(axis=0)
    flat_segments = runs_of_true(all_flat, int(0.5 * fs))
    thr = 20 * np.median(np.abs(g), axis=1, keepdims=True) + 1e-6
    step_frac = (np.abs(g) > thr).mean(axis=0)
    step_idx = np.where(step_frac > 0.5)[0]
    # merge consecutive samples into events
    step_events = []
    for s in step_idx:
        if step_events and s - step_events[-1][-1] <= int(0.1 * fs):
            step_events[-1].append(int(s))
        else:
            step_events.append([int(s)])
    del dif, g

    rows = []
    for i, n in enumerate(names):
        flags = [k for k, v in (("flat", flat[i]), ("high_variance", high_var[i]), ("low_variance", low_var[i]),
                                ("line_noise", line_outlier[i]), ("hf_noise", hf_outlier[i]), ("clipping", clipping[i]),
                                ("nan", nan_count[i] > 0)) if v]
        rows.append({"channel": n, "tsv_status": ch["status"].iloc[i] if i < len(ch) and ch["name"].iloc[i] == n else "",
                     "evaluated": bool(good_mask[i]), "std_uv": round(std[i], 3), "ptp_uv": round(ptp[i], 2),
                     "zero_diff_frac": round(zero_diff_frac[i], 4), "clip_frac": round(float(clip_frac[i]), 5),
                     "line60_ratio": round(line_ratio[i], 2), "line120_ratio": round(float(line_ratio_120[i]), 2),
                     "hf_80_200_frac": round(hf[i], 4), "logstd_robust_z": round(float(lz[i]), 2) if np.isfinite(lz[i]) else "",
                     "flags": ";".join(flags)})
    ev = [r for r in rows if r["evaluated"]]
    rec["signal_qc"] = {
        "evaluated_channels": int(good_mask.sum()),
        "excluded_from_eval": [n for n, m in zip(names, good_mask) if not m],
        "median_std_uv": float(np.median(std[good_mask])) if good_mask.any() else None,
        "median_line60_ratio": float(np.median(line_ratio[good_mask])) if good_mask.any() else None,
        "flagged": {k: [r["channel"] for r in ev if k in r["flags"].split(";")] for k in ("flat", "high_variance", "low_variance", "line_noise", "hf_noise", "clipping", "nan")},
        "n_flagged_any": sum(1 for r in ev if r["flags"]),
        "all_channel_flat_segments": [{"start_s": s / fs, "dur_s": l / fs} for s, l in flat_segments],
        "simultaneous_step_events": [{"t_s": e[0] / fs, "n_samples": len(e)} for e in step_events][:50],
        "n_simultaneous_step_events": len(step_events),
        "run_level_line60_ratio_median": float(np.median(line_ratio[good_mask])) if good_mask.any() else None,
        "run_level_line_noise": bool(good_mask.any() and np.median(line_ratio[good_mask]) > 10),
        "edf_record_count_x_duration_equals_samples": bool(hdr["n_records"] * hdr["record_duration_s"] * fs == data.shape[1]),
        "thresholds": "flat: std<0.5uV or >50% zero first-differences; high/low variance: |robust z(log10 std)|>5 among evaluated channels; line_noise: robust z(log10 P59-61/median P50-57,63-70)>5 and ratio>10 (Welch 2 s, first 120 s); hf_noise: robust z(P80-200/P1-200)>5; clipping: >0.1% samples within 1.5 LSB of EDF phys min/max; discontinuity: >=0.5 s where all evaluated channels have zero first-difference, or samples where >50% of evaluated channels jump >20x their median |diff|",
    }
    del data

    # events
    if ev_tsv and os.path.exists(ev_tsv):
        e = pd.read_csv(ev_tsv, sep="\t", keep_default_na=False, encoding="utf-8")
        evs = []
        for _, r in e.iterrows():
            on = float(r["onset"]); du = float(r["duration"]) if str(r["duration"]) not in ("n/a", "") else 0.0
            smp = r.get("sample", "n/a")
            evs.append({"onset_s": on, "duration_s": du, "trial_type": r.get("trial_type"), "value": r.get("value"), "sample": smp,
                        "within_recording": bool(0 <= on <= rec["duration_s"]),
                        "sample_matches_onset": (str(smp) not in ("n/a", "") and abs(int(float(smp)) - on * fs) <= 1)})
        on_ev = [x for x in evs if "onset" in str(x["trial_type"]).lower()]
        off_ev = [x for x in evs if "offset" in str(x["trial_type"]).lower()]
        coh = {"n_onset": len(on_ev), "n_offset": len(off_ev),
               "all_within_recording": all(x["within_recording"] for x in evs),
               "all_samples_match": all(x["sample_matches_onset"] for x in evs)}
        if len(on_ev) == 1 and len(off_ev) == 1:
            coh["offset_after_onset"] = off_ev[0]["onset_s"] > on_ev[0]["onset_s"]
            coh["seizure_duration_s"] = off_ev[0]["onset_s"] - on_ev[0]["onset_s"]
            coh["pre_onset_s"] = on_ev[0]["onset_s"]
            coh["post_offset_s"] = rec["duration_s"] - off_ev[0]["onset_s"]
        if len(on_ev) >= 1 and len(off_ev) >= 1:
            t0, t1 = min(x["onset_s"] for x in on_ev), max(x["onset_s"] for x in off_ev)
            st = [x["t_s"] for x in [{"t_s": e_[0] / fs} for e_ in step_events]]
            rec["signal_qc"]["step_events_inside_seizure_window"] = sum(1 for t in st if t0 <= t <= t1)
            rec["signal_qc"]["step_events_outside_seizure_window"] = [round(t, 3) for t in st if not (t0 <= t <= t1)]
        rec["events_tsv"] = os.path.relpath(ev_tsv, bids_root).replace("\\", "/")
        rec["events"] = evs
        rec["event_coherence"] = coh
    else:
        rec["signal_qc"]["step_events_outside_seizure_window"] = [round(e_[0] / fs, 3) for e_ in step_events]
        rec["events_tsv"] = None
        rec["events"] = []
        rec["event_coherence"] = {"note": "no events.tsv for this run"}
    return rec, rows


def coords_qc(el_tsv, cs_json, channel_names, bids_root):
    el = pd.read_csv(el_tsv, sep="\t", dtype=str, keep_default_na=False, encoding="utf-8")
    cs = json.load(open(cs_json, encoding="utf-8"))
    xyz = el[["x", "y", "z"]].apply(pd.to_numeric, errors="coerce")
    has = xyz.notna().all(axis=1)
    X = xyz[has].to_numpy(float)
    names = list(el.loc[has, "name"])
    out = {"electrodes_tsv": os.path.relpath(el_tsv, bids_root).replace("\\", "/"),
           "coordsystem_json": os.path.relpath(cs_json, bids_root).replace("\\", "/"),
           "coordsystem": cs, "n_rows": int(len(el)), "n_with_xyz": int(has.sum()),
           "rows_without_xyz": list(el.loc[~has, "name"]),
           "channels_without_electrode_row": sorted(set(channel_names) - set(el["name"])),
           "electrode_rows_without_channel": sorted(set(el["name"]) - set(channel_names))}
    if len(X):
        out["range"] = {a: [float(X[:, i].min()), float(X[:, i].max())] for i, a in enumerate("xyz")}
        out["abs_max"] = float(np.abs(X).max())
        inside = np.ones(len(X), bool)
        for i, a in enumerate("xyz"):
            inside &= (X[:, i] >= MNI_BOX[a][0]) & (X[:, i] <= MNI_BOX[a][1])
        out["frac_inside_mni_box_mm"] = float(inside.mean())
        out["outside_mni_box"] = [n for n, k in zip(names, inside) if not k]
        # nearest-neighbour spacing within the same electrode shaft (name prefix)
        nn_names = [norm_name(n) for n in names]
        pref = [re.match(r"^(.*?)(\d+)$", n).group(1) if re.match(r"^(.*?)(\d+)$", n) else n for n in nn_names]
        nn = []
        for p in set(pref):
            idx = [i for i, q in enumerate(pref) if q == p]
            if len(idx) < 2:
                continue
            Y = X[idx]
            D = np.sqrt(((Y[:, None, :] - Y[None, :, :]) ** 2).sum(-1)); np.fill_diagonal(D, np.inf)
            nn.extend(D.min(axis=1).tolist())
        out["median_within_shaft_nn_dist"] = float(np.median(nn)) if nn else None
        out["iqr_within_shaft_nn_dist"] = [float(np.percentile(nn, 25)), float(np.percentile(nn, 75))] if nn else None
        # hemisphere naming vs x sign (RAS check)
        L = [x for n, x in zip(names, X[:, 0]) if norm_name(n).upper().startswith("L")]
        R = [x for n, x in zip(names, X[:, 0]) if norm_name(n).upper().startswith("R")]
        out["hemisphere_check"] = {"n_L_prefixed": len(L), "frac_L_x_neg": float(np.mean(np.array(L) < 0)) if L else None,
                                   "n_R_prefixed": len(R), "frac_R_x_pos": float(np.mean(np.array(R) > 0)) if R else None}
        out["centroid"] = [float(v) for v in X.mean(axis=0)]
    # decision
    ev = []
    unit_mm = out.get("abs_max", 0) > 1.0
    ev.append(f"abs max coordinate {out.get('abs_max')}: {'>1 so values cannot be metres for a head (would be >1 m)' if unit_mm else '<=1, consistent with metres'}")
    if out.get("median_within_shaft_nn_dist") is not None:
        ev.append(f"median within-shaft nearest-contact spacing {out['median_within_shaft_nn_dist']:.2f} (typical SEEG/ECoG pitch 3.5-10 mm)")
    ev.append(f"{out.get('frac_inside_mni_box_mm', 0)*100:.1f}% of contacts inside MNI brain box [-80,80]x[-120,90]x[-70,90] mm")
    hc = out.get("hemisphere_check", {})
    ev.append(f"L-prefixed contacts with x<0: {hc.get('frac_L_x_neg')}; R-prefixed with x>0: {hc.get('frac_R_x_pos')} (RAS orientation check)")
    nn_ok = out.get("median_within_shaft_nn_dist") is not None and 1.5 <= out["median_within_shaft_nn_dist"] <= 15
    out["decision"] = {
        "units": "mm" if unit_mm and nn_ok else "to_verify",
        "units_basis": "value magnitudes and inter-contact spacing; coordsystem.json iEEGCoordinateUnits='m' judged a metadata error" if unit_mm and nn_ok else "inconclusive",
        "frame": "MNI-like template space (RAS, mm); specific template to_verify: README says ICBM152 MNI, coordsystem.json says fsaverage (FreeSurfer fsaverage = MNI305 Talairach space). MNI305 vs ICBM152 differ by a near-identity affine (few mm), not resolvable from coordinate values alone",
        "frame_status": "to_verify",
        "evidence": ev,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--bids-root", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    case, root = a.case, a.bids_root
    subdir = os.path.join(root, f"sub-{case}")
    files = sorted(p for p in glob.glob(os.path.join(subdir, "**", "*"), recursive=True) if os.path.isfile(p))

    # checksums
    man = pd.read_csv(a.manifest, dtype=str)
    man = man[man["path"].str.startswith(f"sub-{case}/")].set_index("path")
    chk = []
    for p in files:
        rel = os.path.relpath(p, root).replace("\\", "/")
        h = sha256(p); sz = os.path.getsize(p)
        m = man.loc[rel] if rel in man.index else None
        chk.append({"path": rel, "bytes": sz, "sha256": h,
                    "manifest_sha256": None if m is None else m["sha256"],
                    "match": None if m is None else (m["sha256"] == h and int(m["bytes"]) == sz)})
    local = {c["path"] for c in chk}
    missing_local = sorted(set(man.index) - local)
    summary = {"case_id": case, "bids_root": root.replace("\\", "/"),
               "checksums": {"n_files": len(chk), "n_match": sum(1 for c in chk if c["match"]),
                             "mismatches": [c for c in chk if c["match"] is False],
                             "not_in_manifest": [c["path"] for c in chk if c["match"] is None],
                             "in_manifest_missing_locally": missing_local, "files": chk},
               "versions": {"python": sys.version.split()[0], "mne": mne.__version__, "mne_bids": mne_bids.__version__,
                            "numpy": np.__version__, "pandas": pd.__version__}}

    # scans.tsv
    scans = glob.glob(os.path.join(subdir, "*", "*_scans.tsv"))
    summary["scans_tsv"] = [os.path.relpath(s, root).replace("\\", "/") for s in scans]

    # runs
    runs, allrows = [], []
    for edf in sorted(glob.glob(os.path.join(subdir, "*", "ieeg", "*_ieeg.edf"))):
        base = os.path.basename(edf)
        ents = dict(re.findall(r"(sub|ses|task|acq|run)-([A-Za-z0-9]+)", base))
        ch_tsv = edf.replace("_ieeg.edf", "_channels.tsv")
        ev_tsv = edf.replace("_ieeg.edf", "_events.tsv")
        print(f"[qc] {base}", flush=True)
        rec, rows = qc_run(edf, ch_tsv, ev_tsv if os.path.exists(ev_tsv) else None, case, root, ents)
        runs.append(rec)
        for r in rows:
            r["run"] = f"task-{ents.get('task')}_run-{ents.get('run')}"
            allrows.append(r)
    summary["runs"] = runs

    # cross-run channel consistency
    soz_sets = {r["edf"]: tuple(r["soz"]) for r in runs}
    res_sets = {r["edf"]: tuple(r["resect"]) for r in runs}
    bad_sets = {r["edf"]: tuple(r["bad_in_tsv"]) for r in runs}
    summary["cross_run"] = {"soz_identical_across_runs": len(set(soz_sets.values())) <= 1,
                            "resect_identical_across_runs": len(set(res_sets.values())) <= 1,
                            "bad_identical_across_runs": len(set(bad_sets.values())) <= 1,
                            "sfreqs": sorted({r["sfreq_hz"] for r in runs}),
                            "channel_counts": sorted({r["n_channels_edf"] for r in runs})}

    # coordinates
    el = glob.glob(os.path.join(subdir, "*", "ieeg", "*_electrodes.tsv"))
    cs = glob.glob(os.path.join(subdir, "*", "ieeg", "*_coordsystem.json"))
    ch_names = []
    if runs:
        ch0 = pd.read_csv(os.path.join(root, runs[0]["channels_tsv"]), sep="\t", dtype=str, keep_default_na=False, encoding="utf-8")
        ch_names = list(ch0["name"])
    summary["coordinates"] = coords_qc(el[0], cs[0], ch_names, root) if el and cs else {"status": "reported_absent"}
    if runs and el:
        neural_good = [n for n in ch_names if n not in runs[0]["bad_in_tsv"] and not is_nonneural(n)]
        noxyz = set(summary["coordinates"]["rows_without_xyz"]) | set(summary["coordinates"]["channels_without_electrode_row"])
        summary["coordinates"]["good_neural_channels_without_xyz"] = [n for n in neural_good if n in noxyz]
        summary["coordinates"]["soz_without_xyz"] = [n for n in runs[0]["soz"] if n in noxyz]
        summary["coordinates"]["resect_without_xyz"] = [n for n in runs[0]["resect"] if n in noxyz]

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"qc_summary_{case}.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    with open(os.path.join(a.out, f"qc_channels_{case}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
        w.writeheader(); w.writerows(allrows)
    print(json.dumps({"case": case, "runs": len(runs), "checksum_match": f"{summary['checksums']['n_match']}/{len(chk)}"}))


if __name__ == "__main__":
    main()
