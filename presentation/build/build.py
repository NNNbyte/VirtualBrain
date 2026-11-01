"""Build presentation/slides.html from committed study records (read-only) and the slides template.

Run with the model venv (nilearn bundles the fsaverage5 mesh used for the TI field):
    .venv-model/Scripts/python.exe presentation/build/build.py

Reads only: study ledgers, A0038-SimulationBatch outputs, Wang 2025 anatomy (Code Ocean, patient 2) and EMF maps.
Never reads studies/*/vault/ or any *truth* file. Writes only inside presentation/.
"""
import base64
import collections
import io
import json
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "presentation"
BATCH = ROOT / "studies/study-002/artifacts/A0038-SimulationBatch"
ANA = ROOT / "data/wang-co2-ana"
EMF = ROOT / "data/wang-5367ef4/data/EMF"

# Arms shown in the before/after figures and the 3D animation (npz key, label, family)
ARMS = [("BASELINE", "Before: no treatment", "base"),
        ("RES-EZpPZ__ablation", "After: ablation of estimated EZ + PZ", "res"),
        ("STIM-PT__amp1", "After: SEEG pulse-train stimulation (amp 1)", "stim")]
N_FRAMES = 360  # 14.4 s at 40 ms


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def ledger_stats(study):
    ev = [json.loads(l) for l in open(ROOT / f"studies/{study}/ledger.jsonl", encoding="utf-8")]
    c = collections.Counter(e["type"] for e in ev)
    gates = [e for e in ev if e["type"] == "gate_recorded"]
    verdicts = collections.Counter(e["verdict"] for e in gates)
    return {"events": len(ev), "tasks": c["task_admitted"], "artifacts": c["artifact_committed"],
            "gates": len(gates), "gates_passed": verdicts["passed"], "gates_failed": verdicts["failed"],
            "gates_indeterminate": verdicts["indeterminate"], "repairs": c["repair_issued"],
            "refused": c["task_refused"], "needs": c["need_opened"], "vault": c["vault_sealed"],
            "evaluators": sorted({e["evaluator"] for e in gates}),
            "first": ev[0]["ts"], "last": ev[-1]["ts"]}


def region_names():
    z = zipfile.ZipFile(ANA / "tvb/connectivity.vep.zip")
    names = [l.split()[0] for l in z.read("centres.txt").decode().splitlines()]
    assert names[0] == "Unknown" and len(names) == 163
    return names[1:]  # model region i == connectivity row i + 1 (verified: model 82 = Right-Orbito-frontal-cortex)


def sim_data(names):
    payload = json.load(open(BATCH / "payload.json"))
    full = payload["results"]["full"]
    sig = np.load(BATCH / "full_signals_median_sample.npz", allow_pickle=False)
    runs = json.load(open(BATCH / "full_runs.json"))
    med = full["median_sample"]["id"]
    seizing = {}
    for r in runs["baselines"] + runs["candidates"]:
        if r.get("sample_id") == med:
            seizing[r["candidate_id"]] = r["seizures"]["seizing_regions"]
    t = sig["BASELINE__t_ms"]
    idx = np.linspace(0, len(t) - 1, N_FRAMES).round().astype(int)
    u = {k: sig[k + "__u1"] for k, _, _ in ARMS}
    for k in u:
        assert np.isfinite(u[k]).all(), k
    ablated = [c for c in json.load(open(BATCH / "full_candidates.json"))["candidates"]
               if c["id"] == "RES-EZ+PZ/ablation"][0]["regions"]
    # Heatmap rows: regions active (u1 > -1) in any shown arm, plus the ablated set; ordered by first baseline crossing.
    active = set()
    for k in u:
        active |= set(np.where((u[k] > -1).any(0))[0].tolist())
    rows = sorted(active | set(ablated), key=lambda i: (np.argmax(u["BASELINE"][:, i] > -1) if (u["BASELINE"][:, i] > -1).any() else 10**6, i))
    lo, hi = -2.1, 0.5
    q = lambda a: np.clip((a - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    heat = {k: b64(q(u[k][idx][:, rows].T)) for k in u}  # rows x frames
    # SEEG traces: 6 channels with the largest baseline SD
    ch = [str(c) for c in sig["ch_names"]]
    sd = sig["BASELINE__seeg"].std(0)
    top = np.argsort(-sd)[:6].tolist()
    seeg = {k: [np.round(sig[k + "__seeg"][idx, j], 2).tolist() for j in top] for k, _, _ in ARMS}
    # Forest plot: change in number of seizing regions, finite paired runs only (finalize.py record)
    order = ["RES-EZ+PZ/ablation", "RES-EZ/ablation", "RES-1/ablation", "RES-EZ+PZ/disconnection",
             "RES-EZ/disconnection", "RES-1/disconnection", "STIM-1/amp2", "STIM-1/amp1", "STIM-1/amp0.5",
             "STIM-2/amp1", "STIM-PT/amp0.5", "STIM-PT/amp1", "STIM-PT-chronic/amp0.5", "STIM-PT-chronic/amp1"]
    eff = full["effects"]
    forest = [{"id": a, "median": eff[a]["d_n_seizing_regions"]["median"], "p05": eff[a]["d_n_seizing_regions"]["p05"],
               "p95": eff[a]["d_n_seizing_regions"]["p95"], "abolish": eff[a]["frac_abolish_all"], "n": eff[a]["n_samples"]}
              for a in order]
    return {"label": payload["label"], "headline": payload["headline"], "limitations": payload["limitations"],
            "baseline": full["baseline_summary"], "forest": forest,
            "failed_arms": list(full["numerically_failed_arms"].keys()),
            "qual_check": full["qualitative_check_vs_recording"]["verdict"],
            "median_sample": med, "seizing_median": {k: [names[i] for i in seizing.get(k.replace("__", "/").replace("EZpPZ", "EZ+PZ"), [])] for k, _, _ in ARMS},
            "rows": [names[i] for i in rows], "ablated_names": [names[i] for i in ablated],
            "heat": heat, "heat_lo": lo, "heat_hi": hi, "t_end_s": float(t[-1]) / 1000,
            "seeg_ch": [ch[j] for j in top], "seeg": seeg,
            "arms": [{"key": k, "label": l, "fam": f} for k, l, f in ARMS],
            "ez_set": [names[i] for i in full["derived"]["ez_set"]], "pz": [names[i] for i in full["derived"]["pz"]],
            "stim_contact": full["derived"]["stim1_contact_name"],
            "u_frames": {k: b64(q(u[k][idx])) for k in u},  # frames x 162
            "ablated": ablated, "n_frames": N_FRAMES}


def patient_brain():
    z = zipfile.ZipFile(ANA / "tvb/Cortex_pial_ico5.zip")
    v = np.loadtxt(io.BytesIO(z.read("vertices.txt")), dtype=np.float32)
    f = np.loadtxt(io.BytesIO(z.read("triangles.txt")), dtype=np.int64)
    rm = np.loadtxt(ANA / "tvb/region_map_ico5.txt").astype(np.int16) - 1  # -1 = Unknown
    con = [l.split() for l in open(ANA / "elec/seeg.xyz") if l.strip()]
    cxyz = np.array([[float(a) for a in l[1:4]] for l in con], dtype=np.float32)
    names = [l[0] for l in con]
    c = v.mean(0)
    s = float(np.abs(v - c).max())
    return {"v": b64((v - c) / s), "f": b64(f.astype(np.uint16)), "rm": b64(rm), "nv": len(v),
            "contacts": b64((cxyz - c) / s), "contact_names": names}


def template_brain():
    from nilearn import datasets, surface
    import nibabel as nib
    fs = datasets.fetch_surf_fsaverage("fsaverage5")
    vs, fs_, off = [], [], 0
    for h in ("left", "right"):
        m = surface.load_surf_mesh(fs[f"pial_{h}"])
        vs.append(np.asarray(m.coordinates, dtype=np.float32))
        fs_.append(np.asarray(m.faces, dtype=np.int64) + off)
        off += len(m.coordinates)
    v, f = np.vstack(vs), np.vstack(fs_)
    g = {k: np.concatenate([np.squeeze(np.asarray(nib.load(EMF / f"{h}.{k}_normal_field_fs_ico5.mgh").get_fdata()))
                            for h in ("lh", "rh")]) for k in ("E1", "E2")}
    depth = 2 * np.minimum(np.abs(g["E1"]), np.abs(g["E2"]))
    hi = float(np.percentile(depth, 99))
    c = v.mean(0)
    s = float(np.abs(v - c).max())
    return {"v": b64(((v - c) / s).astype(np.float32)), "f": b64(f.astype(np.uint16)), "nv": len(v),
            "ti": b64(np.clip(depth / hi * 255, 0, 255).astype(np.uint8)), "ti_hi": hi}


def next_version(folder, stem):
    """Never overwrite: the unversioned <stem>.html counts as v1, so the next build is <stem>_v2.html, then _v3, ..."""
    n = 2
    while (folder / f"{stem}_v{n}.html").exists():
        n += 1
    return folder / f"{stem}_v{n}.html"


def main():
    names = region_names()
    data = {"s1": ledger_stats("study-001"), "s2": ledger_stats("study-002"), "sim": sim_data(names),
            "patient": patient_brain(), "template": template_brain(), "region_names": names}
    tpl = (Path(__file__).parent / "slides_template.html").read_text(encoding="utf-8")
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    out = next_version(OUT, "slides")
    out.write_text(html, encoding="utf-8")
    print("wrote", out.name)
    # A small JSON of the numbers quoted on the slides, for checking against the records
    quoted = {k: data[k] for k in ("s1", "s2")}
    quoted["sim"] = {k: data["sim"][k] for k in ("label", "headline", "baseline", "forest", "failed_arms", "qual_check",
                                                 "median_sample", "seizing_median", "ez_set", "pz", "stim_contact", "ablated_names")}
    (Path(__file__).parent / "quoted_numbers.json").write_text(json.dumps(quoted, indent=1), encoding="utf-8")
    print("slides.html", round(len(html) / 1e6, 2), "MB")
    print(json.dumps(quoted["s1"]), json.dumps(quoted["s2"]))
    print(json.dumps(quoted["sim"]["seizing_median"]))


if __name__ == "__main__":
    main()
