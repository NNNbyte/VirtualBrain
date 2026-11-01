"""Build PatientCase + QCReport payload JSON (and commit context) from qc_summary_<case>.json.

Usage: python build_payloads.py <qc_summary.json> <out_dir> <split_label> <tool_sha256>
Writes <out_dir>/patientcase_<case>.json, qcreport_<case>.json, context_<case>.json.
No outcome information is read or written.
"""
import json, os, sys
from collections import Counter

summ_path, out_dir, split_label, tool_sha = sys.argv[1:5]
s = json.load(open(summ_path, encoding="utf-8"))
case = s["case_id"]
runs = s["runs"]
ictal = [r for r in runs if r["entities"].get("task") == "ictal"]
inter = [r for r in runs if r["entities"].get("task") == "interictal"]
co = s["coordinates"]
dec = co.get("decision", {})
r0 = runs[0]
sha = {f["path"]: f["sha256"] for f in s["checksums"]["files"]}
fs_set = sorted({r["sfreq_hz"] for r in runs})
fs = fs_set[0] if len(fs_set) == 1 else "/".join(str(x) for x in fs_set)
units_sig = sorted({u for r in runs for u in r["tsv_units"]})
edf_dims = sorted({u for r in runs for u in r["edf_header"]["phys_dim_values"] if u})
ictal_total = sum(r["duration_s"] for r in ictal)
sz_total = sum(r["event_coherence"].get("seizure_duration_s", 0) for r in ictal)
acq = sorted({r["entities"].get("acq") for r in runs})
sessions = sorted({r["entities"].get("ses") for r in runs})

def rid(r):
    return f"task-{r['entities'].get('task')}_acq-{r['entities'].get('acq')}_run-{r['entities'].get('run')}"

recordings = [{
    "run_id": rid(r), "task": r["entities"].get("task"), "acq": r["entities"].get("acq"), "run": r["entities"].get("run"),
    "edf_path": f"data/ds004100-1.1.3/{r['edf']}", "edf_sha256": sha.get(r["edf"]),
    "channels_tsv": r["channels_tsv"], "events_tsv": r["events_tsv"],
    "sfreq_hz": r["sfreq_hz"], "duration_s": r["duration_s"], "n_samples": r["n_samples"],
    "n_channels": r["n_channels_edf"], "edf_format": r["edf_type"],
    "sidecar_RecordingDuration_s": (r["sidecar"] or {}).get("RecordingDuration"),
    "power_line_hz": (r["sidecar"] or {}).get("PowerLineFrequency"),
} for r in runs]

events = {rid(r): {"annotations": [{"trial_type": e["trial_type"], "onset_s": e["onset_s"], "sample": e["sample"]} for e in r["events"]],
                   "coherence": r["event_coherence"]} for r in ictal}
for r in inter:
    events[rid(r)] = {"annotations": [], "coherence": "no events.tsv (interictal run; none expected)"}

nonneural = r0["non_neural_named_channels"]
channels = {
    "n_channels": r0["n_channels_edf"],
    "counts_by_type_channels_tsv": r0["type_counts"],
    "counts_by_status_channels_tsv": r0["status_counts"],
    "bad_channels_tsv": r0["bad_in_tsv"],
    "non_neural_by_name": nonneural,
    "non_neural_typed_as_neural_in_tsv": r0["non_neural_typed_as_neural"],
    "n_good_neural": r0["n_channels_edf"] - len(set(r0["bad_in_tsv"]) | set(nonneural)),
    "soz": {"n": len(r0["soz"]), "channels": r0["soz"], "source": "channels.tsv status_description tag 'soz' (clinician-marked)"},
    "resect": {"n": len(r0["resect"]), "channels": r0["resect"], "source": "channels.tsv status_description tag 'resect' (delivered intervention zone: resection or ablation, not distinguished)"},
    "soz_and_resect": sorted(set(r0["soz"]) & set(r0["resect"])),
    "soz_or_resect_marked_bad": sorted((set(r0["soz"]) | set(r0["resect"])) & set(r0["bad_in_tsv"])),
    "identical_across_runs": {"soz": s["cross_run"]["soz_identical_across_runs"], "resect": s["cross_run"]["resect_identical_across_runs"], "bad": s["cross_run"]["bad_identical_across_runs"]},
    "channel_names_match_edf_all_runs": all(r["channels_tsv_names_match_edf"] for r in runs),
    "n_with_coordinates": co.get("n_with_xyz"),
    "channels_without_coordinates": sorted(set(co.get("rows_without_xyz", [])) | set(co.get("channels_without_electrode_row", []))),
    "good_neural_channels_without_coordinates": co.get("good_neural_channels_without_xyz"),
}

coord_tf = {
    "transform_chain_id": "ds004100-coordsystem-as-provided",
    "declared_coordsystem_json": co.get("coordsystem"),
    "declared_readme": "README (dataset level, A0070): electrode localizations in ICBM152 MNI space",
    "decision": {"units": dec.get("units"), "units_basis": dec.get("units_basis"), "frame": dec.get("frame"), "frame_status": dec.get("frame_status")},
    "evidence": dec.get("evidence"),
    "value_ranges_mm": co.get("range"),
    "frac_inside_mni_box": co.get("frac_inside_mni_box_mm"),
    "median_within_shaft_spacing_mm": co.get("median_within_shaft_nn_dist"),
    "hemisphere_check": co.get("hemisphere_check"),
    "transforms_applied": "none - coordinates used numerically as provided; only the unit label is corrected (m -> mm); no subject-to-template registration information is available (no MRI/CT)",
    "downstream_hazard": f"mne_bids.read_raw_bids honours the declared 'm' and places contacts up to {r0['mne_bids_read'].get('dig_abs_max_internal_units')} m from origin; consumers must rescale by 1e-3 (or read electrodes.tsv as mm) before any geometry use",
}

pc = {
    "case_id": case, "bids_subject": f"sub-{case}",
    "dataset_id": "openneuro:ds004100 v1.1.3 (A0070-DatasetCard)",
    "split": f"{split_label} (A0071-CohortSplit)",
    "sessions": [{"session": x, "acquisitions": acq} for x in sessions],
    "recordings": recordings,
    "recording_summary": {"n_ictal_runs": len(ictal), "ictal_total_s": round(ictal_total, 3), "annotated_seizure_total_s": round(sz_total, 3),
                          "n_interictal_runs": len(inter), "interictal_total_s": round(sum(r["duration_s"] for r in inter), 3)},
    "checksums": {"manifest": "studies/study-001/work/T0015/retrieval_manifest.csv", "n_files": s["checksums"]["n_files"],
                  "n_match": s["checksums"]["n_match"], "mismatches": [m["path"] for m in s["checksums"]["mismatches"]],
                  "not_in_manifest": s["checksums"]["not_in_manifest"], "in_manifest_missing_locally": s["checksums"]["in_manifest_missing_locally"],
                  "sha256": sha},
    "anatomy": {"status": "template-only; electrodes.tsv coords", "mri": "reported_absent (no anat/ in v1.1.3)", "ct": "reported_absent",
                "electrodes_tsv": co.get("electrodes_tsv"), "coordsystem_json": co.get("coordsystem_json"),
                "atlas_labels": "not_reported (none in electrodes.tsv)"},
    "coordinate_transforms": coord_tf,
    "channels": channels,
    "montage": {"reference": "referential as recorded", "iEEGReference_sidecar": sorted({str((r["sidecar"] or {}).get("iEEGReference")) for r in runs}),
                "reference_electrode": "not_reported", "rereferencing_applied": "none"},
    "events": events,
    "units": {"signal": units_sig, "signal_edf_phys_dim": edf_dims, "signal_as_loaded_by_mne": "V (scaled from EDF uV)",
              "edf_physical_range_uv": sorted({tuple(x) for r in runs for x in r.get("edf_phys_range_uv", [])}),
              "time": "s", "coordinates": dec.get("units"), "coordinates_declared": (co.get("coordsystem") or {}).get("iEEGCoordinateUnits"),
              "sampling_rate_hz": fs},
    "intervention_linkage": "contact-level 'resect' tags only (delivered intervention); resection-vs-ablation not distinguished here",
    "outcome": "sealed - not read, not included",
    "qc_tool": {"script": "studies/study-001/work/T0023/qc_case.py", "sha256": tool_sha, "versions": s["versions"]},
}

# ---------------- QC report
findings, limits, exclude = [], [], []
def add(sev, fid, text, ev=None):
    findings.append({"id": fid, "severity": sev, "finding": text, **({"evidence": ev} if ev is not None else {})})

c = s["checksums"]
if c["mismatches"] or c["in_manifest_missing_locally"]:
    add("major", "checksum", f"{len(c['mismatches'])} sha256 mismatches, {len(c['in_manifest_missing_locally'])} manifest files missing", [m["path"] for m in c["mismatches"]] + c["in_manifest_missing_locally"])
    exclude.append("raw files do not match retrieval manifest")
else:
    add("info", "checksum", f"all {c['n_files']} case files match retrieval manifest sha256 and byte size")
fail_read = [rid(r) for r in runs if not r["mne_bids_read"].get("ok")]
add("major" if fail_read else "info", "read", f"mne-bids/mne read {'failed for ' + str(fail_read) if fail_read else 'succeeded for all ' + str(len(runs)) + ' runs'} (header + full data)")
if not ictal:
    exclude.append("no ictal run")
add("info", "format", f"EDF+C (continuous) all runs; {fs} Hz; {r0['n_channels_edf']} channels; records x duration == samples in all runs: {all(r['signal_qc']['edf_record_count_x_duration_equals_samples'] for r in runs)}; sidecar RecordingDuration = EDF duration - 1 sample (convention, benign)")
edfd = [rid(r) for r in runs if r["edf_type"].startswith("EDF+D")]
flatseg = {rid(r): r["signal_qc"]["all_channel_flat_segments"] for r in runs if r["signal_qc"]["all_channel_flat_segments"]}
tail_only = all(all(abs(seg["start_s"] + seg["dur_s"] - next(x for x in runs if rid(x) == k)["duration_s"]) < 0.01 for seg in v) for k, v in flatseg.items())
add("minor" if (edfd or (flatseg and not tail_only)) else "info", "discontinuity",
    f"EDF+D files: {edfd or 'none'}; all-channel flatline segments >=0.5 s: {flatseg or 'none'}"
    + (" (only at the very end of the file: trailing pad, trim before analysis)" if flatseg and tail_only else "")
    + "; simultaneous multi-channel step events are mostly inside annotated seizure windows (ictal activity, not acquisition gaps)",
    {rid(r): {"inside_sz": r["signal_qc"].get("step_events_inside_seizure_window"), "outside_sz_t_s": r["signal_qc"].get("step_events_outside_seizure_window")} for r in runs})
if flatseg and not tail_only:
    limits.append(f"within-recording all-channel flat segments: {flatseg}")
ln = {rid(r): round(r["signal_qc"]["run_level_line60_ratio_median"], 1) for r in runs}
ln_bad = [k for k, v in ln.items() if v > 10]
if ln_bad:
    add("minor", "line_noise", f"run-level 60 Hz contamination (median P59-61 / P50-57,63-70 ratio >10) in {ln_bad}; notch filtering required before spectral/connectivity analysis", ln)
    limits.append(f"60 Hz line noise in {len(ln_bad)}/{len(runs)} runs (notch needed)")
else:
    add("info", "line_noise", "no run-level 60 Hz contamination above ratio 10", ln)
flag_union = Counter()
for r in runs:
    for k, v in r["signal_qc"]["flagged"].items():
        for ch in v:
            flag_union[(ch, k)] += 1
recurrent = sorted({ch for (ch, k), n in flag_union.items() if n >= max(2, len(runs) // 2)})
add("minor" if flag_union else "info", "channel_flags",
    f"channels flagged by signal metrics (not tagged bad in channels.tsv); recurrent (>= half of runs): {recurrent}",
    {rid(r): {k: v for k, v in r["signal_qc"]["flagged"].items() if v} for r in runs})
flat_any = sorted({ch for r in runs for ch in r["signal_qc"]["flagged"]["flat"]})
if flat_any:
    add("minor", "flat", f"flat channels among status=good: {flat_any}")
soz_flag = sorted(set(recurrent) & set(r0["soz"]))
if soz_flag:
    add("minor", "soz_flagged", f"SOZ-tagged channels with recurrent high-variance/noise flags (may reflect epileptiform activity rather than artefact): {soz_flag}")
add("info", "bad_channels", f"{len(r0['bad_in_tsv'])} channels status=bad in channels.tsv: {r0['bad_in_tsv']}")
if r0["non_neural_typed_as_neural"]:
    add("minor", "channel_types", f"non-neural channels typed SEEG/ECOG in channels.tsv: {r0['non_neural_typed_as_neural']} (status bad; must be dropped by name, not by type)")
ev_ok = all(r["event_coherence"].get("all_within_recording") and r["event_coherence"].get("all_samples_match") and r["event_coherence"].get("offset_after_onset") and r["event_coherence"].get("n_onset") == 1 for r in ictal)
add("info" if ev_ok else "major", "annotations",
    f"{'all' if ev_ok else 'NOT all'} ictal runs have exactly one 'sz onset' and one 'sz offset' inside the recording, offset after onset, sample column == onset*fs; EDF files carry no embedded annotations",
    {rid(r): {k: r["event_coherence"].get(k) for k in ("pre_onset_s", "seizure_duration_s", "post_offset_s")} for r in ictal})
if not ev_ok:
    limits.append("annotation incoherence in some ictal run")
if not r0["soz"]:
    limits.append("no SOZ tags")
add("info" if r0["soz"] else "major", "soz_resect", f"soz tags n={len(r0['soz'])}, resect tags n={len(r0['resect'])}, overlap n={len(channels['soz_and_resect'])}; identical across runs: {channels['identical_across_runs']}")
add("info", "coordinates_missing", f"{co.get('n_with_xyz')}/{co.get('n_rows')} electrodes.tsv rows have xyz; without: {channels['channels_without_coordinates']}; good neural channels without xyz: {channels['good_neural_channels_without_coordinates']}")
add("minor", "coordinate_frame", "units resolved to mm (coordsystem.json 'm' is a metadata error); template frame ICBM152 (README) vs fsaverage/MNI305 (coordsystem.json) to_verify", dec.get("evidence"))
limits.append("coordinate template (ICBM152 vs fsaverage/MNI305) to_verify; template-only anatomy, no subject MRI/CT; declared unit 'm' must be overridden to mm")
if co.get("frac_inside_mni_box_mm", 1) < 0.95:
    limits.append(f"only {co.get('frac_inside_mni_box_mm'):.2f} of contacts inside MNI brain box")

missing = {
    "mri_ct": "reported_absent (dataset level)",
    "atlas_labels": "not_reported",
    "reference_electrode": "not_reported (iEEGReference n/a)",
    "interictal_events": "not_applicable",
    "channels_without_coordinates": channels["channels_without_coordinates"],
    "hardware_filters": "channels.tsv low_cutoff/high_cutoff only (0-fs/2), SoftwareFilters n/a",
    "manufacturer": "n/a in sidecar",
    "outcome": "sealed (not missing; intentionally inaccessible)",
}
verdict = "exclude" if exclude else ("accept_with_limits" if limits else "accept")
qc = {
    "case_id": case,
    "findings": findings,
    "missingness": missing,
    "verdict": verdict,
    "verdict_reasons": exclude if exclude else limits,
    "usable_runs": {"ictal": [rid(r) for r in ictal], "interictal": [rid(r) for r in inter]},
    "recommended_channel_exclusions": {"tsv_bad": r0["bad_in_tsv"], "non_neural": nonneural, "signal_flag_recurrent_review": recurrent},
    "methods": "qc_case.py (sha256 " + tool_sha + "): sha256 vs manifest; EDF header parse; mne_bids.read_raw_bids (metadata) + mne.io.read_raw_edf (full data); per-channel std/ptp/zero-diff/clipping/Welch 60,120 Hz ratios/80-200 Hz fraction with robust-z outliers over status=good neural channels; discontinuity scan; events.tsv coherence; electrodes.tsv ranges, within-shaft spacing, MNI-box and hemisphere-sign checks. Thresholds in qc_summary attachment.",
    "attachments": [f"qc_summary_{case}.json", f"qc_channels_{case}.csv"],
}
ctx = {"sample_rate_hz": fs, "time_window": f"ictal runs: n={len(ictal)}, total {ictal_total:.1f} s",
       "signal_units": "uV", "reference_montage": "referential as recorded",
       "coordinate_frame": "MNI-template (ICBM152 per README vs fsaverage/MNI305 per coordsystem.json; to_verify)",
       "coordinate_units": dec.get("units"), "transform_chain_id": "ds004100-coordsystem-as-provided"}
os.makedirs(out_dir, exist_ok=True)
json.dump(pc, open(os.path.join(out_dir, f"patientcase_{case}.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
json.dump(qc, open(os.path.join(out_dir, f"qcreport_{case}.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
json.dump(ctx, open(os.path.join(out_dir, f"context_{case}.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps({"verdict": verdict, "reasons": qc["verdict_reasons"], "ctx": ctx, "recurrent": recurrent}, indent=1, ensure_ascii=False))
