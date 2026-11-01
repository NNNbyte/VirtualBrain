"""Build a self-contained HTML summary report for a study (workflow, agent history, results, figures).

    python system/reports/study_report.py --study study-001 --out reports/study-001-summary.html

Reads only the ledger, committed artifacts and agent work files. Never reads studies/*/vault/.
"""
import argparse
import csv
import datetime as dt
import html
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "system"))
import controller as ctl  # noqa: E402

E = html.escape

# Role identity: fixed categorical order (reference palette slots 1-8).
ROLE_ORDER = ["LEAD-study-lead", "R1-evidence-scout", "R2-case-curation", "R3-virtual-patient",
              "R4-intervention-design", "R5-independent-evaluation", "RV-clinical-engineering-review",
              "R6-improvement-research"]
ROLE_SHORT = {r: r.split("-")[0] for r in ROLE_ORDER}
ROLE_VAR = {r: f"var(--s{i + 1})" for i, r in enumerate(ROLE_ORDER)}
ROLE_NAME = {"LEAD-study-lead": "Lead orchestrator", "R1-evidence-scout": "Evidence & dataset scout",
             "R2-case-curation": "Case curation", "R3-virtual-patient": "Virtual patient",
             "R4-intervention-design": "Intervention design", "R5-independent-evaluation": "Independent evaluation",
             "RV-clinical-engineering-review": "Clinical & engineering review",
             "R6-improvement-research": "Improvement research"}


def ts(s):
    return dt.datetime.fromisoformat(s)


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt_dur(sec):
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} s"
    m = sec // 60
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


# --------------------------------------------------------------------------- SVG helpers
class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.parts = w, h, []
        self.label = label

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, cls="t", anchor="start", extra=""):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{E(str(s))}</text>')

    def line(self, x1, y1, x2, y2, cls="grid"):
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"/>')

    def render(self):
        return (f'<svg viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{E(self.label)}" '
                f'preserveAspectRatio="xMinYMin meet">' + "".join(self.parts) + "</svg>")


def tip(s):
    return f'data-tip="{E(s)}"'


def nice_ticks(lo, hi, n=5):
    span = hi - lo
    raw = span / n
    mag = 10 ** int(f"{raw:e}".split("e")[1])
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    t = (int(lo / step)) * step
    out = []
    while t <= hi + 1e-9:
        if t >= lo - 1e-9:
            out.append(round(t, 10))
        t += step
    return out


def figure(num, title, svg_html, caption, legend=""):
    return (f'<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {num}</span> {E(title)}'
            f'</figcaption>{legend}<div class="chart">{svg_html}</div><p class="fig-cap">{caption}</p></figure>')


def legend_html(items):
    return '<div class="legend">' + "".join(
        f'<span class="lg"><span class="sw {shape}" style="background:{col}"></span>{E(lbl)}</span>'
        for lbl, col, shape in items) + "</div>"


def table(headers, rows, cls="", raw_cols=()):
    h = "".join(f"<th>{E(x)}</th>" for x in headers)
    body = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            cells.append(f"<td>{c if i in raw_cols else E(str(c))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def badge(kind, text=None):
    icons = {"passed": "✓", "failed": "✕", "indeterminate": "?", "unreviewed": "·", "succeeded": "✓",
             "abstained": "–", "refused": "✕", "open": "○", "fulfilled": "✓", "done": "✓", "skipped": "–",
             "not_qualified": "✕", "stale": "↻"}
    return f'<span class="badge b-{kind}">{icons.get(kind, "")} {E(text or kind.replace("_", " "))}</span>'


# --------------------------------------------------------------------------- data
def load(study):
    d = ctl.study_dir(study)
    st = ctl.load_state(d)
    events = [json.loads(x) for x in (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return d, st, events


def task_rows(events):
    tasks, order = {}, []
    for e in events:
        t = e["type"]
        if t == "task_proposed":
            tk = e["task"]
            tasks[tk["task_id"]] = {"id": tk["task_id"], "role": tk["assigned_role"], "type": tk["task_type"],
                                    "objective": tk["objective"], "stage": tk["stage"], "case": tk.get("case_id"),
                                    "proposed": ts(e["ts"]), "start": None, "end": None, "state": "proposed",
                                    "summary": "", "outputs": [], "progress": 0}
            order.append(tk["task_id"])
        elif t == "task_refused":
            tasks[e["task_id"]]["state"] = "refused"
            tasks[e["task_id"]]["summary"] = "; ".join(e["reasons"])
        elif t == "task_started" and e["task_id"] in tasks:
            tasks[e["task_id"]]["start"] = ts(e["ts"])
        elif t == "task_finished" and e["task_id"] in tasks:
            tasks[e["task_id"]].update(end=ts(e["ts"]), state=e["status"], summary=e.get("summary", ""))
        elif t == "task_progress" and e["task_id"] in tasks:
            tasks[e["task_id"]]["progress"] += 1
        elif t == "artifact_committed":
            env = e["envelope"]
            if env["task_id"] in tasks:
                tasks[env["task_id"]]["outputs"].append(env["artifact_id"])
    return [tasks[i] for i in order]


# --------------------------------------------------------------------------- figures
def fig_workflow():
    phases = [("P0", "Protocol", "LEAD", "done", "Protocol v1 drafted and approved by the user"),
              ("P1", "Discovery", "R1 · R5", "done", "30 evidence claims, 9 dataset cards, 3 method cards, all source-checked"),
              ("P2", "Case curation", "R2 · R5", "done", "56 eligible, 34/22 split, 10 cases curated and re-verified"),
              ("P3", "Virtual patient", "R3 · R5", "failed", "2 pipeline benchmarks failed; R5: not qualified"),
              ("P4", "Intervention design", "R4", "skipped", "Not run: no qualified model"),
              ("P5", "Evaluation", "R5", "skipped", "Not run: predictions never frozen, vault never opened"),
              ("P6", "Dossier", "LEAD", "done", "DecisionBundle + report, revised once"),
              ("P7", "Review", "RV", "done", "Revision requested, then accepted (1 repair cycle)"),
              ("P8", "Improvement", "R6", "skipped", "R6 disabled in frozen release; lessons applied to next release")]
    w, bw, bh, gap = 1080, 108, 92, 9
    s = Svg(w, 150, "Workflow phases P0 to P8 with their status")
    for i, (pid, name, roles, status, note) in enumerate(phases):
        x = 6 + i * (bw + gap)
        cls = {"done": "ph-done", "failed": "ph-fail", "skipped": "ph-skip"}[status]
        s.add(f'<g {tip(f"{pid} · {name} ({roles}): {note}")}><rect x="{x}" y="20" width="{bw}" height="{bh}" rx="8" class="{cls}"/>')
        s.text(x + 10, 42, pid, "t-strong")
        s.text(x + 10, 62, name, "t-small")
        s.text(x + 10, 80, roles, "t-muted")
        lab = {"done": "✓ done", "failed": "✕ not qualified", "skipped": "– not run"}[status]
        s.text(x + 10, 101, lab, "t-small t-" + status)
        s.add("</g>")
        if i < len(phases) - 1:
            ax = x + bw + 1
            s.add(f'<path d="M{ax} 66 l{gap - 3} 0" class="arrow"/>')
    s.text(6, 140, "Hover a phase for its result. Gates between phases are recorded by an evaluator other than the producer.", "t-muted")
    return s.render()


def fig_gantt(tasks, t0, t1):
    run = [t for t in tasks if t["start"] and t["end"]]
    roles = [r for r in ROLE_ORDER if any(t["role"] == r for t in run)]
    lane_h, left, top, w = 34, 190, 28, 1080
    h = top + lane_h * len(roles) + 46
    span = (t1 - t0).total_seconds()
    X = lambda t: left + (t - t0).total_seconds() / span * (w - left - 16)
    s = Svg(w, h, "Gantt chart of agent tasks over time, one lane per agent role")
    # hour grid
    hr = t0.replace(minute=0, second=0, microsecond=0)
    while hr <= t1:
        if hr >= t0:
            x = X(hr)
            s.line(x, top - 6, x, top + lane_h * len(roles), "grid")
            s.text(x, top + lane_h * len(roles) + 18, hr.strftime("%H:%M") + " UTC", "t-muted", "middle")
        hr += dt.timedelta(hours=1)
    for li, r in enumerate(roles):
        y = top + li * lane_h
        s.text(left - 12, y + lane_h / 2 + 4, f"{ROLE_SHORT[r]} · {ROLE_NAME[r]}", "t-small", "end")
        s.line(left, y + lane_h, w - 16, y + lane_h, "grid-faint")
        lane = sorted([t for t in run if t["role"] == r], key=lambda t: t["start"])
        # stack overlapping tasks in sub-rows
        rows_end = []
        for t in lane:
            k = next((i for i, e in enumerate(rows_end) if e <= t["start"]), None)
            if k is None:
                k = len(rows_end)
                rows_end.append(t["end"])
            else:
                rows_end[k] = t["end"]
            t["_sub"] = k
        nsub = max(1, len(rows_end))
        sub_h = (lane_h - 8) / nsub
        for t in lane:
            x1, x2 = X(t["start"]), X(t["end"])
            yy = y + 4 + t["_sub"] * sub_h
            dur = (t["end"] - t["start"]).total_seconds()
            label = (f'{t["id"]} · {t["type"]} ({ROLE_SHORT[r]}) · {fmt_dur(dur)} · {t["state"]}'
                     f' · outputs {len(t["outputs"])} · {t["objective"][:150]}')
            s.add(f'<rect x="{x1:.1f}" y="{yy:.1f}" width="{max(3, x2 - x1):.1f}" height="{max(3, sub_h - 2):.1f}" '
                  f'rx="2" fill="{ROLE_VAR[r]}" class="mark" {tip(label)}/>')
            if x2 - x1 > 56 and sub_h >= 12:
                s.text(x1 + 4, yy + sub_h / 2 + 3, t["id"], "t-onbar")
    return s.render()


def fig_gate_bars(st):
    per = defaultdict(Counter)
    for a in st["artifacts"].values():
        per[a["producer_role"]][a["effective_validation"]] += 1
    roles = [r for r in ROLE_ORDER if r in per]
    cats = [("passed", "var(--good)"), ("failed", "var(--critical)"), ("indeterminate", "var(--warning)"),
            ("unreviewed", "var(--neutral)")]
    left, top, bar_h, gap, w = 190, 10, 22, 12, 1080
    mx = max(sum(per[r].values()) for r in roles)
    h = top + len(roles) * (bar_h + gap) + 30
    s = Svg(w, h, "Artifacts committed per role by gate verdict")
    X = lambda v: left + v / mx * (w - left - 60)
    for tk in nice_ticks(0, mx, 6):
        s.line(X(tk), top - 4, X(tk), h - 26, "grid")
        s.text(X(tk), h - 10, int(tk), "t-muted", "middle")
    for i, r in enumerate(roles):
        y = top + i * (bar_h + gap)
        s.text(left - 12, y + bar_h / 2 + 4, f"{ROLE_SHORT[r]} · {ROLE_NAME[r]}", "t-small", "end")
        acc = 0
        for c, col in cats:
            n = per[r][c]
            if not n:
                continue
            x1, x2 = X(acc), X(acc + n)
            s.add(f'<rect x="{x1 + 1:.1f}" y="{y}" width="{max(1, x2 - x1 - 2):.1f}" height="{bar_h}" rx="3" '
                  f'fill="{col}" class="mark" {tip(f"{ROLE_SHORT[r]}: {n} {c}")}/>')
            acc += n
        s.text(X(acc) + 6, y + bar_h / 2 + 4, sum(per[r].values()), "t-small")
    return s.render()


def fig_range(rows, title_label, lo_max=100):
    """rows: (label, lo, hi, color var, refs, note). Horizontal range bars on a 0-100 % axis."""
    left, top, rh, w = 280, 10, 30, 1080
    h = top + len(rows) * rh + 34
    s = Svg(w, h, title_label)
    X = lambda v: left + v / lo_max * (w - left - 40)
    for tk in range(0, lo_max + 1, 10):
        s.line(X(tk), top - 4, X(tk), h - 28, "grid")
        s.text(X(tk), h - 12, f"{tk}%", "t-muted", "middle")
    for i, (lab, lo, hi, col, refs, note) in enumerate(rows):
        y = top + i * rh + rh / 2
        s.text(left - 12, y + 4, lab, "t-small", "end")
        t = f"{lab}: {lo:g}–{hi:g}% · {note} · {refs}" if hi != lo else f"{lab}: {lo:g}% · {note} · {refs}"
        g = f'<g class="mark" {tip(t)}>'
        if hi != lo:
            g += f'<rect x="{X(lo):.1f}" y="{y - 5:.1f}" width="{X(hi) - X(lo):.1f}" height="10" rx="5" fill="{col}" opacity="0.35"/>'
        g += f'<circle cx="{X(lo):.1f}" cy="{y:.1f}" r="5.5" fill="{col}" class="ring"/>'
        if hi != lo:
            g += f'<circle cx="{X(hi):.1f}" cy="{y:.1f}" r="5.5" fill="{col}" class="ring"/>'
        g += f'<rect x="{left}" y="{y - rh / 2:.1f}" width="{w - left}" height="{rh}" fill="transparent"/></g>'
        s.add(g)
        s.text(X(hi) + 10, y + 4, f"{lo:g}–{hi:g}%" if hi != lo else f"{lo:g}%", "t-small")
    return s.render()


def fig_cases(cases):
    left, top, bh, gap, w = 150, 10, 20, 10, 1080
    mx = max(c["n_soz"] for c in cases)
    h = top + len(cases) * (bh + gap) + 30
    s = Svg(w, h, "Seizure-onset contacts per case, split into resected and not resected")
    X = lambda v: left + v / mx * (w - left - 220)
    for tk in nice_ticks(0, mx, 7):
        s.line(X(tk), top - 4, X(tk), h - 26, "grid")
        s.text(X(tk), h - 10, int(tk), "t-muted", "middle")
    for i, c in enumerate(cases):
        y = top + i * (bh + gap)
        s.text(left - 12, y + bh / 2 + 4, f'{c["case"]} ({c["split"]})', "t-small", "end")
        a, b = c["n_soz_res"], c["n_soz"] - c["n_soz_res"]
        cid, ns = c["case"], c["n_soz"]
        if a:
            s.add(f'<rect x="{X(0) + 1:.1f}" y="{y}" width="{X(a) - X(0) - 2:.1f}" height="{bh}" rx="3" fill="var(--s1)" class="mark" '
                  + tip(f"{cid}: {a} of {ns} seizure-onset contacts inside the resection/ablation zone") + "/>")
        if b:
            s.add(f'<rect x="{X(a) + 1:.1f}" y="{y}" width="{X(a + b) - X(a) - 2:.1f}" height="{bh}" rx="3" fill="var(--s2)" class="mark" '
                  + tip(f"{cid}: {b} of {ns} seizure-onset contacts outside the resection/ablation zone") + "/>")
        s.text(X(a + b) + 8, y + bh / 2 + 4, f'{a}/{c["n_soz"]} resected · {c["implant"]} · {c["n_ictal"]} seizures', "t-muted")
    return s.render()


def fig_rhat(diags):
    left, top, lane, w = 260, 12, 70, 1080
    hi = max(max(d["rhat"]) for d in diags) * 1.05
    h = top + lane * len(diags) + 36
    s = Svg(w, h, "R-hat of each region's excitability x0 in the three benchmark fits")
    X = lambda v: left + (v - 1.0) / (hi - 1.0) * (w - left - 30)
    for tk in nice_ticks(1.0, hi, 7):
        s.line(X(tk), top - 4, X(tk), h - 28, "grid")
        s.text(X(tk), h - 12, f"{tk:g}", "t-muted", "middle")
    s.line(X(1.05), top - 6, X(1.05), h - 28, "thresh")
    s.text(X(1.05) + 5, top + 4, "1.05 pass threshold", "t-small t-critical")
    rnd = random.Random(7)
    for i, d in enumerate(diags):
        y0 = top + i * lane
        s.text(left - 12, y0 + lane / 2, d["label"], "t-small", "end")
        s.text(left - 12, y0 + lane / 2 + 15, f'{d["n_bad"]}/162 fail · max {max(d["rhat"]):.2f}', "t-muted", "end")
        for reg, r in zip(d["regions"], d["rhat"]):
            yy = y0 + 12 + rnd.random() * (lane - 24)
            col = "var(--s2)" if r > 1.05 else "var(--s1)"
            s.add(f'<circle cx="{X(r):.1f}" cy="{yy:.1f}" r="4" fill="{col}" class="mark ring" {tip(f"{reg}: R-hat {r:.3f}")}/>')
        s.line(left, y0 + lane, w - 30, y0 + lane, "grid-faint")
    return s.render()


def fig_truth_scatter(rows, label, ez, pz):
    w, h, l, r, t, b = 520, 400, 58, 16, 14, 46
    xs = [float(x["true_x0"]) for x in rows]
    ys = [float(x["post_mean"]) for x in rows]
    lo, hi = min(xs + ys) - 0.1, max(xs + ys) + 0.1
    X = lambda v: l + (v - lo) / (hi - lo) * (w - l - r)
    Y = lambda v: h - b - (v - lo) / (hi - lo) * (h - t - b)
    s = Svg(w, h, f"{label}: true versus estimated x0 per region")
    for tk in nice_ticks(lo, hi, 6):
        s.line(X(tk), t, X(tk), h - b, "grid")
        s.line(l, Y(tk), w - r, Y(tk), "grid")
        s.text(X(tk), h - b + 16, f"{tk:g}", "t-muted", "middle")
        s.text(l - 6, Y(tk) + 4, f"{tk:g}", "t-muted", "end")
    s.line(X(lo), Y(lo), X(hi), Y(hi), "diag")
    s.line(l, Y(-2.05), w - r, Y(-2.05), "thresh")
    s.text(w - r - 4, Y(-2.05) - 5, "seizure threshold −2.05", "t-small t-critical", "end")
    s.text((l + w - r) / 2, h - 8, "true x0 (planted)", "t-muted", "middle")
    s.add(f'<text transform="translate(14,{(t + h - b) / 2}) rotate(-90)" class="t-muted" text-anchor="middle">estimated x0 (posterior mean)</text>')
    order = sorted(rows, key=lambda x: (x["region"] == ez, x["region"] in pz))
    for x in order:
        reg = x["region"]
        col, rad = ("var(--s2)", 7) if reg == ez else (("var(--s3)", 6) if reg in pz else ("var(--s1)", 3.5))
        fp = float(x["P_gt_thr"]) > 0.5 and reg != ez and reg not in pz
        stroke = ' style="stroke:var(--critical);stroke-width:2.5"' if fp else ""
        tx, pm, ps, pg, rh = (float(x[k]) for k in ("true_x0", "post_mean", "post_sd", "P_gt_thr", "rhat"))
        msg = (f"{reg}: true {tx:.2f}, estimated {pm:.2f} ± {ps:.2f}, P(seizing) {pg:.2f}, R-hat {rh:.2f}"
               + (" · FALSE POSITIVE" if fp else ""))
        s.add(f'<circle cx="{X(tx):.1f}" cy="{Y(pm):.1f}" r="{rad}" fill="{col}"{stroke} class="mark ring" ' + tip(msg) + "/>")
    return s.render()


def fig_chain_ranks(diags):
    left, top, lane, w = 260, 26, 46, 1080
    h = top + lane * len(diags) + 52
    s = Svg(w, h, "Rank of the true epileptogenic region in each sampling chain")
    import math
    X = lambda v: left + math.log10(v) / math.log10(162) * (w - left - 30)
    for tk in (1, 2, 5, 10, 20, 50, 100, 162):
        s.line(X(tk), top - 4, X(tk), h - 42, "grid")
        s.text(X(tk), h - 26, tk, "t-muted", "middle")
    s.text(X(1) + 6, top - 10, "← rank 1 = EZ found", "t-small t-good")
    for i, d in enumerate(diags):
        y = top + i * lane + lane / 2
        s.text(left - 12, y + 4, d["label"], "t-small", "end")
        s.line(left, y, w - 30, y, "grid-faint")
        cnt = Counter()
        for c, rk in enumerate(d["ranks"]):
            off = cnt[rk] * 11
            cnt[rk] += 1
            col = "var(--s1)" if rk == 1 else "var(--s2)"
            msg = f"{d['label']} chain {c + 1}: {d['ez']} ranked {rk} of 162"
            s.add(f'<circle cx="{X(rk):.1f}" cy="{y - 8 + off:.1f}" r="5.5" fill="{col}" class="mark ring" ' + tip(msg) + "/>")
    s.text((left + w - 30) / 2, h - 6, "rank of the true EZ among 162 regions (log scale)", "t-muted", "middle")
    return s.render()


def fig_lbfgs(groups):
    w, h, l, r, t, b = 1080, 330, 70, 20, 16, 50
    allx = [p["lp"] for g in groups for p in g["pts"]]
    s = Svg(w, h, "Optimizer runs: log posterior versus number of falsely seizing regions")
    panels = len(groups)
    pw = (w - l - r) / panels
    ymax = max(p["fp"] for g in groups for p in g["pts"]) + 1  # shared y-axis across panels
    for gi, g in enumerate(groups):
        x0 = l + gi * pw
        xs = [p["lp"] for p in g["pts"]]
        ys = [p["fp"] for p in g["pts"]]
        lo, hi = min(xs), max(xs)
        pad = (hi - lo) * 0.08 or 1
        lo, hi = lo - pad, hi + pad
        X = lambda v: x0 + 14 + (v - lo) / (hi - lo) * (pw - 40)
        Y = lambda v: h - b - v / ymax * (h - t - b - 20)
        s.text(x0 + 14, t + 4, g["label"], "t-strong")
        for tk in nice_ticks(0, ymax, 5):
            s.line(x0 + 14, Y(tk), x0 + pw - 26, Y(tk), "grid")
            if gi == 0:
                s.text(l - 2, Y(tk) + 4, int(tk), "t-muted", "end")
        for tk in nice_ticks(lo, hi, 3):
            s.text(X(tk), h - b + 16, f"{tk:,.0f}", "t-muted", "middle")
        for p in g["pts"]:
            col = "var(--s1)" if p["ez_rank"] == 1 else "var(--s2)"
            msg = f"{g['label']} run {p['job']}: log posterior {p['lp']:,.1f}, true EZ rank {p['ez_rank']}, {p['fp']} false positives"
            s.add(f'<circle cx="{X(p["lp"]):.1f}" cy="{Y(p["fp"]):.1f}" r="6" fill="{col}" class="mark ring" ' + tip(msg) + "/>")
    s.text(l + (w - l - r) / 2, h - 8, "log posterior of the optimum (higher = better fit)", "t-muted", "middle")
    s.add(f'<text transform="translate(16,{(t + h - b) / 2}) rotate(-90)" class="t-muted" text-anchor="middle">false-positive regions</text>')
    return s.render()


def fig_lp_gap():
    rows = [("Offset and amplitude priors", 1200, "var(--s1)"), ("iid likelihood on AR(1) noise", 1470, "var(--s2)")]
    left, top, bh, w = 280, 12, 26, 1080
    h = top + 2 * (bh + 14) + 30
    s = Svg(w, h, "Why the true parameters score worse than the chains")
    X = lambda v: left + v / 1600 * (w - left - 120)
    for tk in range(0, 1601, 400):
        s.line(X(tk), top - 4, X(tk), h - 26, "grid")
        s.text(X(tk), h - 10, tk, "t-muted", "middle")
    for i, (lab, v, col) in enumerate(rows):
        y = top + i * (bh + 14)
        s.text(left - 12, y + bh / 2 + 4, lab, "t-small", "end")
        s.add(f'<rect x="{left}" y="{y}" width="{X(v) - left:.1f}" height="{bh}" rx="3" fill="{col}" class="mark" '
              f'{tip(f"{lab}: about {v} log-posterior units (A0098)")}/>')
        s.text(X(v) + 8, y + bh / 2 + 4, f"≈{v}", "t-small")
    return s.render()


# --------------------------------------------------------------------------- page
CSS = """
:root{color-scheme:light;--bg:#f6f5f1;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#77756f;--line:#e4e2dc;--line2:#efede8;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;
--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--neutral:#b9b7af;--accent:#2a78d6;--goodtext:#006300;--crittext:#b42828}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#9a988f;--line:#33322f;--line2:#262624;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;--neutral:#5d5c57;--accent:#3987e5;--goodtext:#4cc94c;--crittext:#f07070}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#9a988f;--line:#33322f;--line2:#262624;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;--neutral:#5d5c57;--accent:#3987e5;--goodtext:#4cc94c;--crittext:#f07070}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 16px 80px}
header.top{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:8px}
h1{font-size:28px;line-height:1.2;margin:4px 0 8px;letter-spacing:-.01em}
h2{font-size:21px;margin:44px 0 6px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:26px 0 6px}
p{margin:6px 0 10px;max-width:880px}.lead{color:var(--ink2);font-size:16px}
.meta{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--ink2);font-size:13px}
.warn{border:1px solid var(--line);border-left:4px solid var(--warning);background:var(--surface);padding:10px 14px;border-radius:6px;margin:14px 0;max-width:880px}
nav.toc{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 4px}nav.toc a{font-size:13px;color:var(--ink2);text-decoration:none;border:1px solid var(--line);background:var(--surface);padding:4px 10px;border-radius:999px}
nav.toc a:hover{color:var(--ink);border-color:var(--ink2)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .v{font-size:26px;font-weight:650;letter-spacing:-.01em}.tile .k{font-size:12.5px;color:var(--ink2)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:760px){.cols{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card h3{margin-top:0}.card ul{margin:4px 0;padding-left:18px}.card li{margin:4px 0}
.fig{margin:18px 0 22px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.fig-title{font-weight:600;font-size:14.5px}.fig-num{color:var(--accent);margin-right:4px}
.fig-cap{font-size:13px;color:var(--ink2);margin:8px 0 0;max-width:none}
.chart{overflow-x:auto}.chart svg{width:100%;min-width:640px;height:auto;display:block}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:760px){.pair{grid-template-columns:1fr}}
.pair .chart svg{min-width:320px}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;color:var(--ink2);margin:6px 0 4px}
.lg{display:inline-flex;align-items:center;gap:6px}.sw{width:12px;height:12px;border-radius:3px;display:inline-block}.sw.dot{border-radius:50%}.sw.line{height:2px;width:16px;border-radius:0}
svg text{fill:var(--ink);font:12px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
svg .t-small{font-size:12px;fill:var(--ink)}svg .t-muted{font-size:11.5px;fill:var(--ink2)}svg .t-strong{font-size:13px;font-weight:650}
svg .t-onbar{font-size:10.5px;fill:#fff;pointer-events:none}svg .t-done,svg .t-good{fill:var(--goodtext)}svg .t-failed,svg .t-critical{fill:var(--crittext)}svg .t-skipped{fill:var(--muted)}
svg .grid{stroke:var(--line);stroke-width:1}svg .grid-faint{stroke:var(--line2);stroke-width:1}
svg .thresh{stroke:var(--critical);stroke-width:1.5;stroke-dasharray:5 4}svg .diag{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 4}
svg .arrow{stroke:var(--muted);stroke-width:2;fill:none}
svg .ring{stroke:var(--surface);stroke-width:2}svg .mark{cursor:default}svg .mark:hover{opacity:.82}
svg .ph-done{fill:var(--surface);stroke:var(--good);stroke-width:2}svg .ph-fail{fill:var(--surface);stroke:var(--critical);stroke-width:2}
svg .ph-skip{fill:var(--line2);stroke:var(--line);stroke-width:1.5;stroke-dasharray:5 4}
.tbl-wrap{overflow-x:auto;margin:10px 0 16px;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
th{font-weight:600;color:var(--ink2);background:var(--line2);position:sticky;top:0}tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);white-space:nowrap}
.b-passed,.b-succeeded,.b-fulfilled,.b-done{color:var(--goodtext);border-color:var(--good)}
.b-failed,.b-refused,.b-not_qualified{color:var(--crittext);border-color:var(--critical)}
.b-indeterminate,.b-open{color:var(--ink2);border-color:var(--warning)}.b-unreviewed,.b-skipped,.b-stale,.b-abstained{color:var(--muted)}
details{margin:10px 0}summary{cursor:pointer;color:var(--accent);font-weight:600;font-size:14px}
code{font:12.5px ui-monospace,Consolas,monospace;background:var(--line2);padding:1px 5px;border-radius:4px}
.who{font-size:12px;color:var(--ink2);text-transform:uppercase;letter-spacing:.06em}
#tip{position:fixed;z-index:9;pointer-events:none;max-width:380px;background:var(--ink);color:var(--surface);font-size:12.5px;line-height:1.4;padding:7px 10px;border-radius:6px;opacity:0;transition:opacity .08s}
.themebtn{float:right;font-size:12px;border:1px solid var(--line);background:var(--surface);color:var(--ink2);border-radius:999px;padding:4px 10px;cursor:pointer}
@media print{nav.toc,.themebtn{display:none}.fig,.card,.tbl-wrap{break-inside:avoid}details{display:block}}
"""

JS = """
const tipEl=document.getElementById('tip');
document.addEventListener('mouseover',e=>{const t=e.target.closest('[data-tip]');if(!t){tipEl.style.opacity=0;return}tipEl.textContent=t.dataset.tip;tipEl.style.opacity=1});
document.addEventListener('mousemove',e=>{const w=tipEl.offsetWidth,h=tipEl.offsetHeight;let x=e.clientX+14,y=e.clientY+14;if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;tipEl.style.left=x+'px';tipEl.style.top=y+'px'});
document.querySelector('.themebtn').addEventListener('click',()=>{const r=document.documentElement;const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;r.dataset.theme=dark?'light':'dark'});
"""


def build(study, out):
    d, st, events = load(study)
    S = st["study"]
    tasks = task_rows(events)
    t0, t1 = ts(events[0]["ts"]), ts(events[-1]["ts"])
    arts = st["artifacts"]
    A = lambda aid: json.loads((d / "artifacts" / aid / "payload.json").read_text(encoding="utf-8"))
    ev_counts = Counter(e["type"] for e in events)
    run_tasks = [t for t in tasks if t["start"]]
    agent_secs = sum((t["end"] - t["start"]).total_seconds() for t in run_tasks if t["end"])
    gates = [e for e in events if e["type"] == "gate_recorded"]

    # cases
    split = next((A(a) for a in arts if arts[a]["schema_name"] == "CohortSplit" and not arts[a]["stale"]), {})
    dev_ids = {x.replace("sub-", "") for x in split.get("development_ids", [])}
    cases = []
    for a in sorted(arts):
        if arts[a]["schema_name"] == "PatientCase" and not arts[a]["stale"]:
            p = A(a)
            ch = p["channels"]
            qc = next(x for x in arts if arts[x]["schema_name"] == "QCReport" and arts[x]["case_id"] == p["case_id"])
            # R2 curators used three payload layouts; read each field from whichever key is present.
            rec = p["recordings"]
            runs = rec.get("ictal", []) + rec.get("interictal", []) if isinstance(rec, dict) else rec
            acq = p.get("montage", {}).get("acquisition") or sorted({r.get("acq") or r.get("acquisition") for r in runs} - {None})
            acq = [acq] if isinstance(acq, str) else acq
            first = lambda *ks: next((ch[k] for k in ks if k in ch), [])
            names = lambda v: v["channels"] if isinstance(v, dict) else v
            cases.append({"case": p["case_id"], "split": "dev" if p["case_id"] in dev_ids else "test",
                          "implant": "/".join(acq).upper(), "n_ch": ch.get("n_total", ch.get("n_channels")),
                          "bad": len(first("bad", "bad_channels_tsv")), "n_soz": len(names(ch["soz"])), "n_res": len(names(ch["resect"])),
                          "n_soz_res": len(names(ch["soz_and_resect"])),
                          "n_ictal": sum(1 for r in runs if r.get("task") == "ictal"),
                          "n_inter": sum(1 for r in runs if r.get("task") == "interictal"), "pc": a, "qc": qc,
                          "noxyz": len(first("channels_without_coords", "channels_without_coordinates"))})

    # modeling diagnostics (R5's independent recomputation)
    W = d / "work"
    dg = {k: json.loads((W / "T0031" / f"diag_{k}.json").read_text()) for k in ("T0026", "T0029A", "T0029B")}
    p1 = read_csv(d / "artifacts/A0095-ModelBundle/posterior_x0_EV_by_region.csv")
    pa = read_csv(d / "artifacts/A0097-ModelBundle/posterior_x0_by_region_armA.csv")
    pb = read_csv(d / "artifacts/A0097-ModelBundle/posterior_x0_by_region_armB.csv")
    truth = json.loads((W / "T0029/attach/truth.json").read_text())
    rhat_sets = [{"label": "VBT-P1 reproduction (A0095)", "regions": [r["Region"] if "Region" in r else r["region"] for r in p1],
                  "rhat": [float(r["rhat"]) for r in p1]},
                 {"label": "Synthetic, own connectome (arm A)", "regions": [r["region"] for r in pa], "rhat": [float(r["rhat"]) for r in pa]},
                 {"label": "Synthetic, template connectome (arm B)", "regions": [r["region"] for r in pb], "rhat": [float(r["rhat"]) for r in pb]}]
    for x in rhat_sets:
        x["n_bad"] = sum(1 for r in x["rhat"] if r > 1.05)
    rank_sets = [{"label": "VBT-P1 · Left-O2", "ez": "Left-O2", "ranks": dg["T0026"]["EZ_rank_per_chain"]},
                 {"label": "Synthetic arm A · R-Amygdala", "ez": "Right-Amygdala", "ranks": dg["T0029A"]["EZ_rank_per_chain"]},
                 {"label": "Synthetic arm B · R-Amygdala", "ez": "Right-Amygdala", "ranks": dg["T0029B"]["EZ_rank_per_chain"]}]
    lb = []
    for lab, f, rk, fp in (("VBT-P1 · 11 of 20 starts converged", "artifacts/A0095-ModelBundle/map_ensemble_primary.csv", "O2_rank_x0", "n_x0_gt_m2_05"),
                           ("Synthetic arm A · 8 of 10 converged", "artifacts/A0097-ModelBundle/map_ensemble_A.csv", "EZ_rank", "n_FP"),
                           ("Synthetic arm B · 9 of 10 converged", "artifacts/A0097-ModelBundle/map_ensemble_B.csv", "EZ_rank", "n_FP")):
        pts = []
        for r in read_csv(d / f):
            if not r.get("lp") or r.get("converged", "True") != "True":
                continue
            n = int(float(r[fp]))
            if fp == "n_x0_gt_m2_05":
                n = max(0, n - (1 if int(float(r[rk])) <= n else 0))  # exclude the EZ itself
            pts.append({"job": r["job"], "lp": float(r["lp"]), "ez_rank": int(float(r[rk])), "fp": n})
        lb.append({"label": lab, "pts": pts})

    fig = iter(range(1, 50))
    H = []
    H.append(f"""<header class="top"><button class="themebtn" type="button">Light / dark</button>
<div class="who">ScienceClaw epilepsy research system · study summary</div>
<h1>Surgery vs neurostimulation for drug-resistant focal epilepsy: study-001</h1>
<p class="lead">{E(S["question"])}</p>
<div class="meta"><span>Study <code>{E(S["study_id"])}</code></span><span>Release <code>{E(S["system_release_id"])}</code></span>
<span>Protocol v1 (A0001)</span><span>Run {t0:%Y-%m-%d %H:%M} – {t1:%H:%M} UTC</span><span>Status: {badge("done", next((e["status"] for e in reversed(events) if e["type"] == "study_status"), "open"))}</span>
<span>Report generated {dt.datetime.now():%Y-%m-%d %H:%M} from the ledger and committed artifacts</span></div>
<div class="warn"><b>Intended use.</b> Research evidence on the literature and on virtual patients. Nothing here is a clinical recommendation for any individual patient. Literature numbers are taken from abstracts; see Limitations.</div>
<nav class="toc"><a href="#summary">1 Summary</a><a href="#workflow">2 Workflow</a><a href="#agents">3 Agents & history</a><a href="#evidence">4 Clinical evidence</a>
<a href="#data">5 Data & cases</a><a href="#modeling">6 Virtual-patient modeling</a><a href="#quality">7 Quality controls</a><a href="#limits">8 Limitations & next steps</a><a href="#appendix">Appendix</a></nav></header>""")

    # 1 summary
    H.append(f"""<h2 id="summary">1 · Summary</h2>
<div class="tiles">
<div class="tile"><div class="v">{len(run_tasks)}</div><div class="k">agent tasks run ({ev_counts["task_refused"]} more refused by the controller)</div></div>
<div class="tile"><div class="v">{len(arts)}</div><div class="k">artifacts committed</div></div>
<div class="tile"><div class="v">{len(gates)}</div><div class="k">gate decisions, none by the producing role</div></div>
<div class="tile"><div class="v">{fmt_dur((t1 - t0).total_seconds())}</div><div class="k">wall clock; {fmt_dur(agent_secs)} of agent work</div></div>
<div class="tile"><div class="v">10</div><div class="k">patient cases curated and independently re-verified</div></div>
<div class="tile"><div class="v">0</div><div class="k">patient models qualified (pipeline failed benchmarks)</div></div></div>
<div class="cols">
<div class="card"><h3>For clinicians</h3><ul>
<li><b>Resectable focus, especially mesial temporal lobe epilepsy:</b> open temporal resection has the strongest evidence and is the only option with randomised evidence against continued medication. 58–73% were free of disabling seizures at 1–2 years, and 66–72.5% were seizure-free long term.</li>
<li><b>LITT:</b> 53–58% Engel I at 12–24 months, with fewer complications than open surgery. The gap to open surgery is not significant after matching in one pooled analysis, and there is no RCT.</li>
<li><b>Neurostimulation (RNS, ANT-DBS, VNS) is palliative.</b> Median seizure reduction is about 40–75%, up to 82% in one RNS cohort, but seizure freedom is uncommon (8–22%). No head-to-head trial compares the modalities.</li>
<li><b>Model-guided ("virtual brain twin") stimulation</b> has no clinical outcome evidence yet.</li></ul></div>
<div class="card"><h3>For engineers</h3><ul>
<li>A deterministic controller admitted {len(run_tasks)} tasks for 6 agent roles. It refused {ev_counts["task_refused"]} proposals and recorded {ev_counts["repair_issued"]} repairs. Outcome labels were sealed in a vault that was never opened.</li>
<li>The Wang 2025 vep-stim inversion pipeline <b>failed both qualification benchmarks</b>. Sampling did not converge (R-hat up to 4.24) and the planted or documented seizure-onset zone was not reliably recovered, even with the true connectome.</li>
<li>R5 traced the failure to the method: amplitude vs EZ-extent non-identifiability, priors that conflict with realistic feature levels, an iid likelihood on autocorrelated noise, and a multimodal posterior. Three package defects were also found and patched in a copy.</li>
<li>So no patient was modeled, and intervention design and outcome evaluation (P4–P5) were not run.</li></ul></div></div>""")

    # 2 workflow
    H.append(f"""<h2 id="workflow">2 · Workflow</h2>
<p>Agents propose and the controller decides. Every task is admitted against the role's frozen profile (allowed outputs, scope, budget, input status). Every artifact is gated by a different role, and every event is appended to <code>ledger.jsonl</code>. Skills, profiles and controller code were frozen at study start as release <code>{E(S["system_release_id"])}</code>.</p>
{figure(next(fig), "Phases and their outcome", fig_workflow(), "Green border: phase completed. Red border: phase ran but its result failed qualification. Dashed grey: phase not run, and why.")}
{table(["Phase", "What happened", "Key records"], [
        ["P0 Protocol", "LEAD drafted protocol v1 (question, population, endpoints, 60/40 patient-level split, acceptance criteria, budgets); the user approved it.", "A0001"],
        ["P1 Discovery", "R1 searched the literature, datasets and methods; R5 source-checked each record. Two reports and three dataset cards were repaired.", "A0002–A0070"],
        ["P2 Case curation", "ds004100 downloaded with approval; outcomes sealed; patient split 34/22; 10 cases selected without outcomes and curated; R5 re-hashed all 254 files.", "A0071–A0094"],
        ["P3 Virtual patient", "Two R3 benchmarks (Wang Patient 1 reproduction; synthetic planted-EZ recovery); R5 qualification: not qualified.", "A0079, A0095–A0098"],
        ["P4–P5", "Not run: no qualified model, so no intervention simulations, no frozen predictions, no outcome reveal.", "N014"],
        ["P6 Dossier", "LEAD assembled the DecisionBundle and report from gated records only.", "A0099–A0100"],
        ["P7 Review", "RV requested revision (7 findings); LEAD repaired; RV accepted.", "A0101–A0104"],
        ["P8 Improvement", "R6 disabled; the lessons were applied as edits for the next release (controller fixes, skills, budgets).", "system/history"]])}""")

    # 3 agents
    roles_used = [r for r in ROLE_ORDER if any(t["role"] == r for t in tasks)]
    prof = {r: json.loads((d / "release" / "profiles" / f"{r}.json").read_text()) for r in ROLE_ORDER
            if (d / "release" / "profiles" / f"{r}.json").exists()}
    role_rows = []
    for r in ROLE_ORDER:
        tl = [t for t in tasks if t["role"] == r]
        rr = [t for t in tl if t["start"]]
        secs = sum((t["end"] - t["start"]).total_seconds() for t in rr if t["end"])
        produced = [a for a in arts.values() if a["producer_role"] == r]
        given = sum(1 for g in gates if g["evaluator"] == r)
        bud = prof.get(r, {}).get("budget", {}).get("max_tasks_per_run", "–")
        en = prof.get(r, {}).get("enabled", True)
        role_rows.append([f'<span class="sw" style="background:{ROLE_VAR[r]}"></span> <b>{ROLE_SHORT[r]}</b> {E(ROLE_NAME[r])}',
                          f"{len(rr)} / {bud}" if en else "disabled", fmt_dur(secs) if rr else "–", len(produced),
                          given, ", ".join(sorted({t["type"] for t in rr})) or "–"])
    H.append(f"""<h2 id="agents">3 · Agents and working history</h2>
<p>Each role is a subagent that follows its frozen skill and talks to the study only through the controller CLI. The lead (this session) orchestrated, gated R5's reports, sealed outcome files and wrote the dossier.</p>
{table(["Role", "Tasks used / budget", "Agent time", "Artifacts produced", "Gates given", "Task types"], role_rows, raw_cols=(0,))}
{figure(next(fig), "Who worked on what, when", fig_gantt(tasks, t0, t1),
        "One bar per task from start to finish, coloured by role and labelled with its task id when space allows. Overlapping bars in a lane are agents of the same role running in parallel. Hover a bar for its objective, duration and result.",
        legend_html([(ROLE_SHORT[r] + " " + ROLE_NAME[r], ROLE_VAR[r], "") for r in roles_used]))}
{figure(next(fig), "Artifacts per producing role, by gate verdict", fig_gate_bars(st),
        "Effective verdict of each committed artifact (latest gate). Failed artifacts were repaired or superseded where needed; the two failed ModelBundles are the benchmark results themselves.",
        legend_html([("passed", "var(--good)", ""), ("failed", "var(--critical)", ""), ("indeterminate", "var(--warning)", ""), ("unreviewed", "var(--neutral)", "")]))}""")
    trows = []
    for t in tasks:
        dur = fmt_dur((t["end"] - t["start"]).total_seconds()) if t["start"] and t["end"] else "–"
        trows.append([f"<code>{t['id']}</code>", f'<span class="sw" style="background:{ROLE_VAR[t["role"]]}"></span> {ROLE_SHORT[t["role"]]}',
                      E(t["type"]), E(t["case"] or "–"), t["start"].strftime("%H:%M") if t["start"] else "–", dur,
                      badge(t["state"] if t["state"] in ("succeeded", "refused", "abstained") else "unreviewed", t["state"]),
                      E(", ".join(x.split("-")[0] for x in t["outputs"]) or "–"), E(t["objective"][:220] + ("…" if len(t["objective"]) > 220 else ""))])
    H.append("<details><summary>Full task log (" + str(len(tasks)) + " proposals)</summary>" +
             table(["Task", "Role", "Type", "Case", "Start (UTC)", "Duration", "Result", "Outputs", "Objective"], trows, raw_cols=(0, 1, 2, 3, 6, 7, 8)) + "</details>")
    rep = [e for e in events if e["type"] in ("repair_issued", "task_refused")]
    H.append("<h3>Repairs and refusals</h3>" + table(["Time", "Event", "Target", "Reason"], [
        [ts(e["ts"]).strftime("%H:%M"), "repair" if e["type"] == "repair_issued" else "refused proposal",
         e.get("artifact_id") or e.get("task_id"), (e.get("reason") or "; ".join(e.get("reasons", [])))[:260]] for e in rep]))

    # 4 evidence
    sf = [("Medical therapy (comparator in RCTs)", 0, 8, "var(--neutral)", "A0017, A0018", "free of disabling seizures, 1–2 y"),
          ("Temporal resection · RCTs", 58, 73, "var(--s1)", "A0017, A0018", "free of disabling seizures, 1–2 y, n=118"),
          ("Temporal resection · long term", 66, 72.5, "var(--s1)", "A0020, A0027", "seizure-free ≥5 y / >24 mo pooled"),
          ("All resections, adults · 5–10 y", 47, 52, "var(--s1)", "A0021", "continuous seizure freedom (stricter)"),
          ("LITT · mesial TLE", 53.4, 58.0, "var(--s3)", "A0022–A0024", "Engel I, 12–24 mo, no RCT"),
          ("RNS", 18, 22, "var(--s2)", "A0004–A0006", "≥12 mo seizure-free"),
          ("ANT-DBS", 16, 16, "var(--s2)", "A0009", "≥6 mo seizure-free (SANTE)"),
          ("VNS", 8.2, 8.2, "var(--s2)", "A0015", "seizure-free at 24–48 mo, mixed epilepsies")]
    red = [("RNS", 44, 82, "var(--s2)", "A0003–A0006", "median reduction; 44–53% at 1–2 y, 75% at 9 y, 67–82% real-world"),
           ("ANT-DBS", 41, 75, "var(--s2)", "A0008–A0010", "median reduction; 41–56% at 1–2 y, 69–75% at 5–7 y"),
           ("VNS", 45, 51, "var(--s2)", "A0013, A0014", "median 45% at 12 mo; 51% average reduction (meta-analysis)")]
    claims = [a for a in sorted(arts) if arts[a]["schema_name"] == "EvidenceClaim"]
    H.append(f"""<h2 id="evidence">4 · Clinical evidence (literature, abstract level)</h2>
<p>R1 committed {len(claims)} evidence claims, one per source passage. R5 checked each against the source text, and papers on the same patients were grouped into one study family. Seizure freedom and seizure reduction are different endpoints, so they are shown in separate charts.</p>
{figure(next(fig), "Seizure freedom by intervention", fig_range(sf, "Seizure-free proportion by intervention"),
        "Range across the cited studies (dots at the reported low and high values; a single dot is a single estimate). Definitions differ: Engel I, free of disabling seizures, or ≥6 vs ≥12-month freedom. Comparisons across rows are indirect.",
        legend_html([("Resection", "var(--s1)", "dot"), ("Laser ablation (LITT)", "var(--s3)", "dot"), ("Neurostimulation", "var(--s2)", "dot"), ("Medical therapy", "var(--neutral)", "dot")]))}
{figure(next(fig), "Median seizure-frequency reduction with neurostimulation (≥12 months)", fig_range(red, "Median seizure reduction by neurostimulation modality"),
        "Gains grow with years of open-label follow-up, which is confounded by attrition, medication and programming changes. Only the short blinded phases were randomised. VNS pooled data include non-focal epilepsy.")}
{table(["Comparison", "Finding", "Strength / caveat", "Records"], [
        ["Resection vs LITT", "Open 67.1% vs LITT 52.5%, RR 0.78 unmatched; 72.5% vs 57.1% in MTLE >24 mo", "Not significant after propensity matching (RR 0.85, p=0.30) or within TLE; LITT has fewer complications", "A0027–A0029"],
        ["Resection risks", "Memory decline 36% (ERSET); paediatric RCT serious adverse events 33%", "Small trials", "A0018, A0019"],
        ["RNS vs DBS vs VNS", "No head-to-head RCT", "Indirect comparison only", "A0031"],
        ["Model-guided stimulation", "No clinical outcome study found; Wang 2025 is diagnostic (2 patients + synthetic); VEP retrospective precision 0.6 (n=53)", "Need N001 open", "A0016, A0055–A0057"],
        ["Guideline", "AES/CNS 2026: strong for ATL in MTLE; conditional for LITT", "Synthesises the same primary studies", "A0030"]])}
<details><summary>All {len(claims)} evidence claims</summary>{table(["Id", "Claim", "Gate"], [[a.split("-")[0], arts[a].get("title") or "", badge(arts[a]["effective_validation"])] for a in claims], raw_cols=(2,))}</details>""")

    # 5 data & cases
    ds = [["1", "OpenNeuro ds004100 v1.1.3 (HUP)", "57", "Contact coordinates (mm, MNI template); resect + soz tags 57/57", "Engel, S/F/NR (sealed)", "CC0 · 14.2 GB", "A0070"],
          ["2", "Omni-iEEG (Hugging Face)", "328 rows", "Channel-level resection 0/1", "Binary Engel 1 vs 2+", "Licence to verify · 159 GB", "A0040"],
          ["3", "OpenNeuro ds003498 (Zurich HFO)", "20", "Resection-zone contacts (clinical sheet)", "ILAE 1–6", "CC0 · 48 GB", "A0038"],
          ["4", "OpenNeuro ds003029 (Fragility)", "35", "No coordinates; surgery type", "Engel/ILAE", "CC0 · 11.1 GB", "A0035"],
          ["5", "OpenNeuro ds003876 v1.0.2", "39 (10 RNS)", "No stimulation settings", "After-surgery outcome (sealed)", "CC0 · 5.5 GB", "A0065"],
          ["6", "Kini 2019 virtual-resection cohort", "28 reported", "Resected electrodes reported", "Engel/ILAE reported", "IEEG.org, to verify", "A0034"],
          ["–", "Wang 2025 dataSim", "2 simulated", "SC + gain matrices", "none (simulated)", "Apache-2.0", "A0067"]]
    H.append(f"""<h2 id="data">5 · Data and patient cases</h2>
<p>The target was public intracranial EEG with electrode positions, a record of what was resected or stimulated, and a post-intervention outcome class. No public dataset links stimulation settings to outcomes (need N006). Omni-iEEG repackages ranks 1, 3, 4 and 5, so it is not independent of them.</p>
{table(["Rank", "Dataset", "Subjects", "Localisation / intervention", "Outcome field", "Access", "Card"], ds)}
<h3>Cohort and the 10 curated cases (ds004100)</h3>
<p>56 eligible patients were split by patient into 34 development and 22 test cases with seed 20261101 (A0071, split_hash <code>255216f5…</code>). R2 selected 10 cases without seeing outcomes and curated each one. R5 re-hashed all 254 raw files and passed all 20 records (A0094).</p>
{figure(next(fig), "Seizure-onset contacts inside vs outside the resection/ablation zone", fig_cases(cases),
        "From channel tags in each PatientCase (clinical 'soz' and 'resect' marks); this is the delivered intervention, not an outcome. In 5 of 10 cases at least one onset contact lies outside the resected zone, and in 4 of them most do. A qualified model could have tested this against outcomes in P5.",
        legend_html([("onset contact resected", "var(--s1)", ""), ("onset contact not resected", "var(--s2)", "")]))}
{table(["Case", "Split", "Implant", "Channels (bad)", "No coordinates", "Seizures", "Interictal", "Onset contacts", "Resected contacts", "Onset ∩ resected", "Records"],
        [[c["case"], c["split"], c["implant"], f'{c["n_ch"]} ({c["bad"]})', c["noxyz"], c["n_ictal"], c["n_inter"], c["n_soz"], c["n_res"], c["n_soz_res"], f'{c["pc"].split("-")[0]}, {c["qc"].split("-")[0]}'] for c in cases])}
<p class="fig-cap">R5's additional findings: 21 of the 61 runs, all ictal (21 of 41 ictal runs), end with a constant EDF pad, so the last 1 s of each ictal run should be dropped. Some contacts share identical coordinates (HUP126, HUP114). The coordinate template (ICBM152 vs fsaverage) is still to be verified, and mne-bids reads the mm values as metres.</p>""")

    # 6 modeling
    nuts = [["VBT-P1 reproduction (Wang Patient 1)", "Left-O2 (documented)", "8 × 75", f'{dg["T0026"]["x0_rhat_max"]:.2f}', f'{dg["T0026"]["x0_n_rhat_gt_1_05"]}/162',
             f'{dg["T0026"]["x0_ess_bulk_min"]:.1f}', f'{sum(dg["T0026"]["divergences_per_chain"])}', f'{dg["T0026"]["n_at_max_depth"]}/600',
             f'{dg["T0026"]["EZ_rank_pooled_mean"]}', f'{dg["T0026"]["EZ_P_rank1"]:.2f}', badge("failed")],
            ["Synthetic arm A (own connectome)", "Right-Amygdala (planted)", "5 × 300", f'{dg["T0029A"]["x0_rhat_max"]:.2f}', f'{dg["T0029A"]["x0_n_rhat_gt_1_05"]}/162',
             f'{dg["T0029A"]["x0_ess_bulk_min"]:.1f}', f'{sum(dg["T0029A"]["divergences_per_chain"])}', f'{dg["T0029A"]["n_at_max_depth"]}/1500',
             f'{dg["T0029A"]["EZ_rank_pooled_mean"]}', f'{dg["T0029A"]["EZ_P_rank1"]:.2f}', badge("failed")],
            ["Synthetic arm B (template connectome)", "Right-Amygdala (planted)", "6 × 300", f'{dg["T0029B"]["x0_rhat_max"]:.2f}', f'{dg["T0029B"]["x0_n_rhat_gt_1_05"]}/162',
             f'{dg["T0029B"]["x0_ess_bulk_min"]:.1f}', f'{sum(dg["T0029B"]["divergences_per_chain"])}', f'{dg["T0029B"]["n_at_max_depth"]}/1800',
             f'{dg["T0029B"]["EZ_rank_pooled_mean"]}', f'{dg["T0029B"]["EZ_P_rank1"]:.2f}', badge("indeterminate", "informative only")]]
    pz = set(truth["pz_names"])
    H.append(f"""<h2 id="modeling">6 · Virtual-patient modeling (simulation and inference)</h2>
<p>The planned method was Wang et al. 2025's virtual brain twin (vep-stim, commit <code>5367ef4</code>). It fits a 162-region 2D Epileptor network to SEEG features with Stan, and the region excitability <i>x0</i> above about −2.05 marks a region as seizing (the epileptogenic zone, EZ). Before fitting any patient, the pipeline had to pass two benchmarks where the right answer is known.</p>
{table(["Benchmark", "Design", "Truth", "Run", "Records"], [
        ["1 · Reproduction (T0026)", "Fit Wang's own simulated SEEG for Patient 1 with the authors' Stan model and settings", "EZ documented as Left-O2", "20 L-BFGS starts + 8 NUTS chains, 2 h 20 min", "A0079, A0095"],
        ["2 · Synthetic recovery (T0029)", "Plant an EZ (seed 20261129) on Patient 2's connectome + gain, simulate with the model's own forward model, fit twice", "Right-Amygdala x0 = −1.6; 2 sub-threshold neighbours", "10 L-BFGS + 5–6 NUTS chains per arm, 1 h 52 min", "A0096, A0097"],
        ["Qualification (T0031)", "R5 recomputed all diagnostics from stored draws with its own code, re-ran cheap checks", "Protocol: R-hat < 1.05, EZ recovered", "15 min", "A0098"]])}
<h3>Convergence and recovery (R5's recomputation)</h3>
{table(["Fit", "EZ", "Chains × draws", "Max R-hat", "x0 R-hat > 1.05", "Min ESS", "Divergences", "At max tree depth", "EZ rank (pooled)", "P(EZ ranked 1st)", "Verdict"], nuts, raw_cols=(10,))}
{figure(next(fig), "Convergence: R-hat of every region's x0", fig_rhat(rhat_sets),
        "Each dot is one of 162 regions (per-region values from R3's posterior summaries; R5's own recomputation, in the table above, agrees within 0.05). R-hat compares the chains with one another; values above 1.05 mean the chains disagree and the posterior cannot be trusted. Orange dots fail the threshold.",
        legend_html([("R-hat ≤ 1.05", "var(--s1)", "dot"), ("R-hat > 1.05", "var(--s2)", "dot"), ("1.05 threshold", "var(--critical)", "line")]))}
{figure(next(fig), "Recovery: where each chain ranks the true EZ", fig_chain_ranks(rank_sets),
        "Each dot is one sampling chain. In the Patient 1 reproduction, two chains ranked Left-O2 4th and six ranked it near the bottom. With the matching connectome (arm A), only 2 of 5 chains put the planted EZ first. With the template connectome (arm B), all 6 did, but those chains still did not converge.",
        legend_html([("EZ ranked 1st", "var(--s1)", "dot"), ("EZ not 1st", "var(--s2)", "dot")]))}
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Synthetic benchmark: planted vs estimated excitability, per region</figcaption>
{legend_html([("planted EZ (Right-Amygdala)", "var(--s2)", "dot"), ("planted sub-threshold neighbours", "var(--s3)", "dot"), ("other regions", "var(--s1)", "dot"), ("false positive (red ring)", "var(--critical)", "dot")])}
<div class="pair"><div><div class="t-muted" style="font-size:13px;font-weight:600">Arm A · own connectome</div><div class="chart">{fig_truth_scatter(pa, "Arm A", truth["ez_name"], pz)}</div></div>
<div><div class="t-muted" style="font-size:13px;font-weight:600">Arm B · template connectome</div><div class="chart">{fig_truth_scatter(pb, "Arm B", truth["ez_name"], pz)}</div></div></div>
<p class="fig-cap">Perfect recovery would put every dot on the dotted diagonal. Regions above the dashed line are estimated to seize. In both arms the planted EZ is found, but the two planted sub-threshold neighbours are also estimated as seizing, and insula and prefrontal regions appear as false positives. The amplitude was estimated at about 0.05 against a true 0.1.</p></figure>
{figure(next(fig), "Optimizer ensembles: better fit does not mean the right answer", fig_lbfgs(lb),
        "Each dot is one converged L-BFGS optimum (primary settings). If the model were identifiable, the best-fitting runs (right) would rank the true EZ first (blue) with few false positives (bottom). In the Patient 1 reproduction no optimum ranks Left-O2 first, and near-equal fits name different regions. In the synthetic arms most optima find the planted EZ, but with 6–14 extra seizing regions, except the few best arm B fits. The EZ extent is therefore not recovered. For VBT-P1, false positives are the regions above threshold other than Left-O2.",
        legend_html([("true EZ ranked 1st", "var(--s1)", "dot"), ("true EZ not 1st", "var(--s2)", "dot")]))}
{figure(next(fig), "Why the true parameters score worse than the chains (arm A)", fig_lp_gap(),
        "At the planted truth the log posterior is about 2,700 units below every chain. R5 attributed about 1,200 units to the offset and amplitude priors and about 1,470 to the iid likelihood fitting autocorrelated (AR(1)) noise. The model prefers wrong answers, so longer sampling alone cannot fix it.")}
<h3>Defects found in the package (patched only in a work-dir copy)</h3>
{table(["Defect", "Effect", "Fix and check"], [
        ["Likelihood skip is column-major", "Drops SEEG channels 0–11 (and 110 steps of channel 12) instead of the first 10 time points", "Patched; matched an independent numpy log density (R5)"],
        ["Feature filters hard-code 250 Hz", "Wang files are 100 Hz (Patient 1) and 125 Hz (Patient 2)", "Read the rate from each file"],
        ["Noise padding", "Step artefacts dominate channels with DC offsets", "Per-channel baseline referencing"],
        ["End zero-padding", "Distorts the last samples of the window", "Reflect padding"]])}
<div class="card"><h3>Verdict (A0098)</h3><p>{badge("not_qualified", "not qualified")} The pipeline, as packaged or as patched, is not qualified for fitting HUP patients with a template connectome. The failures lie mainly in the method (identifiability, priors, observation model), not in run length. Patient modeling, intervention simulation (P4) and outcome evaluation (P5) were therefore not run. A virtual-patient result, had there been one, would be a hypothesis about a model, not a clinical prediction.</p></div>""")

    # 7 quality
    needs = st["needs"]
    vault_items = [e for e in events if e["type"] == "vault_sealed"]
    H.append(f"""<h2 id="quality">7 · Quality controls and traceability</h2>
<div class="cols"><div class="card"><h3>Outcome blinding</h3><ul>
<li>{len(vault_items)} outcome-bearing files were sealed in the vault (V001–V{len(vault_items):03d}) and their plaintext deleted.</li>
<li>The vault is readable only by an R5 outcome-evaluation task after predictions are frozen. Predictions were never frozen and the vault was never opened (0 access events).</li>
<li><b>Disclosed exposure:</b> before sealing, discovery read some participants files, so dataset-level outcome aggregates appear in superseded records (A0033, A0058) and in three cards. No per-patient labels are on record outside the vault. Any future outcome evaluation on this split must report this.</li></ul></div>
<div class="card"><h3>Independent checking</h3><ul>
<li>{len(gates)} gate decisions; the controller refuses a gate by the producing role.</li>
<li>R5 re-derived every number it gated (source passages, file hashes, R-hat from raw draws). RV reviewed the dossier, found 7 issues and accepted the repaired version.</li>
<li>{ev_counts["repair_issued"]} repairs marked {ev_counts["artifact_stale"]} artifacts stale until replaced; {ev_counts["task_refused"]} task proposals were refused at admission.</li></ul></div></div>
<h3>Open needs (evidence still missing)</h3>
{table(["Need", "Raised by", "Missing", "State"], [[n, needs[n]["requester"].split("-")[0], needs[n]["missing_input"][:230], badge(needs[n]["state"] if needs[n]["state"] in ("open", "fulfilled") else "unreviewed", needs[n]["state"])] for n in sorted(needs)], raw_cols=(3,))}""")

    # 8 limits
    H.append("""<h2 id="limits">8 · Limitations and next steps</h2>
<div class="cols"><div class="card"><h3>Limitations</h3><ul>
<li>All literature evidence is abstract-level: late-timepoint denominators and responder definitions are unverified (needs N002, N003).</li>
<li>VNS pooled and registry data include generalised epilepsy, which is outside the protocol population.</li>
<li>Cross-modality comparisons are indirect; resection and neurostimulation answer different questions (cure vs palliation) in different populations.</li>
<li>No virtual-patient evidence: the benchmarks used one planted EZ and one seed, and the synthetic data bypassed the feature pipeline.</li>
<li>Only 10 of 56 eligible cases were curated, within the role budgets.</li></ul></div>
<div class="card"><h3>Already applied for the next release</h3><ul>
<li>Controller: a summary may cite records from its own task; review reports and decisions are no longer marked stale when what they judged is repaired (2 new invariant tests).</li>
<li>R3 skill: a mandatory synthetic qualification benchmark through the full feature pipeline, per-file sampling rate, and observation-model checks.</li>
<li>R1 skill: never read outcome-bearing files; dataset cards hold field names only.</li>
<li>Lead skill: stop modeling on a failed benchmark; check budgets before modeling. R3 budget raised 10 → 14 and R5 10 → 12.</li>
<li>To revisit patient modeling: a pipeline that passes the benchmark (need N014), e.g. a reparameterised likelihood with AR(1) noise and data-centred priors, plus an MNI template connectome.</li></ul></div></div>""")

    # appendix
    man = []
    for a in sorted(arts):
        x = arts[a]
        man.append([a.split("-")[0], x["schema_name"], x["producer_role"].split("-")[0], x.get("case_id") or "–",
                    badge("stale" if x["stale"] else x["effective_validation"], ("stale · " if x["stale"] else "") + x["effective_validation"]),
                    E((x.get("title") or "")[:140]), f'<code>{x["manifest_hash"][:12]}</code>'])
    H.append(f"""<h2 id="appendix">Appendix · Reproducibility</h2>
<ul><li>Frozen release <code>{E(S["system_release_id"])}</code> (skills, profiles and controller code under <code>studies/{E(S["study_id"])}/release/</code>).</li>
<li>Environments: Python 3.11 with mne 1.13.2 and mne-bids 0.20.0; model venv with tvb-library 2.10.0, cmdstanpy 1.3.0, numpy 2.4.6 and vep-stim 0.1.0a1 @ 5367ef4; CmdStan 2.40 (conda-forge).</li>
<li>Data: ds004100 v1.1.3 retrieval manifest sha256 <code>62e8da45…</code>; seeds 20261101 (split, case selection), 20261129 (synthetic truth), L-BFGS 1000–1019 and NUTS 12345 (Patient 1 benchmark).</li>
<li>Final dossier: A0102-DecisionBundle and A0103-Report (accepted by RV in A0104); text in <code>studies/{E(S["study_id"])}/report.md</code>.</li></ul>
<details><summary>All {len(arts)} artifacts with manifest hashes</summary>{table(["Id", "Schema", "Producer", "Case", "Verdict", "Title", "Manifest hash"], man, raw_cols=(4, 5, 6))}</details>""")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Study-001 Summary Report</title><style>{CSS}</style></head><body><div class="wrap">{"".join(H)}</div><div id="tip" role="tooltip"></div><script>{JS}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--study", default="study-001")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else ROOT / "reports" / f"{a.study}-summary.html"
    print(build(a.study, out))


if __name__ == "__main__":
    main()
