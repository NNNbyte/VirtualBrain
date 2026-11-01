"""Study-002 summary report: workflow, agent history, modeling, simulation (3D brain, before/after), truth check.

    .venv-model/Scripts/python.exe system/reports/study2_report.py [--out reports/study-002-summary.html]

Reads only the ledger, committed artifacts, work files and the public/permitted anatomy. Never reads the vault;
the ground-truth evaluation is shown only from R5's committed OutcomeEvaluation.
"""
import argparse
import base64
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain3d  # noqa: E402
import study_report as sr  # noqa: E402

ROOT = sr.ROOT
E = sr.E
STUDY = "study-002"
ANA = ROOT / "data/wang-co2-ana"
EMF = ROOT / "data/wang-5367ef4/data/EMF"


def art_dir(d, aid):
    return next(p for p in (d / "artifacts").iterdir() if p.name.startswith(aid))


def payload(d, aid):
    return json.loads((art_dir(d, aid) / "payload.json").read_text(encoding="utf-8"))


def region_names():
    z = zipfile.ZipFile(ANA / "tvb/connectivity.vep.zip")
    names = [l.split()[0] for l in z.read("centres.txt").decode().splitlines()]
    return names[1:]


def png_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    return base64.b64encode(buf.getvalue()).decode()


def before_after_png(batch, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    z = np.load(batch / "full_signals_median_sample.npz", allow_pickle=False)
    arms = [("BASELINE", "Before: no treatment", "#52514e"),
            ("RES-EZpPZ__ablation", "After: ablation of estimated EZ + PZ", "#2a78d6"),
            ("STIM-1__amp1", "After: sustained-current SEEG stimulation", "#1baf7a"),
            ("STIM-PT__amp1", "After: paper's 50 Hz pulse train (3 s)", "#eb6834")]
    t = z["BASELINE__t_ms"] / 1000
    ub = z["BASELINE__u1"]
    act = np.argsort(-ub.max(0))[:18]
    sb = z["BASELINE__seeg"]
    ch = [str(c) for c in z["ch_names"]]
    top = np.argsort(-sb.std(0))[:6]
    fig, ax = plt.subplots(2, 4, figsize=(20, 7.5), gridspec_kw={"height_ratios": [1, 1]})
    for j, (k, title, col) in enumerate(arms):
        u, s = z[k + "__u1"], z[k + "__seeg"]
        ax[0, j].imshow(u[:, act].T, aspect="auto", extent=[t[0], t[-1], len(act) - .5, -.5], cmap="viridis",
                        vmin=ub[:, act].min(), vmax=ub[:, act].max())
        ax[0, j].set_yticks(range(len(act)))
        ax[0, j].set_yticklabels([names[i] for i in act] if j == 0 else [], fontsize=6.5)
        ax[0, j].set_title(title, fontsize=10)
        for n, c in enumerate(top):
            ax[1, j].plot(t, (s[:, c] - sb[:, c].mean()) / (sb[:, c].std() * 4) + n, lw=.6, color=col)
        ax[1, j].set_yticks(range(len(top)))
        ax[1, j].set_yticklabels([ch[c] for c in top] if j == 0 else [], fontsize=7)
        ax[1, j].set_xlabel("time (s)")
        for a in ax[:, j]:
            a.spines[["top", "right"]].set_visible(False)
    ax[0, 0].set_ylabel("region activity (u1)")
    ax[1, 0].set_ylabel("simulated SEEG")
    fig.tight_layout()
    out = png_b64(fig)
    plt.close(fig)
    return out


def forest_svg(eff, order, labels):
    rows = [(labels.get(a, a), eff[a]["d_n_seizing_regions"], eff[a]["frac_abolish_all"]) for a in order if a in eff]
    left, top, rh, w = 300, 14, 30, 1080
    lo = min(r[1]["p05"] for r in rows) - .5
    hi = max(r[1]["p95"] for r in rows) + .5
    h = top + len(rows) * rh + 36
    s = sr.Svg(w, h, "Paired change in the number of seizing regions per candidate")
    X = lambda v: left + (v - lo) / (hi - lo) * (w - left - 170)
    for tk in sr.nice_ticks(lo, hi, 8):
        s.line(X(tk), top - 4, X(tk), h - 30, "grid")
        s.text(X(tk), h - 14, f"{tk:g}", "t-muted", "middle")
    s.line(X(0), top - 6, X(0), h - 30, "diag")
    for i, (lab, d, ab) in enumerate(rows):
        y = top + i * rh + rh / 2
        s.text(left - 12, y + 4, lab, "t-small", "end")
        col = "var(--s1)" if d["median"] < 0 else "var(--neutral)"
        tip = f"{lab}: median {d['median']:+g} regions (5-95%: {d['p05']:+.1f} to {d['p95']:+.1f}); all seizures abolished in {ab:.0%} of samples"
        s.add(f'<g class="mark" {sr.tip(tip)}><rect x="{X(d["p05"]):.1f}" y="{y - 4:.1f}" width="{max(2, X(d["p95"]) - X(d["p05"])):.1f}" height="8" rx="4" fill="{col}" opacity=".35"/>'
              f'<circle cx="{X(d["median"]):.1f}" cy="{y:.1f}" r="6" fill="{col}" class="ring"/>'
              f'<rect x="{left}" y="{y - rh / 2:.1f}" width="{w - left}" height="{rh}" fill="transparent"/></g>')
        s.text(w - 160, y + 4, f"{d['median']:+g}  ·  abolished {ab:.0%}", "t-muted")
    s.text(X(0), h - 1, "← fewer seizing regions    0    more →", "t-muted", "middle")
    return s.render()


def flatten(obj, prefix="", out=None, depth=0):
    out = [] if out is None else out
    if isinstance(obj, dict) and depth < 3:
        for k, v in obj.items():
            flatten(v, f"{prefix}{k}." if prefix or True else k, out, depth + 1)
    else:
        txt = json.dumps(obj) if not isinstance(obj, str) else obj
        out.append((prefix.rstrip("."), txt[:400] + ("…" if len(txt) > 400 else "")))
    return out


def build(out):
    d, st, events = sr.load(STUDY)
    arts = st["artifacts"]
    tasks = sr.task_rows(events)
    t0, t1 = sr.ts(events[0]["ts"]), sr.ts(events[-1]["ts"])
    ev = Counter(e["type"] for e in events)
    gates = [e for e in events if e["type"] == "gate_recorded"]
    run_tasks = [t for t in tasks if t["start"]]
    names = region_names()
    batch = art_dir(d, "A0038")
    bp = payload(d, "A0038")
    full = bp["results"]["full"]
    eff = full["effects"]
    derived = full["derived"]
    runs = json.loads((batch / "full_runs.json").read_text())
    med = full["median_sample"]["id"]
    seiz = {}
    for r in runs["baselines"] + runs["candidates"]:
        if r.get("sample_id") == med:
            seiz[r["candidate_id"]] = r["seizures"]["seizing_regions"]
    ablated = next(c for c in json.loads((batch / "full_candidates.json").read_text())["candidates"]
                   if c["id"] == "RES-EZ+PZ/ablation")["regions"]
    outcome = next((a for a in sorted(arts) if arts[a]["schema_name"] == "OutcomeEvaluation" and not arts[a]["stale"]), None)
    oe = payload(d, outcome) if outcome else None
    status = next((e["status"] for e in reversed(events) if e["type"] == "study_status"), "open")
    fig = iter(range(1, 60))

    # ---------------------------------------------------------------- 3D: patient cortex + contacts
    zc = zipfile.ZipFile(ANA / "tvb/Cortex_pial_ico5.zip")
    v = np.loadtxt(io.BytesIO(zc.read("vertices.txt")), dtype=np.float32)
    f = np.loadtxt(io.BytesIO(zc.read("triangles.txt")), dtype=np.int64)
    rm = np.loadtxt(ANA / "tvb/region_map_ico5.txt").astype(int) - 1
    con = [l.split() for l in open(ANA / "elec/seeg.xyz") if l.strip()]
    cxyz = np.array([[float(a) for a in l[1:4]] for l in con], dtype=np.float32)
    cname = [l[0] for l in con]
    stim = derived.get("stim1_contact_name", "")
    stim_contacts = [i for i, n in enumerate(cname) if n in _bipolar_pair(stim)]

    def per_vertex(reg_vals):
        vals = np.zeros(len(rm), dtype=np.float32)
        ok = rm >= 0
        vals[ok] = np.asarray(reg_vals, dtype=np.float32)[rm[ok]]
        return vals
    ez_freq = np.zeros(162)
    for i in derived.get("ez_set", []):
        ez_freq[i] = 1.0
    abl = np.zeros(162)
    abl[ablated] = 1.0
    base_seiz = np.zeros(162)
    base_seiz[seiz.get("BASELINE", seiz.get("baseline", []))] = 1.0
    after_seiz = np.zeros(162)
    after_seiz[seiz.get("RES-EZ+PZ/ablation", [])] = 1.0
    overlays = [
        {"name": "Ablation target: estimated EZ + PZ (RES-EZ+PZ)", "values": per_vertex(abl), "unit": "(1 = removed)", "cmap": "seq"},
        {"name": "Before: regions seizing at baseline (median sample)", "values": per_vertex(base_seiz), "unit": "(1 = seizes)", "cmap": "seq"},
        {"name": "After ablation: regions still seizing (median sample)", "values": per_vertex(after_seiz), "unit": "(1 = seizes)", "cmap": "seq"},
        {"name": "Atlas regions (region index)", "values": per_vertex(np.arange(162) % 7 + 1), "unit": "", "cmap": "seq"},
    ]
    pts = [{"xyz": cxyz, "color": "--neutral", "label": f"SEEG contacts ({len(cxyz)})", "size": 3}]
    if stim_contacts:
        pts.append({"xyz": cxyz[stim_contacts], "color": "--s2", "label": f"stimulating pair {stim}", "size": 6})
    brain_patient = brain3d.brain_viewer_html(overlays, "brainP", height=480, mesh=(v, f), points=pts)
    brain_ti = brain3d.brain_viewer_html(brain3d.ti_overlays(str(EMF)), "brainTI", height=420)

    # ---------------------------------------------------------------- page
    H = []
    H.append(f"""<header class="top"><button class="themebtn" type="button">Light / dark</button>
<div class="who">ScienceClaw epilepsy research system · study summary</div>
<h1>Virtual brain twins for treatment choice: study-002</h1>
<p class="lead">{E(st['study']['question'])}</p>
<div class="meta"><span>Study <code>{STUDY}</code></span><span>Release <code>{E(st['study']['system_release_id'])}</code></span>
<span>Protocol v1 (A0001) + amendments A0012, A0015</span><span>Run {t0:%Y-%m-%d %H:%M} – {t1:%H:%M} UTC</span>
<span>Status: {sr.badge('done' if status == 'completed' else 'unreviewed', status)}</span></div>
<div class="warn"><b>Exploratory results on a virtual patient.</b> The inversion model did not pass its qualification benchmark (v2 A0037, v3 A0040), so the onset-zone estimates and the treatment ranking below are exploratory. Nothing here is a clinical recommendation.</div>
<nav class="toc"><a href="#summary">1 Summary</a><a href="#workflow">2 Workflow & agents</a><a href="#data">3 Data & blinding</a><a href="#modeling">4 Modeling</a>
<a href="#simulation">5 Simulation</a><a href="#truth">6 Truth check</a><a href="#quality">7 Quality & limits</a><a href="#appendix">Appendix</a></nav></header>""")

    best = min(eff, key=lambda k: eff[k]["d_n_seizing_regions"]["median"])
    H.append(f"""<h2 id="summary">1 · Summary</h2>
<div class="tiles">
<div class="tile"><div class="v">{len(run_tasks)}</div><div class="k">agent tasks run ({ev['task_refused']} refused at admission)</div></div>
<div class="tile"><div class="v">{len(arts)}</div><div class="k">artifacts committed</div></div>
<div class="tile"><div class="v">{len(gates)}</div><div class="k">gate decisions</div></div>
<div class="tile"><div class="v">{sr.fmt_dur((t1 - t0).total_seconds())}</div><div class="k">wall clock (local 22 cores + GCP VM 32 vCPU)</div></div>
<div class="tile"><div class="v">{full['n_samples'] if 'n_samples' in full else 12}</div><div class="k">model samples simulated × {len(eff)} treatment arms</div></div>
<div class="tile"><div class="v">{ev['vault_sealed']}</div><div class="k">files sealed in the vault before modeling</div></div></div>
<div class="cols"><div class="card"><h3>For clinicians</h3><ul>
<li>We built a virtual brain twin of Wang et al.'s virtual Patient 2 (162-region connectome, 205 SEEG contacts) and tested resection/ablation and electrical stimulation <i>in silico</i> before any (virtual) intervention.</li>
<li>Exploratory result: removing the model's estimated onset + spread regions reduced the number of seizing regions most (median {eff[best]['d_n_seizing_regions']['median']:+g}; all seizures stopped in {eff[best]['frac_abolish_all']:.0%} of model samples). Sustained-current SEEG stimulation helped a little; the paper's 50 Hz pulse train did not.</li>
<li>{('<b>Against the sealed ground truth the model failed:</b> the true onset region (' + E(', '.join(oe['metrics']['ground_truth_summary']['true_ez_names'])) + ') was not among the estimated regions, and the treatment ranking could not be confirmed. The value shown here is the honest negative result and a clear path to fix it.') if oe else 'The ground-truth check (R5) is pending.'}</li></ul></div>
<div class="card"><h3>For engineers</h3><ul>
<li>Seven agent roles worked through a deterministic controller: every task admitted against a frozen profile, every artifact gated by another role, truth sealed in a vault until predictions were frozen (freeze hash <code>1fcf288a…</code>).</li>
<li>Two inversion models were tried and both failed qualification: v2 (≈520 parameters, R-hat up to 4.7) and v3 (68 parameters, Pathfinder modes spread ≈50 nats). Root cause: the 2D fitting model cannot reproduce data generated by the richer 6D model.</li>
<li>Treatments were simulated with the paper's full TVB SpatEpiStim model (reproduces the package bit for bit), on the GCP VM and locally, with paired baselines.</li></ul></div></div>""")

    # workflow
    roles_used = [r for r in sr.ROLE_ORDER if any(t["role"] == r for t in tasks)]
    H.append(f"""<h2 id="workflow">2 · Workflow and agent history</h2>
<p>Same controller-governed workflow as study-001, run on the release that includes study-001's lessons (benchmark-first modeling, sealed outcome files, larger budgets). Two protocol amendments were approved by the user: cloud compute (A0012) and a parallel schedule to meet a noon deadline (A0015).</p>
{sr.figure(next(fig), "Who worked on what, when", sr.fig_gantt(tasks, t0, t1), "One bar per task, coloured by role; hover for objective, duration and result.", sr.legend_html([(sr.ROLE_SHORT[r] + ' ' + sr.ROLE_NAME[r], sr.ROLE_VAR[r], '') for r in roles_used]))}
{sr.figure(next(fig), "Artifacts per role by gate verdict", sr.fig_gate_bars(st), "Latest gate per artifact. Failed benchmark ModelBundles are the qualification results themselves.", sr.legend_html([('passed', 'var(--good)', ''), ('failed', 'var(--critical)', ''), ('indeterminate', 'var(--warning)', ''), ('unreviewed', 'var(--neutral)', '')]))}""")
    trows = [[f"<code>{t['id']}</code>", sr.ROLE_SHORT[t['role']], E(t['type']), E(t['case'] or '–'),
              t['start'].strftime('%H:%M') if t['start'] else '–',
              sr.fmt_dur((t['end'] - t['start']).total_seconds()) if t['start'] and t['end'] else '–',
              sr.badge(t['state'] if t['state'] in ('succeeded', 'refused', 'abstained', 'failed') else 'unreviewed', t['state']),
              E(t['objective'][:200])] for t in tasks]
    H.append("<details><summary>Full task log</summary>" + sr.table(["Task", "Role", "Type", "Case", "Start", "Duration", "Result", "Objective"], trows, raw_cols=(0, 6)) + "</details>")

    # data
    H.append(f"""<h2 id="data">3 · Data and blinding</h2>
{sr.table(["Source", "Content", "Use", "Licence", "Record"], [
        ["GitHub HuifangWang/VBT_INS_Stimulation @5367ef4", "Simulated SEEG/EEG for virtual Patients 1 and 2 (SC 162×162, gain), TI field maps", "P1 = development/benchmark, P2 = blinded test", "Apache-2.0", "A0002, A0004"],
        ["Code Ocean CO.2143670.v1 (Part 2)", "Patient 2 anatomy: cortex (20,484 vertices), region map, 205 SEEG contacts, neural-field gain", "3D model, stimulation geometry", "CC BY-NC", "data/wang-co2-ana (manifest)"],
        ["Authors' simulation notebooks + posterior spreadsheets", "Patient 2 generating configuration (ground truth)", "Sealed (V001–V010) before modeling; revealed only to R5 after the prediction freeze", "—", "vault"]])}""")

    # modeling
    H.append(f"""<h2 id="modeling">4 · Virtual-brain modeling</h2>
<p>Strategy (as in Wang et al. 2025): infer each region's excitability <i>x0</i> with a reduced 2D Epileptor network in Stan, then simulate treatments with the full stimulation model in TVB. A pipeline must first recover a planted onset zone on synthetic data (benchmark) before its patient estimates count.</p>
{sr.table(["Model", "Parameters", "Benchmark result", "Record"], [
        ["v2 (AR(1) likelihood, data-centred priors)", "≈520", "Planted EZ ranked 2nd (P(rank 1) 0.026); x0 R-hat up to 4.73; 7 false positives; 24 optimizer runs → 24 different optima — NOT QUALIFIED", "A0014, A0037"],
        ["v3 (40 visible regions, offsets marginalised, 24 PCs, Pathfinder + dense NUTS)", "68", "Planted EZ not recovered (P(rank 1) 0.012); NUTS did not finish warm-up in 45 min — NOT QUALIFIED", "A0039, A0040"],
        ["Patient 2 fits with v2 (exploratory, frozen)", "≈520", "MAP ensemble (24 starts × 2 windows) and NUTS (R-hat up to ≈3.3, not converged); most consistent hypothesis: left dorsolateral prefrontal", "A0017, A0018, A0019"]])}""")

    # simulation
    lbl = {"RES-EZ+PZ/ablation": "Ablate est. EZ + PZ", "RES-EZ/ablation": "Ablate est. EZ", "RES-1/ablation": "Ablate top-1 region",
           "RES-EZ+PZ/disconnection": "Disconnect EZ + PZ", "RES-EZ/disconnection": "Disconnect EZ", "RES-1/disconnection": "Disconnect top-1",
           "STIM-1/amp2": "Sustained current, best contact, ×2", "STIM-1/amp1": "Sustained current, best contact, ×1",
           "STIM-1/amp0.5": "Sustained current, best contact, ×0.5", "STIM-2/amp1": "Sustained current, two contacts",
           "STIM-PT/amp0.5": "50 Hz pulse train 3 s, ×0.5", "STIM-PT/amp1": "50 Hz pulse train 3 s, ×1",
           "STIM-PT-chronic/amp0.5": "50 Hz pulse train chronic, ×0.5", "STIM-PT-chronic/amp1": "50 Hz pulse train chronic, ×1"}
    order = list(lbl)
    H.append(f"""<h2 id="simulation">5 · Simulation: virtual brain, stimulation and treatments</h2>
<p>R4 simulated every prespecified candidate on each of the 12 best full-window MAP solutions with a paired no-treatment baseline (TVB SpatEpiStim, 0.05 ms steps, 14.4 s horizon). Stimulation follows the paper: a bipolar SEEG contact pair, 50 Hz biphasic pulses, spatial weights from that contact's gain. The detailed R4 report is <a href="study-002-R4-simulations.html">study-002-R4-simulations.html</a>.</p>
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> The virtual patient in 3D: cortex, SEEG implant and treatment targets</figcaption>
{brain_patient}
<p class="fig-cap">Patient 2's own cortex (Code Ocean anatomy, 20,484 vertices) with all {len(cxyz)} SEEG contacts{(' and the stimulating pair ' + E(stim) + ' highlighted') if stim_contacts else ''}. Overlays paint atlas regions: the ablation target set chosen from the (unqualified) onset estimate, and the regions seizing before and after ablation in the median model sample. Region-level model: colours mark whole regions, not tissue extents.</p></figure>
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Temporal-interference stimulation field (Wang et al. EMF maps)</figcaption>
{brain_ti}
<p class="fig-cap">Two 1000/1005 Hz field pairs beat at 5 Hz; the modulation depth 2·min(|E1|,|E2|) marks where TI stimulation acts. Shown on the fsaverage5 template the maps are defined on. TI was not simulated in the network model (no surface-to-region mapping at design time; need N001).</p></figure>
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Before and after treatment: region activity and simulated SEEG (median model sample)</figcaption>
<img alt="Before/after simulated region activity and SEEG for baseline, ablation, sustained-current and pulse-train stimulation" style="width:100%;border-radius:8px" src="data:image/png;base64,{before_after_png(batch, names)}">
<p class="fig-cap">Top: activity of the 18 most active regions (yellow = seizure state). Bottom: six most active SEEG channels on a common scale. Ablation silences most of the seizing network; sustained-current stimulation changes little; the 3 s pulse train does not stop the seizures.</p></figure>
{sr.figure(next(fig), "Effect of each treatment: change in seizing regions vs paired baseline", forest_svg(eff, order, lbl), "Median (dot) and 5–95% range over the 12 model samples; right column: share of samples in which all seizures stopped. High-amplitude pulse-train arms failed numerically and are excluded. Exploratory: the model is not qualified.")}""")

    # truth
    if oe:
        m = oe["metrics"]
        gt = m["ground_truth_summary"]
        rec = m["ez_recovery"]["per_source_window"]
        lab = {"A0018-ModelBundle:post": "MAP ensemble · post-stimulation window", "A0018-ModelBundle:full": "MAP ensemble · full window",
               "A0019-ModelBundle:post": "NUTS (not converged) · post window", "A0019-ModelBundle:full": "NUTS (not converged) · full window"}
        rrows = []
        for k, r in rec.items():
            te = r["true_ez"][0]
            rrows.append([lab.get(k, k), len(r["est_ez_set"]), "—" if r["precision"] is None else f"{r['precision']:.2f}",
                          f"{r['recall']:.2f}", names[r["top1"]] if isinstance(r["top1"], int) else r.get("top1_name", ""),
                          f"{te['rank_by_median_x0']:.0f} / 162", f"{te['freq_x0_gt_thr']:.2f}"])
        tr = m.get("treatment_ranking", {})
        tr_txt = json.dumps(tr)[:1200]
        truth_v = np.zeros(162)
        est = rec.get("A0019-ModelBundle:full", {}).get("est_ez_set", [])
        truth_v[est] = 0.5
        truth_v[gt["true_ez_npz_cols"]] = 1.0
        brain_truth = brain3d.brain_viewer_html(
            [{"name": "True EZ (1.0, revealed after freeze) vs estimated EZ set, NUTS full window (0.5)", "values": per_vertex(truth_v), "unit": "", "cmap": "seq"}],
            "brainT", height=420, mesh=(v, f), points=pts[:1])
        H.append(f"""<h2 id="truth">6 · Ground-truth check (R5, after the prediction freeze)</h2>
<p>R5 opened the sealed configuration only after the predictions were frozen (freeze before reveal in the ledger), scored the frozen onset estimates, and re-ran R4's planned treatments plus an oracle (ablating the true onset zone) on the true virtual patient. Records: <code>{outcome}</code>, A0044. <b>Verdict: failed.</b></p>
<div class="cols"><div class="card"><h3>True onset zone</h3><p><b>{E(', '.join(gt['true_ez_names']))}</b> (a single region; no propagation zone set). None of the four frozen estimates contained it (recall 0); the most frequent estimate was Right orbito-frontal cortex, the region with the strongest SEEG coverage.</p></div>
<div class="card"><h3>Treatment ranking</h3><p>On the true model in the region-level simulator the patient did not seize spontaneously, so no candidate, not even ablating the true onset zone, could show an effect. Rank concordance is undefined; in the full window all 9 predicted reductions had the wrong sign. The recorded seizure was stimulation-induced, so the next check is to simulate the observed stimulation protocol.</p></div></div>
{sr.table(["Estimate", "Regions flagged", "Precision", "Recall", "Top region", "True EZ rank (median x0)", "Share x0 > −2.06"], rrows)}
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Truth vs estimate on the patient's cortex</figcaption>{brain_truth}
<p class="fig-cap">Full colour: the true onset region; half colour: regions the (unconverged) NUTS fit flagged in the full window. They do not overlap.</p></figure>
<details><summary>Raw treatment-ranking metrics (A0043)</summary><pre style="white-space:pre-wrap;font-size:12px">{E(tr_txt)}</pre></details>""")
    else:
        H.append('<h2 id="truth">6 · Ground-truth check</h2><p>Pending: R5 has not committed the OutcomeEvaluation yet.</p>')

    # quality
    needs = st["needs"]
    H.append(f"""<h2 id="quality">7 · Quality controls and limitations</h2>
<div class="cols"><div class="card"><h3>Controls</h3><ul>
<li>Ground truth and the authors' notebooks/posteriors sealed ({ev['vault_sealed']} items) before modeling; revealed once, to R5, after the freeze.</li>
<li>Every model frozen with hashes before its benchmark; failures reported, not tuned away.</li>
<li>{ev['repair_issued']} repairs; {ev['task_refused']} proposals refused by the controller.</li></ul></div>
<div class="card"><h3>Limitations</h3><ul>
<li>No qualified inversion model: onset estimates and treatment ranking are exploratory.</li>
<li>Region-level (not neural-field) simulation; 12 of 24 samples in the full window; post window uninformative (no baseline seizures).</li>
<li>Simulated top channels did not match the recording's (qualitative check failed).</li>
<li>Virtual patients from one study family; not a clinical result.</li></ul></div></div>
{sr.table(["Need", "Raised by", "Missing", "State"], [[n, needs[n]['requester'].split('-')[0], needs[n]['missing_input'][:200], sr.badge(needs[n]['state'] if needs[n]['state'] in ('open', 'fulfilled') else 'unreviewed', needs[n]['state'])] for n in sorted(needs)], raw_cols=(3,))}""")

    man = [[a.split("-")[0], arts[a]["schema_name"], arts[a]["producer_role"].split("-")[0], arts[a].get("case_id") or "–",
            sr.badge("stale" if arts[a]["stale"] else arts[a]["effective_validation"], arts[a]["effective_validation"]),
            E((arts[a].get("title") or "")[:120]), f"<code>{arts[a]['manifest_hash'][:12]}</code>"] for a in sorted(arts)]
    H.append(f"""<h2 id="appendix">Appendix · Reproducibility</h2>
<ul><li>Release <code>{E(st['study']['system_release_id'])}</code>; models: v2 <code>f15d0a54…</code>, v3 <code>7c3545e2…</code>; simulator p2sim <code>0c6f3923…</code>; spec v2 <code>70ee917c…</code>; prediction freeze <code>1fcf288a…</code>.</li>
<li>Compute: local 22 cores + GCP VM scienceclaw-swarm (n2-standard-32), pinned CmdStan 2.40, tvb-library 2.10.0, vep-stim @5367ef4.</li></ul>
<details><summary>All {len(arts)} artifacts</summary>{sr.table(["Id", "Schema", "Producer", "Case", "Verdict", "Title", "Hash"], man, raw_cols=(4, 5, 6))}</details>""")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Study-002 Summary Report</title><style>{sr.CSS}{brain3d.BRAIN_CSS}:root{{--brain:#d6d3cb;--seq-lo:#f6dcc8}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme="light"])){{--brain:#5a5853;--seq-lo:#6b4a36}}}}:root[data-theme="dark"]{{--brain:#5a5853;--seq-lo:#6b4a36}}</style></head>
<body><div class="wrap">{"".join(H)}</div><div id="tip" role="tooltip"></div><script>{sr.JS}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def _bipolar_pair(name):
    """'TP1-2' -> ['TP1', 'TP2']."""
    import re
    m = re.match(r"([A-Za-z']+)(\d+)-(\d+)$", name or "")
    return [m.group(1) + m.group(2), m.group(1) + m.group(3)] if m else []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "study-002-summary.html"))
    print(build(Path(ap.parse_args().out)))
