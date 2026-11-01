"""Build a standalone, offline HTML report of the R4 intervention simulations of study-002 (A0038-SimulationBatch).

    .venv-model/Scripts/python.exe system/reports/r4_report.py --out reports/study-002-R4-simulations.html

Read-only: committed artifacts A0018-A0038, the prespecified R4 spec, the simulator file (hash only), the ledger
(through the controller's read-only state replay) and the P2 data file (hash only). Never reads studies/*/vault/.
Every number in the page is taken from, or recomputed and checked against, these files.
"""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "system" / "reports"))
import study_report as sr  # noqa: E402  (style + SVG helpers; imports the controller read-only)

E, Svg, tip, nice_ticks, figure, legend_html, badge = sr.E, sr.Svg, sr.tip, sr.nice_ticks, sr.figure, sr.legend_html, sr.badge
ctl = sr.ctl

STUDY = "study-002"
SD = ROOT / "studies" / STUDY
ART = SD / "artifacts"
B = ART / "A0038-SimulationBatch"
WINDOWS = ("post", "full")
TYPE_COL = {"ablation": "var(--s1)", "disconnection": "var(--s3)", "sustained current": "var(--s7)",
            "pulse train": "var(--s2)", "chronic pulse train": "var(--s5)", "baseline": "var(--ink2)"}
STATIC_ARMS = ["BASELINE", "RES-EZ+PZ/ablation", "RES-EZ+PZ/disconnection", "STIM-1/amp1", "STIM-PT/amp1", "STIM-PT-chronic/amp1"]
U_LO, U_HI = -2.2, 0.6  # shared colour scale for region activity u1; the ramp's mid (blue) stop sits at the -1 threshold


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def q(v):
    return dict(median=float(np.median(v)), p05=float(np.percentile(v, 5)), p95=float(np.percentile(v, 95)))


def arm_type(c):
    if c is None:
        return "baseline"
    t = c["type"]
    if t == "pulse_train":
        return "chronic pulse train" if c.get("duration_ms") is None else "pulse train"
    return t.replace("_", " ")


def npz_key(cid):
    return cid.replace("+", "p").replace("/", "__")


def pct(x):
    return f"{100 * x:.0f}%"


def sg(x, nd=1):
    r = round(x, nd)
    return "0" if r == 0 else f"{r:+.{nd}f}"


def rng(d, nd=1):
    return f"{sg(d['median'], nd)} [{sg(d['p05'], nd)}, {sg(d['p95'], nd)}]"


def tbl(headers, rows, raw_cols=(), num_cols=(), caption=None, cls=""):
    h = "".join(f'<th scope="col" class="{"num" if i in num_cols else ""}">{E(x)}</th>' for i, x in enumerate(headers))
    body = "".join("<tr>" + "".join(
        f'<td class="{"num" if i in num_cols else ""}">{c if i in raw_cols else E(str(c))}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    cap = f'<caption>{E(caption)}</caption>' if caption else ""
    return f'<div class="tbl-wrap"><table class="{cls}">{cap}<thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


# --------------------------------------------------------------------------- data
def load():
    P = jload(B / "payload.json")
    lut = [ln.split()[1] for ln in (ROOT / "data/wang-5367ef4/data/VepMrtrixLut.txt").read_text().splitlines()
           if ln.strip() and ln.split()[0].isdigit() and 1 <= int(ln.split()[0]) <= 162]
    assert len(lut) == 162
    W = {}
    for w in WINDOWS:
        R = P["results"][w]
        C = jload(B / f"{w}_candidates.json")
        runs = jload(B / f"{w}_runs.json")
        S = jload(B / f"samples_{w}.json")
        assert lut[R["derived"]["top1"]] == R["derived"]["top1_name"]
        assert [lut[i] for i in R["derived"]["pz"]] == R["derived"]["pz_names"]
        base = {b["sample_index"]: b for b in runs["baselines"]}
        per = {}
        for c in C["candidates"]:
            rr = sorted((r for r in runs["candidates"] if r["candidate_id"] == c["id"]), key=lambda r: r["sample_index"])
            per[c["id"]] = [dict(sid=r["sample_id"], i=r["sample_index"], finite=r["finite"],
                                 dn=r["seizures"]["n_seizing_regions"] - base[r["sample_index"]]["seizures"]["n_seizing_regions"],
                                 dd=r["seizures"]["total_seizure_duration_s"] - base[r["sample_index"]]["seizures"]["total_seizure_duration_s"],
                                 dc=r["n_seeg_channels_exceeding"] - base[r["sample_index"]]["n_seeg_channels_exceeding"],
                                 n=r["seizures"]["n_seizing_regions"], run=r) for r in rr]
            # trace check: the payload's effects are reproduced from the per-sample runs
            if c["id"] in R["effects"]:
                e = R["effects"][c["id"]]
                for key, fld in (("dn", "d_n_seizing_regions"), ("dd", "d_total_seizure_duration_s"), ("dc", "d_n_seeg_channels_exceeding")):
                    got = q([x[key] for x in per[c["id"]]])
                    assert all(abs(got[k] - e[fld][k]) < 1e-9 for k in got), (w, c["id"], fld, got, e[fld])
                assert abs(np.mean([x["n"] == 0 for x in per[c["id"]]]) - e["frac_abolish_all"]) < 1e-12
            else:
                f = R["numerically_failed_arms"][c["id"]]
                assert f["n_nonfinite"] == sum(not x["finite"] for x in per[c["id"]])
        bq = q([b["seizures"]["n_seizing_regions"] for b in runs["baselines"]])
        assert all(abs(bq[k] - R["baseline_summary"]["n_seizing_regions"][k]) < 1e-9 for k in bq)
        W[w] = dict(R=R, C=C, cand={c["id"]: c for c in C["candidates"]}, runs=runs, base=base, per=per, S=S,
                    msi=R["meta"]["median_sample_index"])
    return P, lut, W


# --------------------------------------------------------------------------- SVG charts
def fig_effect(w, Wd, fld, key, unit, title, nd=1, order=None):
    """One row per candidate: 5-95% range bar, one faint dot per optimum, median marker. Failed arms listed, not plotted."""
    R = Wd["R"]
    order = order or (R["ranking"] + list(R["numerically_failed_arms"]))
    vals = [x[key] for cid in order if cid in R["effects"] for x in Wd["per"][cid]]
    lo, hi = min(vals + [0]), max(vals + [0])
    pad = max(0.5, 0.06 * (hi - lo))
    lo, hi = lo - pad, hi + pad
    left, top, rh, w = 300, 14, 28, 1080
    right = 230
    h = top + len(order) * rh + 34
    s = Svg(w, h, title)
    X = lambda v: left + (v - lo) / (hi - lo) * (w - left - right)
    for tk in nice_ticks(lo, hi, 8):
        s.line(X(tk), top - 6, X(tk), h - 28, "grid")
        s.text(X(tk), h - 12, f"{tk:g}", "t-muted", "middle")
    s.add(f'<line x1="{X(0):.1f}" y1="{top - 6}" x2="{X(0):.1f}" y2="{h - 28}" class="zero"/>')
    s.text(w - right + 12, h - 12, unit, "t-muted")
    for k, cid in enumerate(order):
        y = top + k * rh + rh / 2
        c = Wd["cand"][cid]
        col = TYPE_COL[arm_type(c)]
        s.add(f'<circle cx="{left - 268}" cy="{y:.1f}" r="5" fill="{col}"/>')
        s.text(left - 258, y + 4, cid.replace("/", " · "), "t-small")
        if cid not in R["effects"]:
            f = R["numerically_failed_arms"][cid]
            t = f"{cid}: numerical failure, {f['n_nonfinite']} of {f['n_runs']} runs non-finite (NaN/Inf at dt 0.05 ms). Excluded from effects and ranking."
            s.add(f'<g class="mark" {tip(t)}>'
                  f'<rect x="{left}" y="{y - rh / 2 + 3:.1f}" width="{w - left - right}" height="{rh - 6}" rx="4" class="failbox"/>'
                  f'<text x="{left + 10}" y="{y + 4:.1f}" class="t-small t-critical">✕ numerical failure: {f["n_nonfinite"]}/{f["n_runs"]} runs non-finite, excluded</text></g>')
            continue
        e = R["effects"][cid][fld]
        t = f"{cid}: median {sg(e['median'], nd)} {unit}, 5–95% range {sg(e['p05'], nd)} to {sg(e['p95'], nd)} across {R['effects'][cid]['n_samples']} optima"
        g = f'<g class="mark" {tip(t)}>'
        g += f'<rect x="{left}" y="{y - rh / 2:.1f}" width="{w - left - right}" height="{rh}" fill="transparent"/>'
        if e["p95"] > e["p05"]:
            g += f'<rect x="{X(e["p05"]):.1f}" y="{y - 4:.1f}" width="{X(e["p95"]) - X(e["p05"]):.1f}" height="8" rx="4" fill="{col}" opacity="0.28"/>'
        g += "</g>"
        s.add(g)
        n = len(Wd["per"][cid])
        for j, x in enumerate(Wd["per"][cid]):
            jy = (j - (n - 1) / 2) / max(1, n - 1) * 14
            t = f"{cid} · optimum {x['sid']}: {sg(x[key], nd)} {unit} vs its own baseline"
            s.add(f'<circle cx="{X(x[key]):.1f}" cy="{y + jy:.1f}" r="2.6" fill="{col}" opacity="0.55" class="mark" {tip(t)}/>')
        t = f"{cid}: median {sg(e['median'], nd)} {unit}"
        s.add(f'<rect x="{X(e["median"]) - 2:.1f}" y="{y - 9:.1f}" width="4" height="18" rx="1.5" fill="{col}" class="ring mark" {tip(t)}/>')
        s.text(w - right + 12, y + 4, rng(e, nd), "t-small")
    return s.render()


def fig_frac(rows, title, note_fn):
    """rows: (cid, color, value 0-1 or None, failed text). Horizontal bars on 0-100%."""
    left, top, rh, w, right = 300, 12, 24, 1080, 120
    h = top + len(rows) * rh + 32
    s = Svg(w, h, title)
    X = lambda v: left + v * (w - left - right)
    for tk in range(0, 101, 10):
        s.line(X(tk / 100), top - 4, X(tk / 100), h - 26, "grid")
        s.text(X(tk / 100), h - 10, f"{tk}%", "t-muted", "middle")
    for k, (cid, col, v, failed) in enumerate(rows):
        y = top + k * rh
        s.add(f'<circle cx="{left - 268}" cy="{y + rh / 2:.1f}" r="5" fill="{col}"/>')
        s.text(left - 258, y + rh / 2 + 4, cid.replace("/", " · "), "t-small")
        if failed:
            s.text(left + 6, y + rh / 2 + 4, failed, "t-small t-critical")
            continue
        if v > 0:
            s.add(f'<rect x="{left + 1}" y="{y + 5}" width="{max(2, X(v) - left - 2):.1f}" height="{rh - 10}" rx="3" fill="{col}" class="mark" {tip(note_fn(cid, v))}/>')
        else:
            s.add(f'<rect x="{left}" y="{y}" width="{w - left - right}" height="{rh}" fill="transparent" class="mark" {tip(note_fn(cid, v))}/>')
        s.text(X(v) + 8, y + rh / 2 + 4, pct(v), "t-small")
    return s.render()


def fig_lanes(lanes, title, xlab, thr=None, thr_lab="", integer=False):
    """lanes: (label, [(value, tip)], color). One dot per optimum per lane, on one shared x axis."""
    vals = [v for _, pts, _ in lanes for v, _ in pts] + ([thr] if thr is not None else [])
    lo, hi = min(vals), max(vals)
    pad = 0.5 if integer else 0.05 * (hi - lo or 1)
    lo, hi = (lo - pad, hi + pad)
    left, top, lane, w = 190, 26, 54, 1080
    h = top + lane * len(lanes) + 40
    s = Svg(w, h, title)
    X = lambda v: left + (v - lo) / (hi - lo) * (w - left - 40)
    for tk in nice_ticks(lo, hi, 8):
        if integer and abs(tk - round(tk)) > 1e-9:
            continue
        s.line(X(tk), top - 6, X(tk), h - 34, "grid")
        s.text(X(tk), h - 18, f"{tk:g}", "t-muted", "middle")
    s.text(w - 40, h - 2, xlab, "t-muted", "end")
    if thr is not None:
        s.add(f'<line x1="{X(thr):.1f}" y1="{top - 14}" x2="{X(thr):.1f}" y2="{h - 34}" class="thresh"/>')
        s.text(X(thr) + 6, top - 8, thr_lab, "t-muted")
    for k, (lab, pts, col) in enumerate(lanes):
        y0 = top + k * lane + lane / 2
        s.text(left - 14, y0 + 4, lab, "t-small", "end")
        tot = {}
        for v, _ in pts:
            tot[round(v, 3)] = tot.get(round(v, 3), 0) + 1
        cnt = {}
        for k, (v, t) in enumerate(pts):
            key = round(v, 3)
            j = cnt.get(key, 0)
            cnt[key] = j + 1
            r = 5
            if integer and tot[key] > 5:  # a dense stack becomes one larger dot labelled with its count
                if j == 0:
                    s.add(f'<circle cx="{X(v):.1f}" cy="{y0:.1f}" r="7" fill="{col}" class="ring mark" {tip(f"{tot[key]} optima: {v:g} seizing regions")}/>')
                continue
            if integer:
                dy = (j - (tot[key] - 1) / 2) * 7
            else:
                dy = ((k * 7) % 9 - 4) * 2.2
            s.add(f'<circle cx="{X(v):.1f}" cy="{y0 + dy:.1f}" r="{r}" fill="{col}" class="ring mark" {tip(t)}/>')
        if integer:
            for key, n in tot.items():
                if n > 1:
                    s.text(X(key) + 10, y0 + 4, f"×{n}", "t-muted")
    return s.render()


# --------------------------------------------------------------------------- signal payload for the canvases
def enc_u8(a):
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.uint8).tobytes()).decode()


def enc_i16(a):
    return base64.b64encode(np.ascontiguousarray(a, dtype="<i2").tobytes()).decode()


def signal_data(w, Wd, lut):
    z = np.load(B / f"{w}_signals_median_sample.npz", allow_pickle=False)
    ch = [str(c) for c in z["ch_names"]]
    t = z["BASELINE__t_ms"].astype(float)
    arms = ["BASELINE"] + [c["id"] for c in Wd["C"]["candidates"]]
    U = {a: z[f"{npz_key(a)}__u1"].astype(float) for a in arms}
    X = {a: z[f"{npz_key(a)}__seeg"].astype(float) for a in arms}
    for a in arms:
        assert np.allclose(z[f"{npz_key(a)}__t_ms"], t)
    d = Wd["R"]["derived"]
    targets = set(d["ez_set"]) | set(d["pz"]) | {d["top1"]}
    umax = np.nanmax(np.stack([np.nanmax(U[a], 0) for a in arms]), 0)
    active = {int(i) for i in np.where(umax >= -1.0)[0]}
    rows = set(targets) | active
    for i in np.argsort(-umax):
        if len(rows) >= 18:
            break
        rows.add(int(i))
    if len(rows) > 40:
        rows = set(targets) | set(sorted(active, key=lambda i: -umax[i])[:40 - len(targets)])
    rows = sorted(rows)
    # channels: the 6 most variable baseline channels plus the stimulating contacts
    sd = np.nanstd(X["BASELINE"], 0)
    stim = [ch.index(n) for n in d["stim2_contact_names"]]
    chans = [int(i) for i in np.argsort(-sd) if int(i) not in stim][:6] + stim
    off = np.nanmedian(X["BASELINE"][:, chans], 0)
    scale = float(max(np.nanpercentile(X["BASELINE"][:, c], 99) - np.nanpercentile(X["BASELINE"][:, c], 1) for c in chans)) or 1.0
    out = {}
    for a in arms:
        u = U[a][:, rows]
        qu = np.clip(np.round((u - U_LO) / (U_HI - U_LO) * 254), 0, 254)
        qu[~np.isfinite(u)] = 255
        x = (X[a][:, chans] - off) / scale
        qx = np.clip(np.round(x * 8000), -32000, 32000)
        qx[~np.isfinite(x)] = -32768
        bad = ~np.isfinite(U[a]).all(1) | ~np.isfinite(X[a]).all(1)
        c = Wd["cand"].get(a)
        if a == "BASELINE":
            run = Wd["base"][Wd["msi"]]
        else:
            run = next(x["run"] for x in Wd["per"][a] if x["i"] == Wd["msi"])
        sz = run["seizures"]
        eff = Wd["R"]["effects"].get(a)
        fail = Wd["R"]["numerically_failed_arms"].get(a)
        out[a] = dict(type=arm_type(c), u=enc_u8(qu.T), x=enc_i16(qx.T), nan_ms=float(t[bad][0]) if bad.any() else None,
                      tgt=[rows.index(i) for i in (c or {}).get("regions", []) if i in rows],
                      stim=None if not c or "amp" not in c else dict(kind=arm_type(c), onset=c.get("onset_ms", 0.0) or 0.0,
                                                                   dur=c.get("duration_ms"), contacts=c.get("contact_names"), amp=c["amp"]),
                      ms=dict(finite=run["finite"], n=sz["n_seizing_regions"], regions=[lut[i] for i in sz["seizing_regions"]],
                              dur=round(sz["total_seizure_duration_s"], 2), onset=sz["first_onset_ms"]),
                      eff=None if not eff else dict(dn=eff["d_n_seizing_regions"], dd=eff["d_total_seizure_duration_s"],
                                                    ab=eff["frac_abolish_all"], n=eff["n_samples"]),
                      fail=None if not fail else f'{fail["n_nonfinite"]} of {fail["n_runs"]} runs non-finite')
    return dict(t=[round(float(v), 1) for v in t], T=len(t), rows=[lut[i] for i in rows], chans=[ch[i] for i in chans],
                stimch=[len(chans) - 2, len(chans) - 1], horizon=Wd["R"]["horizon_ms"], sample=Wd["R"]["median_sample"]["id"],
                order=arms, arms=out)


# --------------------------------------------------------------------------- page
CSS_EXTRA = """
.banner{border:1px solid var(--critical);border-left:6px solid var(--critical);background:var(--surface);padding:12px 16px;border-radius:8px;margin:14px 0;max-width:none}
.banner b.k{color:var(--crittext);letter-spacing:.04em}.banner ul{margin:6px 0 0;padding-left:18px}.banner li{margin:3px 0}
svg .zero{stroke:var(--ink2);stroke-width:1.3}svg .failbox{fill:var(--line2);stroke:var(--critical);stroke-dasharray:4 3}
caption{caption-side:top;text-align:left;font-size:12.5px;color:var(--ink2);padding:8px 10px 2px}
.cgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px 16px}@media(max-width:760px){.cgrid{grid-template-columns:1fr}}
.cpanel .ptitle{font-size:13px;font-weight:600;margin:0 0 4px;display:flex;align-items:center;gap:6px}
canvas.hm,canvas.tr{width:100%;display:block}
.controls{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:4px 0 10px;font-size:13.5px}
.controls select{font:inherit;font-size:13.5px;padding:4px 8px;border-radius:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink)}
.readout{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin:10px 0 0}
.readout .tile .v{font-size:19px}
.cbar{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink2)}
.pill{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);color:var(--ink2)}
.fail{color:var(--crittext)}
"""

JS_SIG = r"""
const D=JSON.parse(document.getElementById('sigdata').textContent);
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function hex(c){c=c.replace('#','');if(c.length===3)c=c.split('').map(x=>x+x).join('');return[0,2,4].map(i=>parseInt(c.substr(i,2),16))}
function b64(s){const b=atob(s),a=new Uint8Array(b.length);for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a}
const cache={};function dec(w,a){const k=w+'|'+a;if(!cache[k]){const r=D[w].arms[a];cache[k]={u:b64(r.u),x:new Int16Array(b64(r.x).buffer)}}return cache[k]}
const TYPECOL={'ablation':'--s1','disconnection':'--s3','sustained current':'--s7','pulse train':'--s2','chronic pulse train':'--s5','baseline':'--ink2'};
const ULO=__ULO__,UHI=__UHI__;
let LUT=null;
const TP=(-1-ULO)/(UHI-ULO);
function buildLut(){const a=hex(css('--surface')),b=hex(css('--s1')),c=hex(css('--ink'));LUT=[];
 for(let i=0;i<255;i++){const v=i/254;let r;if(v<TP){const f=v/TP;r=a.map((x,k)=>x+(b[k]-x)*f)}else{const f=(v-TP)/(1-TP);r=b.map((x,k)=>x+(c[k]-x)*f)}LUT.push(r.map(Math.round))}
 LUT.push(hex(css('--neutral')))}
function setup(cv,h){const dpr=window.devicePixelRatio||1,w=cv.clientWidth||600;cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr);cv.style.height=h+'px';const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);return[g,w]}
function fmtT(ms){return(ms/1000).toFixed(2)+' s'}
function axisT(g,w,x0,x1,y,hz){const step=hz>10000?2000:1000;g.fillStyle=css('--ink2');g.strokeStyle=css('--line');g.font='11px system-ui,sans-serif';g.textAlign='center';
 for(let t=0;t<=hz+1;t+=step){const x=x0+t/hz*(x1-x0);g.beginPath();g.moveTo(x,y);g.lineTo(x,y+4);g.stroke();g.fillText((t/1000)+'',x,y+15)}g.textAlign='right';g.fillText('time (s)',x1,y+28)}
function stimBand(g,s,x0,x1,y0,y1,hz){if(!s)return;let a=s.onset,b=s.dur==null?hz:s.onset+s.dur;const xa=x0+a/hz*(x1-x0),xb=x0+Math.min(b,hz)/hz*(x1-x0);
 g.fillStyle=css(TYPECOL[s.kind]);g.globalAlpha=.85;g.fillRect(xa,y0-7,xb-xa,4);g.globalAlpha=1;g.fillStyle=css('--ink2');g.font='10.5px system-ui,sans-serif';g.textAlign='left';
 const lab=s.kind==='sustained current'?'sustained current, whole horizon':(s.kind==='pulse train'?'50 Hz train':'50 Hz train, whole horizon');g.fillText(lab+' · '+s.contacts.join('+')+' · amp '+s.amp,xa+2,y0-10)}
function nanShade(g,ms,x0,x1,y0,y1,hz){if(ms==null)return;const xa=x0+ms/hz*(x1-x0);g.fillStyle=css('--line2');g.fillRect(xa,y0,x1-xa,y1-y0);g.strokeStyle=css('--critical');g.setLineDash([4,3]);g.beginPath();g.moveTo(xa,y0);g.lineTo(xa,y1);g.stroke();g.setLineDash([]);
 g.fillStyle=css('--crittext');g.font='11px system-ui,sans-serif';g.textAlign='left';g.fillText('non-finite from '+fmtT(ms),Math.min(xa+4,x1-120),y0+12)}
const HM=new Map();
function drawHM(cv,w,a,opt={}){const d=D[w],r=d.arms[a],R=d.rows.length,T=d.T,rh=opt.rh||10,L=opt.left||178,top=26,H=top+R*rh+34;const[g,W]=setup(cv,H);
 const x1=W-8;const o=document.createElement('canvas');o.width=T;o.height=R;const og=o.getContext('2d'),im=og.createImageData(T,R),u=dec(w,a).u;
 for(let i=0;i<R;i++)for(let j=0;j<T;j++){const c=LUT[u[i*T+j]],p=(i*T+j)*4;im.data[p]=c[0];im.data[p+1]=c[1];im.data[p+2]=c[2];im.data[p+3]=255}
 og.putImageData(im,0,0);g.imageSmoothingEnabled=false;g.drawImage(o,L,top,x1-L,R*rh);
 g.font='10.5px system-ui,sans-serif';g.textAlign='right';for(let i=0;i<R;i++){const isT=r.tgt.includes(i);g.fillStyle=isT?css(TYPECOL[r.type]):css('--ink');g.font=(isT?'600 ':'')+'10.5px system-ui,sans-serif';g.fillText(d.rows[i]+(isT?' ●':''),L-6,top+i*rh+rh-2)}
 stimBand(g,r.stim,L,x1,top,top+R*rh,d.horizon);axisT(g,W,L,x1,top+R*rh+2,d.horizon);
 if(r.nan_ms!=null){const xa=L+r.nan_ms/d.horizon*(x1-L);g.strokeStyle=css('--critical');g.setLineDash([4,3]);g.beginPath();g.moveTo(xa,top);g.lineTo(xa,top+R*rh);g.stroke();g.setLineDash([]);g.fillStyle=css('--crittext');g.textAlign='right';g.font='11px system-ui,sans-serif';g.fillText('non-finite from '+fmtT(r.nan_ms),x1,top-10)}
 HM.set(cv,{w,a,L,x1,top,rh,R,T})}
function drawTR(cv,w,a,opt={}){const d=D[w],r=d.arms[a],C=d.chans.length,T=d.T,lh=opt.lh||30,L=opt.left||70,top=26,H=top+C*lh+34;const[g,W]=setup(cv,H);const x1=W-8;
 const X=j=>L+j/(T-1)*(x1-L);const tr=(arr,col,lw,alpha)=>{g.strokeStyle=col;g.lineWidth=lw;g.globalAlpha=alpha;for(let c=0;c<C;c++){const y0=top+c*lh+lh/2;g.beginPath();let pen=false;for(let j=0;j<T;j++){const v=arr[c*T+j];if(v===-32768){pen=false;continue}const y=y0-Math.max(-.9,Math.min(.9,v/8000))*lh*.95;if(pen)g.lineTo(X(j),y);else{g.moveTo(X(j),y);pen=true}}g.stroke()}g.globalAlpha=1};
 g.font='10.5px system-ui,sans-serif';g.textAlign='right';for(let c=0;c<C;c++){const st=d.stimch.includes(c);g.fillStyle=st?css('--ink'):css('--ink2');g.font=(st?'600 ':'')+'10.5px system-ui,sans-serif';g.fillText(d.chans[c]+(st?' ⚡':''),L-6,top+c*lh+lh/2+4)}
 nanShade(g,r.nan_ms,L,x1,top,top+C*lh,d.horizon);
 if(a!=='BASELINE'&&opt.overlay!==false)tr(dec(w,'BASELINE').x,css('--neutral'),1,.9);
 tr(dec(w,a).x,css(TYPECOL[r.type]),1.15,1);stimBand(g,r.stim,L,x1,top,top+C*lh,d.horizon);axisT(g,W,L,x1,top+C*lh+2,d.horizon)}
const tipE=document.getElementById('tip');
document.addEventListener('mousemove',e=>{const cv=e.target;if(!(cv instanceof HTMLCanvasElement)||!HM.has(cv))return;const m=HM.get(cv),b=cv.getBoundingClientRect(),x=e.clientX-b.left,y=e.clientY-b.top;
 if(x<m.L||x>m.x1||y<m.top||y>m.top+m.R*m.rh){tipE.style.opacity=0;return}const i=Math.floor((y-m.top)/m.rh),j=Math.min(m.T-1,Math.floor((x-m.L)/(m.x1-m.L)*m.T)),d=D[m.w],q=dec(m.w,m.a).u[i*m.T+j];
 tipE.textContent=d.rows[i]+' · t = '+fmtT(d.t[j])+' · '+(q===255?'non-finite':('u1 ≈ '+(ULO+q/254*(UHI-ULO)).toFixed(2)+(ULO+q/254*(UHI-ULO)>-1?' (above −1 seizure threshold)':' (below −1)')));tipE.style.opacity=1;
 const tw=tipE.offsetWidth,th=tipE.offsetHeight;let tx=e.clientX+14,ty=e.clientY+14;if(tx+tw>innerWidth-8)tx=e.clientX-tw-14;if(ty+th>innerHeight-8)ty=e.clientY-th-14;tipE.style.left=tx+'px';tipE.style.top=ty+'px'});
function cbar(cv){const[g,W]=setup(cv,30);const x0=4,x1=W-4;for(let i=0;i<255;i++){const c=LUT[i];g.fillStyle=`rgb(${c[0]},${c[1]},${c[2]})`;g.fillRect(x0+i/255*(x1-x0),2,(x1-x0)/255+1,12)}
 g.fillStyle=css('--ink2');g.font='10.5px system-ui,sans-serif';g.textAlign='left';g.fillText('≤ '+ULO.toFixed(1),x0,27);g.textAlign='right';g.fillText(UHI.toFixed(1),x1,27);g.textAlign='center';const xt=x0+(-1-ULO)/(UHI-ULO)*(x1-x0);g.fillText('−1 threshold',xt,27);g.fillStyle=css('--critical');g.fillRect(xt-1,0,2,16)}
function fmtR(e){const f=v=>{const r=Math.round(v*10)/10;return r===0?'0':(r>0?'+':'')+r.toFixed(1)};return f(e.median)+' ['+f(e.p05)+', '+f(e.p95)+']'}
function explorer(){const w=document.getElementById('xw').value,sel=document.getElementById('xa');const keep=sel.value;sel.innerHTML='';const groups={};
 D[w].order.slice(1).forEach(a=>{const r=D[w].arms[a];(groups[r.type]=groups[r.type]||[]).push(a)});
 for(const t of['ablation','disconnection','sustained current','pulse train','chronic pulse train']){if(!groups[t])continue;const og=document.createElement('optgroup');og.label=t;groups[t].forEach(a=>{const o=document.createElement('option');o.value=a;o.textContent=a.replace('/',' · ')+(D[w].arms[a].fail?'  (numerical failure)':'');og.appendChild(o)});sel.appendChild(og)}
 sel.value=D[w].arms[keep]?keep:'RES-EZ+PZ/ablation';drawX()}
function drawX(){const w=document.getElementById('xw').value,a=document.getElementById('xa').value,d=D[w],r=d.arms[a],b=d.arms.BASELINE;
 document.getElementById('xc-t').textContent=a.replace('/',' · ');document.getElementById('xc-sw').style.background=css(TYPECOL[r.type]);
 drawHM(document.getElementById('xh0'),w,'BASELINE',{rh:9});drawHM(document.getElementById('xh1'),w,a,{rh:9});drawTR(document.getElementById('xt0'),w,'BASELINE');drawTR(document.getElementById('xt1'),w,a);
 const reg=m=>m.n?m.regions.join(', '):'none';const out=[
 ['Median optimum',d.sample+' ('+(w==='post'?'post window, 7.76 s':'full window, 14.4 s')+')'],
 ['Seizing regions: before → after',b.ms.n+' → '+r.ms.n+(r.ms.finite?'':' (run non-finite)')],
 ['Total seizure duration: before → after',b.ms.dur.toFixed(1)+' s → '+r.ms.dur.toFixed(1)+' s'],
 ['Seizing before',reg(b.ms)],['Seizing after',reg(r.ms)],
 ['Ensemble Δ seizing regions, median [5–95%]',r.eff?fmtR(r.eff.dn)+' over '+r.eff.n+' optima':'not computed: '+r.fail],
 ['Ensemble Δ total duration (s)',r.eff?fmtR(r.eff.dd):'not computed: '+r.fail],
 ['Optima with all seizures abolished',r.eff?(w==='post'?'trivial: no baseline seizures':Math.round(100*r.eff.ab)+'%'):'—']];
 document.getElementById('xr').innerHTML=out.map(([k,v])=>`<div class="tile"><div class="k">${k}</div><div class="v" style="font-size:${v.length>40?13.5:18}px">${v.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div></div>`).join('')}
function drawAll(){buildLut();document.querySelectorAll('canvas[data-hm]').forEach(c=>drawHM(c,c.dataset.w,c.dataset.hm));document.querySelectorAll('canvas[data-tr]').forEach(c=>drawTR(c,c.dataset.w,c.dataset.tr));document.querySelectorAll('canvas.cb').forEach(cbar);if(document.getElementById('xa').value)drawX()}
document.getElementById('xw').addEventListener('change',explorer);document.getElementById('xa').addEventListener('change',drawX);
document.querySelector('.themebtn').addEventListener('click',()=>setTimeout(drawAll,0));matchMedia('(prefers-color-scheme: dark)').addEventListener('change',drawAll);
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(drawAll,150)});
buildLut();explorer();drawAll();
"""


def build(out):
    P, lut, W = load()
    st = ctl.load_state(ctl.study_dir(STUDY))
    arts, tasks = st["artifacts"], st["tasks"]
    man = jload(B / "manifest.json")
    F, Pw = W["full"], W["post"]
    Rf, Rp = F["R"], Pw["R"]
    spec_p = SD / "work/amend/r4_common_spec.json"
    sim_p = SD / "work/T0015/sim/p2sim.py"
    npz_p = ROOT / "data/wang-5367ef4/data/dataSim/Patient2/P2_SEEG_ts_fit.npz"
    spec_sha, sim_sha, npz_sha = sha(spec_p), sha(sim_p), sha(npz_p)
    spec = jload(spec_p)
    A = lambda aid: jload(ART / aid / "payload.json")
    a37, a18, a19 = A("A0037-ModelBundle"), A("A0018-ModelBundle"), A("A0019-ModelBundle")
    n_sims = {w: len(W[w]["runs"]["baselines"]) + len(W[w]["runs"]["candidates"]) for w in WINDOWS}
    n_fail = {w: len(W[w]["R"]["numerically_failed_arms"]) for w in WINDOWS}
    best = Rf["ranking"][0]
    eb = Rf["effects"][best]
    qual = {w: W[w]["R"]["qualitative_check_vs_recording"] for w in WINDOWS}
    last_ts = st["events"][-1]["ts"] if st.get("events") else ""
    fig = iter(range(1, 50))
    H = []

    # ---------------------------------------------------------------- header
    reasons37 = a37["qualification_verdict"]["reasons"]
    H.append(f"""<header class="top"><button class="themebtn" type="button">Toggle light / dark</button>
<div class="who">Study-002 · R4 intervention design and simulation · virtual Patient 2</div>
<h1>Virtual surgery and stimulation on Patient 2: simulation results (A0038)</h1>
<p class="lead">Every prespecified virtual treatment (ablation, disconnection, SEEG sustained-current and 50 Hz pulse-train stimulation) was simulated on the A0018 MAP ensemble with a TVB re-implementation of the Wang et al. 2025 stimulation model. Each treatment is compared with the no-treatment run of the same model optimum.</p>
<div class="meta"><span>Batch <code>A0038-SimulationBatch</code> · committed by R4 in task T0017, finished {E(tasks["T0017"]["finished_at"][11:16])} UTC</span><span>Gate status: {badge(arts["A0038-SimulationBatch"]["effective_validation"])}</span><span>Ledger snapshot {E(last_ts[:16].replace("T", " "))} UTC (study still running)</span><span>Release <code>{E(man["system_release_id"])}</code></span></div>
<div class="banner" role="note"><b class="k">EXPLORATORY: MODEL NOT QUALIFIED.</b> These are research simulations on a virtual patient, not clinical recommendations. No prediction may be frozen on this batch.
<ul><li><b>The inversion model failed its benchmark.</b> A0037 (R3's synthetic qualification benchmark of the v2 AR(1) model): <b>{E(a37["qualification_verdict"]["arm_A"])}</b>. {E(reasons37[0])}; {E(reasons37[1].split(":")[0])}. R5's gate on A0037 is still pending.</li>
<li><b>The simulated patient does not look like the recording.</b> In the median optimum, the 10 most active simulated SEEG channels share <b>{qual["post"]["simulated"]["BASELINE"]["overlap_with_observed_top10"]}/10</b> (post window) and <b>{qual["full"]["simulated"]["BASELINE"]["overlap_with_observed_top10"]}/10</b> (full window) channels with the recording. The simulated recorded protocol (STIM-PT amp 1) also overlaps 0/10.</li>
<li><b>The inputs are not a posterior.</b> A0018 is a preliminary MAP ensemble of optimizer end points, not posterior draws, and it is not qualified. The NUTS fit A0019 did not converge in either window.</li></ul></div>
<nav class="toc" aria-label="Sections"><a href="#findings">Findings</a><a href="#design">1 Design</a><a href="#before-after">2 Before / after</a><a href="#effects">3 Effects</a><a href="#windows">4 Two windows</a><a href="#failures">5 Failures and deviations</a><a href="#ti">6 TI</a><a href="#repro">7 Reproducibility</a></nav></header>""")

    H.append(f"""<div class="tiles">
<div class="tile"><div class="v">{len(F["C"]["candidates"])}</div><div class="k">candidate arms per window, each paired with its own baseline</div></div>
<div class="tile"><div class="v">{n_sims["post"] + n_sims["full"]}</div><div class="k">simulations ({n_sims["post"]} post + {n_sims["full"]} full)</div></div>
<div class="tile"><div class="v">{Rp["n_samples"]} / {Rf["n_samples"]}</div><div class="k">model optima simulated (post / full; full limited to 12 of 24)</div></div>
<div class="tile"><div class="v">{eb["d_n_seizing_regions"]["median"]:+.1f}</div><div class="k">seizing regions, best arm ({E(best)}), full window median</div></div>
<div class="tile"><div class="v">{pct(eb["frac_abolish_all"])}</div><div class="k">of full-window optima with all seizures abolished by that arm</div></div>
<div class="tile"><div class="v fail">{n_fail["post"] + n_fail["full"]}</div><div class="k">arm × window results lost to numerical failure (high-amplitude pulse trains)</div></div></div>""")

    # ---------------------------------------------------------------- findings
    stim1 = [Rf["effects"][k]["d_n_seizing_regions"]["median"] for k in Rf["effects"] if k.startswith(("STIM-1", "STIM-2"))]
    chron = [Rf["effects"][k]["d_total_seizure_duration_s"]["median"] for k in Rf["effects"] if k.startswith("STIM-PT-chronic")]
    ez_names = [lut[i] for i in Rf["derived"]["ez_set"]]
    H.append(f"""<h2 id="findings">Findings</h2>
<div class="cols"><div class="card"><h3>For clinicians</h3><ul>
<li><b>The primary (post-stimulation) window is uninformative.</b> None of the {Rp["n_samples"]} model optima seized without treatment, so no treatment could reduce anything. All {len(Rp["tied_first"])} finite arms tie for first.</li>
<li><b>In the full-window sensitivity analysis</b> ({Rf["n_samples"]} optima, median {Rf["baseline_summary"]["n_seizing_regions"]["median"]:g} seizing regions without treatment), removing the estimated EZ plus the two propagation regions (9 regions) helped most: median <b>{eb["d_n_seizing_regions"]["median"]:+.1f}</b> seizing regions (5–95%: {eb["d_n_seizing_regions"]["p05"]:+.1f} to {eb["d_n_seizing_regions"]["p95"]:+.1f}). It abolished all seizures in {pct(eb["frac_abolish_all"])} of optima.</li>
<li><b>Disconnecting the same regions was weaker than ablating them</b> (median {Rf["effects"]["RES-EZ+PZ/disconnection"]["d_n_seizing_regions"]["median"]:+.1f}).</li>
<li><b>Sustained-current SEEG stimulation</b> at contact {E(Rf["derived"]["stim1_contact_name"])} gave {min(stim1):+.1f} to {max(stim1):+.1f} regions and never abolished seizures.</li>
<li><b>50 Hz pulse trains did not reduce seizing regions.</b> Applied for the whole horizon they lengthened total seizure time (median {min(chron):+.1f} to {max(chron):+.1f} s). The higher amplitudes failed numerically.</li>
<li>Targets are model regions ({E(", ".join(ez_names))}), not surgical volumes. Amplitudes are model units, not mA.</li></ul></div>
<div class="card"><h3>For engineers</h3><ul>
<li>The simulator is <code>p2sim 1.0</code>: TVB 2.10 at region level, the package <code>SpatEpiStim</code> model, Heun integration at dt 0.05 ms, Heaviside coupling a = 0.1·K, and gain-weighted biphasic 50 Hz <code>StimuliRegion</code>. Its self-test reproduces the package equations bitwise (T0015).</li>
<li>Every candidate was paired with its own baseline: same x0, K, initial state, horizon and noise seed. Effects are candidate minus baseline per optimum. They were recomputed in <code>finalize.py</code> over finite runs only, with explicit ties. This page re-derives each median and 5–95% range from the per-run file and checks it against the payload.</li>
<li>Pulse-train arms with Istim ≥ 0.02–0.04 at the max-gain region went NaN at dt 0.05 ms. They are reported as failures, not dropped.</li>
<li>The x0 values come from a 2D-Epileptor fit and were inserted into the 6D+m generator model. This mismatch, together with the failed benchmark, is the main threat to validity.</li></ul></div></div>""")

    # ---------------------------------------------------------------- 1 design
    s = Rf["meta"]["settings"]
    pa9 = A("A0009-PatientCase")
    rec = pa9["recordings"][0]
    plans = [("A0020", "A0021"), ("A0022", "A0023"), ("A0024", "A0025"), ("A0026", "A0027"), ("A0028", "A0029"), ("A0030", "A0031"), ("A0032", "A0033")]
    plan_rows = []
    for p_id, f_id in plans:
        pk = next(a for a in arts if a.startswith(p_id))
        fk = next(a for a in arts if a.startswith(f_id))
        pp, fp = A(pk), A(fk)
        plan_rows.append([f"<code>{p_id}</code> / <code>{f_id}</code>", E(pp["intervention_id"]), E(pp.get("description") or pp["intervention_class"]),
                          badge("failed" if fp["verdict"] == "infeasible" else "passed", fp["verdict"].replace("_", " ")),
                          E("; ".join(fp["verdict_reasons"]))])

    def targets(w, c):
        if "regions" in c:
            return ", ".join(lut[i] for i in c["regions"])
        return ", ".join(c["contact_names"]) + " (contact)"

    def schedule(c):
        t = arm_type(c)
        if t in ("ablation", "disconnection"):
            return "x0 → −3.0 (healthy)" if t == "ablation" else "SC rows and columns → 0"
        if t == "sustained current":
            return f"I_hyp = {c['amp']:g} × normalised gain, 0 → end"
        on, du = c["onset_ms"] / 1000, c["duration_ms"]
        return f"50 Hz biphasic, amp {c['amp']:g} (Istim {c['amp'] * s['pt_istim_per_unit']:g}), " + (f"{on:g}–{on + du / 1000:g} s" if du else "0 → end")

    cand_rows = []
    for c in F["C"]["candidates"]:
        cp = Pw["cand"][c["id"]]
        cand_rows.append([f'<span class="sw" style="background:{TYPE_COL[arm_type(c)]}"></span> <b>{E(c["id"])}</b>', E(arm_type(c)),
                          E(targets("post", cp)), E(targets("full", c)), E(schedule(c)), "primary" if c.get("primary", True) else "secondary"])
    ez_rows = []
    for w in WINDOWS:
        d, e = W[w]["R"]["derived"], W[w]["R"]["ez_estimate"]
        ez_rows.append([w, f'{e["n_optima"]}', E(lut[d["top1"]]), E(", ".join(lut[i] for i in d["ez_set"])) + ("" if e["ez_set"] else " (no region passed −2.06 in > 50% of optima; fell back to top-1)"),
                        E(", ".join(d["pz_names"])), E(f'{d["stim1_contact_name"]}; STIM-2: {" + ".join(d["stim2_contact_names"])}')])
    H.append(f"""<h2 id="design">1 · Design</h2>
<h3>The virtual patient</h3>
<p>Patient 2 is Wang et al. 2025's simulated "virtual patient" (<code>dataSim/Patient2</code>, case record A0009). It has a {pa9["recordings"][0]["keys"]["SC"][0][0]}-region VEP-atlas connectome, a {rec["n_channels"]}-channel bipolar SEEG gain matrix, and a {rec["duration_ms"] / 1000:g} s simulated recording at {rec["sample_rate_hz"]:g} Hz that contains a 50 Hz SEEG stimulation train from 0.5 to 3.5 s. There is no MRI and there are no electrode coordinates, so every target is a whole atlas region or a contact identified by its gain row. Its ground truth is sealed in the study vault and was not used here.</p>
<p>The model input is the A0018 MAP ensemble: 24 L-BFGS optima per fitted window. R3 named two windows before fitting: <b>post</b> (after the stimulation train, primary, horizon {Rp["horizon_ms"] / 1000:g} s) and <b>full</b> (whole recording, sensitivity, horizon {Rf["horizon_ms"] / 1000:g} s). Each horizon is twice the fitted window length.</p>
{tbl(["Window", "Optima used for the estimate", "Top-1 EZ region (RES-1)", "EZ set (RES-EZ)", "Propagation regions added (RES-EZ+PZ)", "Stimulating contacts (STIM-1 / STIM-PT)"], ez_rows,
     caption="Targets derived by R4 from A0018 with the prespecified rules (top-1 = highest median x0; EZ set = x0 > −2.06 in more than half of the optima). Source: payload.results.*.ez_estimate / derived.")}
<p class="fig-cap">A0018 itself warns that region 82 (Right-Orbito-frontal-cortex) carries the implant's largest gain (R7-8), so its top-1 rank may reflect gain leverage rather than excitability.</p>
<h3>Simulator (paper method, T0015)</h3>
{tbl(["Setting", "Value", "Note"], [
        ["Engine", "TVB 2.10.0 Simulator, region level (162 nodes)", "p2sim 1.0, sha256 " + sim_sha[:12] + "…"],
        ["Neural mass", "vep_stim SpatEpiStim (u1, u2, s, q1, q2, g, m)", "Stimulus enters u1 as +400·Istim, and the accumulator m raises excitability when m > 1.8"],
        ["Integrator", f"HeunDeterministicAdapted, dt {s['dt_ms']} ms", "Deterministic, no dynamics noise. dt 0.1 ms was inaccurate under 1 ms pulse phases"],
        ["Coupling", f"Heaviside, a = {s['coupling_a0']}·K, θ = {s['coupling_theta']}", "K from each optimum. a = 0.1·K is an R4 mapping convention"],
        ["Initial state", "Uncoupled healthy equilibrium at x0 = −3, identical for all nodes and arms", "payload.initial_states"],
        ["Monitor", f"TemporalAverage {s['monitor_period_ms']} ms; saved signals at {s['save_period_ms']} ms (50 Hz)", "The 50 Hz pulse artefact averages out in saved signals"],
        ["SEEG", "gain @ (q1 − u1)", f"N(0, {s['seeg_noise_sd']}) observation noise for the log-power metric only, seed 1000 + sample index"],
        ["Seizure", f"u1 > {s['seizure_threshold']} recurring within {s['seizure_gap_ms']:g} ms, sustained ≥ {s['seizure_min_ms'] / 1000:g} s", "Stimulus-driven u1 excursions sustained ≥ 1 s count too"],
        ["Pulse train", f"{s['pt_freq_hz']:g} Hz biphasic, {s['pt_phase_ms']:g} ms per phase, train {s['pt_onset_ms'] / 1000:g}–{(s['pt_onset_ms'] + s['pt_duration_ms']) / 1000:g} s", f"1 model unit = Istim {s['pt_istim_per_unit']} at the max-gain region"],
        ["Horizons", f"post {Rp['horizon_ms']:g} ms · full {Rf['horizon_ms']:g} ms", "2 × fitted window"]],
     caption="From payload.solver_settings and meta.settings; model description from the p2sim.py header.")}
<h3>Candidates</h3>
<p>All {len(F["C"]["candidates"])} arms were run in both windows. Ablation is the primary implementation for surgery, and disconnection is secondary. Stimulation amplitudes are model units. Sham is the baseline itself, because the model is deterministic.</p>
{tbl(["Arm", "Type", "Targets · post", "Targets · full", "Implementation", "Role"], cand_rows, raw_cols=(0,))}
<h3>Plans and feasibility (T0015, committed before any P2 model existed)</h3>
{tbl(["Records", "Plan", "Rule", "Feasibility", "Reasons"], plan_rows, raw_cols=(0, 3))}
<h3>Prespecification</h3>
<ul><li>Common spec <code>work/amend/r4_common_spec.json</code>, {E(spec["version"].split(" ")[0])} (written {E(spec["version"].split("(")[1].split(",")[0])}), sha256 <code>{spec_sha}</code>. This matches the hash recorded in every plan and in the batch metadata ({"✓ match" if spec_sha == Rf["meta"]["spec_sha256"] else "✕ MISMATCH"}).</li>
<li>Effect: {E(spec["effect"])}</li>
<li>Ranking: {E(spec["ranking"])}</li>
<li>Scenario set A0034 and request A0035 were committed at the start of T0017, before any result. The stopping rule was: {E(A("A0035-SimulationRequest")["stopping_criteria"])}.</li></ul>""")

    # ---------------------------------------------------------------- 2 before / after
    SIG = {w: signal_data(w, W[w], lut) for w in WINDOWS}
    dF = SIG["full"]
    panels_hm, panels_tr = [], []
    for a in STATIC_ARMS:
        r = dF["arms"][a]
        col = TYPE_COL[r["type"]]
        lab = "Before: no treatment" if a == "BASELINE" else f"After: {a.replace('/', ' · ')}"
        sub = f'{r["ms"]["n"]} seizing regions, {r["ms"]["dur"]:.1f} s total'
        panels_hm.append(f'<div class="cpanel"><div class="ptitle"><span class="sw" style="background:{col}"></span>{E(lab)} <span class="pill">{E(r["type"])}</span> <span class="pill">{E(sub)}</span></div>'
                         f'<canvas class="hm" data-w="full" data-hm="{E(a)}" role="img" aria-label="Region activity heatmap, {E(lab)}, full window, median optimum"></canvas></div>')
        panels_tr.append(f'<div class="cpanel"><div class="ptitle"><span class="sw" style="background:{col}"></span>{E(lab)}</div>'
                         f'<canvas class="tr" data-w="full" data-tr="{E(a)}" role="img" aria-label="Simulated SEEG traces, {E(lab)}, full window, median optimum"></canvas></div>')
    cb = '<span class="cbar">u1 <canvas class="cb" style="width:260px;height:30px" aria-hidden="true"></canvas></span>'
    H.append(f"""<h2 id="before-after">2 · Before and after: the median optimum</h2>
<p>These panels show the full window's median optimum <code>{E(dF["sample"])}</code> (median by baseline seizure count). Rows are the {len(dF["rows"])} regions (of 162 simulated) that cross u1 = −1 in any arm, plus every targeted region. Colour is the fast variable u1 on one shared scale (colour bar): background-like is rest, blue is the −1 threshold, and the strongest contrast is above it. ● marks a region removed by that arm. Hover a heatmap for region, time and value.</p>
<p>A dark band means u1 went above −1. A region counts as <i>seizing</i> only when such excursions recur within 250 ms for at least 1 s, so the short rhythmic discharges seen in many rows are not counted as seizures.</p>
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Region activity before and after, one panel per treatment family (full window)</figcaption>
<div class="legend">{cb}<span class="lg"><span class="sw" style="background:var(--neutral)"></span>non-finite</span></div>
<div class="cgrid">{"".join(panels_hm)}</div>
<p class="fig-cap">In this optimum, ablation and disconnection of the EZ + PZ regions (9 regions) both leave 0 seizing regions. Short, regular discharges continue in the regions left in place. Pulse trains and sustained current leave the baseline pattern largely intact; sustained current lightens the regions next to R7-8. Values at or below −2.2 (hyperpolarised regions) share the lightest colour. Each stimulation family is shown at amplitude 1; all amplitudes are in the explorer below. Source: <code>full_signals_median_sample.npz</code> (<code>*__u1</code>, 50 Hz).</p></figure>
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Simulated SEEG before and after (full window, same scale in every panel)</figcaption>
{legend_html([("baseline (overlaid grey in each treatment panel)", "var(--neutral)", "line"), ("ablation", TYPE_COL["ablation"], "line"), ("disconnection", TYPE_COL["disconnection"], "line"), ("sustained current", TYPE_COL["sustained current"], "line"), ("pulse train", TYPE_COL["pulse train"], "line"), ("chronic pulse train", TYPE_COL["chronic pulse train"], "line")])}
<div class="cgrid">{"".join(panels_tr)}</div>
<p class="fig-cap">Channels shown: the 6 bipolar channels with the largest baseline variance, plus the stimulating contacts {E(" and ".join(Rf["derived"]["stim2_contact_names"]))} (⚡). Signals are gain @ (q1 − u1) at 50 Hz with the baseline median removed, on one shared scale; the 50 Hz pulse artefact averages out at this rate. The coloured bar above a panel marks when stimulation is on. Source: <code>*__seeg</code>.</p></figure>
<figure class="fig"><figcaption class="fig-title"><span class="fig-num">Figure {next(fig)}</span> Explorer: any arm in either window, against its paired baseline</figcaption>
<div class="controls"><label>Window <select id="xw"><option value="full">full (sensitivity, 12 optima, 14.4 s)</option><option value="post">post (primary, 24 optima, 7.76 s)</option></select></label>
<label>Arm <select id="xa"></select></label>{cb}</div>
<div class="cgrid"><div class="cpanel"><div class="ptitle"><span class="sw" style="background:var(--ink2)"></span>Before: no treatment</div><canvas class="hm" id="xh0" role="img" aria-label="Baseline region activity"></canvas><canvas class="tr" id="xt0" role="img" aria-label="Baseline SEEG"></canvas></div>
<div class="cpanel"><div class="ptitle"><span class="sw" id="xc-sw"></span>After: <span id="xc-t"></span></div><canvas class="hm" id="xh1" role="img" aria-label="Region activity with the selected arm"></canvas><canvas class="tr" id="xt1" role="img" aria-label="SEEG with the selected arm"></canvas></div></div>
<div class="readout" id="xr" aria-live="polite"></div>
<p class="fig-cap">The median optimum differs by window: <code>{E(SIG["full"]["sample"])}</code> (full) and <code>{E(SIG["post"]["sample"])}</code> (post). The post window has no seizure in any arm, and its rows are the most active regions. Arms with a numerical failure show their signal up to the first non-finite sample. The tiles give this optimum's before/after values (<code>*_runs.json</code>) and the ensemble effect (payload).</p></figure>""")

    # ---------------------------------------------------------------- 3 effects
    ranking = Rf["ranking"]
    failed_f = list(Rf["numerically_failed_arms"])
    order = ranking + failed_f
    legend_types = legend_html([(k, v, "dot") for k, v in TYPE_COL.items() if k != "baseline"])
    fr_ab = [(c, TYPE_COL[arm_type(F["cand"][c])], Rf["effects"][c]["frac_abolish_all"] if c in Rf["effects"] else None,
              None if c in Rf["effects"] else "✕ numerical failure, not computed") for c in order]
    fr_rk = [(c, TYPE_COL[arm_type(F["cand"][c])], Rf["rank_first_fraction"][c] if c in Rf["effects"] else None,
              None if c in Rf["effects"] else "✕ numerical failure, excluded from ranking") for c in order]
    eff_rows = []
    for k, c in enumerate(order):
        cc = F["cand"][c]
        if c in Rf["effects"]:
            e = Rf["effects"][c]
            on = e["d_first_onset_ms"]
            eff_rows.append([k + 1, f'<span class="sw" style="background:{TYPE_COL[arm_type(cc)]}"></span> {E(c)}', e["n_samples"], rng(e["d_n_seizing_regions"]),
                             rng(e["d_total_seizure_duration_s"]), rng(on, 0) if on else "–", rng(e["d_n_seeg_channels_exceeding"]), pct(e["frac_abolish_all"]),
                             pct(Rf["rank_first_fraction"][c])])
        else:
            f = Rf["numerically_failed_arms"][c]
            eff_rows.append(["–", f'<span class="sw" style="background:{TYPE_COL[arm_type(cc)]}"></span> {E(c)}', f'{f["n_runs"] - f["n_nonfinite"]} finite of {f["n_runs"]}',
                             '<span class="fail">numerical failure, excluded</span>', "", "", "", "", ""])
    H.append(f"""<h2 id="effects">3 · Paired effects (full window, {Rf["n_samples"]} optima)</h2>
<p>Each value is candidate minus baseline for the same optimum, so negative is better. The bar is the 5–95% range across optima, each faint dot is one optimum, and the tick is the median. Rows follow the prespecified ranking (median Δ seizing regions, ties broken by Δ duration). Arms that failed numerically are listed at the bottom. Without treatment the median optimum had {Rf["baseline_summary"]["n_seizing_regions"]["median"]:g} seizing regions (5–95%: {Rf["baseline_summary"]["n_seizing_regions"]["p05"]:g}–{Rf["baseline_summary"]["n_seizing_regions"]["p95"]:.1f}) and {Rf["baseline_summary"]["total_seizure_duration_s"]["median"]:.1f} s of total seizure time.</p>
{figure(next(fig), "Change in the number of seizing regions", fig_effect("full", F, "d_n_seizing_regions", "dn", "regions", "Paired change in seizing regions per candidate"),
        "Source: payload.results.full.effects.*.d_n_seizing_regions (median, p05, p95). Per-optimum dots recomputed from full_runs.json and checked against the payload. The 5–95% range of 12 values is close to the min–max.", legend_types)}
{figure(next(fig), "Change in total seizure duration (summed over regions)", fig_effect("full", F, "d_total_seizure_duration_s", "dd", "s", "Paired change in total seizure duration per candidate"),
        "A separate measure from the one above. Pulse trains add seizure time because stimulus-driven u1 excursions sustained for 1 s or more count as seizure (see limitations).", legend_types)}
{figure(next(fig), "Optima with all seizures abolished", fig_frac(fr_ab, "Fraction of optima with all seizures abolished", lambda c, v: f"{c}: all seizures abolished in {pct(v)} of {Rf['effects'][c]['n_samples']} optima"),
        "Fraction of optima in which the arm leaves zero seizing regions. Every full-window baseline seizes, so this equals the conditional fraction.")}
{figure(next(fig), "Rank stability: how often each arm is best", fig_frac(fr_rk, "Fraction of optima in which each arm ranks first, ties counted", lambda c, v: f"{c}: ranks first (incl. ties) in {pct(v)} of optima"),
        "Per optimum, every arm tied for the best (Δ regions, then Δ duration) counts as first, so the bars can sum to more than 100%. Source: payload.results.full.rank_first_fraction; tied_first = " + E(", ".join(Rf["tied_first"])) + ".")}
{tbl(["Rank", "Arm", "Optima", "Δ seizing regions", "Δ total duration (s)", "Δ first onset (ms)", "Δ SEEG channels > ref", "All abolished", "Ranks first"], eff_rows, raw_cols=(1, 3), num_cols=(0, 2, 7, 8),
     caption="Full window, median [5%, 95%] across optima. Positive Δ first onset means a later onset. Baseline SEEG channel exceedance is 191/191 in every optimum, so that metric is saturated.")}""")

    # ---------------------------------------------------------------- 4 windows
    lanes_x0, lanes_bs = [], []
    for w, col in (("post", "var(--s4)"), ("full", "var(--s1)")):
        S = W[w]["S"]
        lanes_x0.append((f"{w} ({len(S['samples'])} optima)", [(max(x["x0"]), f"{x['sample_id']}: max x0 {max(x['x0']):.3f} (region {lut[int(np.argmax(x['x0']))]}), lp {x['meta']['lp']:.1f}") for x in S["samples"]], col))
        lanes_bs.append((f"{w} ({len(W[w]['base'])} optima)", [(b["seizures"]["n_seizing_regions"], f"{b['sample_id']}: {b['seizures']['n_seizing_regions']} seizing regions, {b['seizures']['total_seizure_duration_s']:.1f} s total") for b in W[w]["base"].values()], col))
    post_rows = []
    for c in Pw["C"]["candidates"]:
        cid = c["id"]
        if cid in Rp["effects"]:
            e = Rp["effects"][cid]
            post_rows.append([f'<span class="sw" style="background:{TYPE_COL[arm_type(c)]}"></span> {E(cid)}', e["n_samples"], rng(e["d_n_seizing_regions"]), rng(e["d_total_seizure_duration_s"]),
                              rng(e["d_n_seeg_channels_exceeding"]), "n/a (no baseline seizures)", "tied"])
        else:
            f = Rp["numerically_failed_arms"][cid]
            post_rows.append([f'<span class="sw" style="background:{TYPE_COL[arm_type(c)]}"></span> {E(cid)}', f'{f["n_runs"] - f["n_nonfinite"]} finite of {f["n_runs"]}', '<span class="fail">numerical failure, excluded</span>', "", "", "", ""])
    pt_order = [c for c in Rp["effects"] if c.startswith("STIM-PT")] + [c for c in Rp["numerically_failed_arms"]]
    H.append(f"""<h2 id="windows">4 · The two windows: post (primary) vs full (sensitivity)</h2>
{figure(next(fig), "Highest region excitability in each optimum", fig_lanes(lanes_x0, "Maximum x0 per optimum by window", "max x0 over 162 regions", thr=-2.06, thr_lab="−2.06 EZ threshold (A0018)"),
        "One dot per simulated optimum. Source: samples_post.json and samples_full.json. In the post window no optimum puts any region above the threshold; the largest is " + f"{max(max(x['x0']) for x in Pw['S']['samples']):.2f}" + ".")}
{figure(next(fig), "Seizing regions without treatment", fig_lanes(lanes_bs, "Baseline seizing regions per optimum by window", "seizing regions (baseline)", integer=True),
        "Paired baselines from *_runs.json. No post-window optimum seizes, so treatment effects there are zero by construction.")}
<div class="card"><h3>Why the post window says nothing</h3><p>{E(P["headline"]["post (primary)"])}</p><p>A0018 already flagged the cause: {E(a18["limitations"][1])}</p>
<p>The only non-zero post-window effect is in SEEG channel exceedance under the pulse trains. That is stimulation-driven activity, not seizure, and it appears in the table below and in the explorer.</p></div>
{figure(next(fig), "Post window: the pulse trains change SEEG power, not seizures", fig_effect("post", Pw, "d_n_seeg_channels_exceeding", "dc", "channels", "Post window, paired change in SEEG channels above the reference", nd=0, order=pt_order),
        "Paired change in the number of SEEG channels whose log-power exceeds the baseline reference (mean + 3 SD of 250–750 ms) for at least 1 s. Pulse-train arms only; every other finite post arm is 0.")}
{tbl(["Arm", "Optima", "Δ seizing regions", "Δ total duration (s)", "Δ SEEG channels > ref", "Abolished", "Rank"], post_rows, raw_cols=(0, 2),
     caption=f"Post window, median [5%, 95%] across {Rp['n_samples']} optima. The payload's frac_abolish_all = 1.0 for these arms is trivial and not shown. {len(Rp['tied_first'])} arms are tied first, so the ranking is uninformative.")}""")

    # ---------------------------------------------------------------- 5 failures & deviations
    fail_rows = []
    for w in WINDOWS:
        for cid, f in W[w]["R"]["numerically_failed_arms"].items():
            c = W[w]["cand"][cid]
            nan_ms = SIG[w]["arms"][cid]["nan_ms"]
            fail_rows.append([w, f'<span class="sw" style="background:{TYPE_COL[arm_type(c)]}"></span> {E(cid)}', f"{c['amp'] * s['pt_istim_per_unit']:g}",
                              f'{f["n_nonfinite"]} / {f["n_runs"]}', "finite" if nan_ms is None else f"NaN from {nan_ms / 1000:.2f} s", E(f["status"])])
    q_rows = []
    for w in WINDOWS:
        qq = qual[w]
        for arm, v in qq["simulated"].items():
            q_rows.append([w, arm.replace("__", " · "), f'{v["overlap_with_observed_top10"]}/10', ", ".join(v["top10_channels"])])
    tsum = tasks["T0015"]["summary"]
    amb = tsum.split("Spec ambiguities resolved:")[1].strip().rstrip(".").split("; ")
    H.append(f"""<h2 id="failures">5 · Failures, deviations and resolved ambiguities</h2>
<h3>Numerical failures</h3>
<p>These arms went non-finite (NaN/Inf) during integration in at least one optimum. They are <b>failures</b>: the whole arm is excluded from effects and ranking, and it was neither dropped nor imputed. Every one is a 50 Hz pulse train at Istim ≥ 0.02 at the max-gain region. Payload numerical check: all_finite = {str(P["numerical_checks"]["post"]["all_finite"]).lower()} (post), {str(P["numerical_checks"]["full"]["all_finite"]).lower()} (full).</p>
{tbl(["Window", "Arm", "Istim at max-gain region", "Non-finite runs", "Median optimum's signal", "Status"], fail_rows, raw_cols=(1,))}
<h3>Deviations from the request (A0035)</h3><ul>{"".join(f"<li>{E(x)}</li>" for x in P["deviations_from_request_A0035"])}</ul>
<p class="fig-cap">The 12 simulated full-window optima are those with the highest log posterior, chosen before any full-window simulation ran (<code>samples_full.json</code> subset_rule). Their lp ranges from {min(x["meta"]["lp"] for x in F["S"]["samples"]):.1f} to {max(x["meta"]["lp"] for x in F["S"]["samples"]):.1f}. The other 12 were never simulated, so the full-window spread probably understates the ensemble spread.</p>
<h3>Spec ambiguities R4 resolved (T0015, before any model existed)</h3><ul>{"".join(f"<li>{E(x)}</li>" for x in amb)}</ul>
<h3>Qualitative check against the recording (failed)</h3>
<p>{E(qual["full"]["method"])}</p>
{tbl(["Window", "Simulated arm", "Overlap with observed top 10", "Simulated top-10 channels"], q_rows, num_cols=(2,),
     caption="Observed top 10 (P2 recording): " + ", ".join(qual["full"]["observed_top10"]) + ".")}
<p class="fig-cap">Verdicts: post: {E(qual["post"]["verdict"])}. Full: {E(qual["full"]["verdict"])}.</p>
<h3>Limitations recorded by R4</h3><ul>{"".join(f"<li>{E(x)}</li>" for x in P["limitations"])}</ul>""")

    # ---------------------------------------------------------------- 6 TI
    ti_p, ti_f = A(next(a for a in arts if a.startswith("A0032"))), A(next(a for a in arts if a.startswith("A0033")))
    n1 = st["needs"]["N001"]
    ana = ROOT / "data/wang-co2-ana"
    ana_files = sorted(str(p.relative_to(ana)).replace("\\", "/") for p in ana.rglob("*") if p.is_file()) if ana.exists() else []
    rmap = ana / "tvb/region_map_ico5.txt"
    n_rmap = sum(1 for ln in rmap.read_text().splitlines() if ln.strip()) if rmap.exists() else None
    H.append(f"""<h2 id="ti">6 · Temporal interference (TI) stimulation: not simulated</h2>
<p>{badge("failed", "infeasible")} Plan A0032 was judged infeasible in A0033. {E("; ".join(ti_f["verdict_reasons"]))}.</p>
{tbl(["Check", "Result", "Detail"], [[E(c["check"]), badge("passed" if c["result"] == "pass" else "failed", c["result"]), E(c["detail"])] for c in ti_f["checks"]], raw_cols=(0, 1, 2))}
<p>Need <b>N001</b> ({badge(n1["state"] if n1["state"] in ("open", "fulfilled") else "unreviewed", n1["state"])}, raised by {E(n1["requester"].split("-")[0])}): {E(n1["missing_input"])}. Acceptance: {E(n1["acceptance_criterion"])}.</p>
<div class="card"><h3>Possible second wave</h3><p>Patient anatomy has since been downloaded to <code>data/wang-co2-ana/</code> ({len(ana_files)} files: {E(", ".join(ana_files))}). It includes an ico5 region map with {n_rmap if n_rmap is not None else "?"} vertex rows, the same vertex count as the fsaverage5 EMF maps (2 × 10,242), plus an SEEG contact file and an ico5 dipole gain. If that surface is shown to be in fsaverage5 vertex correspondence and its labels match the 162 VEP regions, it could provide the documented mapping N001 asks for, and TI could be simulated in a second wave. None of this has been checked yet: R4 has not used these files, and N001 is still open.</p></div>""")

    # ---------------------------------------------------------------- 7 reproducibility
    pr = []
    for ref in man["payload_refs"]:
        p = SD / ref["uri"]
        got = sha(p)
        pr.append([f'<code>{E(ref["uri"].split("/")[-1])}</code>', f'{ref["byte_size"]:,}', f'<code>{ref["sha256"][:16]}…</code>',
                   badge("passed", "match") if got == ref["sha256"] else badge("failed", "mismatch")])
    rel = ["A0009-PatientCase", "A0015-Report", "A0017-NetworkHypothesisSet", "A0018-ModelBundle", "A0019-ModelBundle", "A0037-ModelBundle"] + \
          [a for a in sorted(arts) if a[:5] in {f"A00{i}" for i in range(20, 39)}]
    ar = [[f"<code>{a.split('-')[0]}</code>", E(arts[a]["schema_name"]), E(arts[a]["producer_role"].split("-")[0]),
           badge("stale" if arts[a]["stale"] else arts[a]["effective_validation"]), E((arts[a].get("title") or "")[:120]), f'<code>{arts[a]["manifest_hash"][:12]}</code>']
          for a in rel if a in arts]
    seeds = {w: sorted(x["meta"]["seed"] for x in W[w]["S"]["samples"]) for w in WINDOWS}
    ru = P["resource_use"]
    H.append(f"""<h2 id="repro">7 · Reproducibility</h2>
{tbl(["Item", "Value"], [
        ["Batch", f'A0038-SimulationBatch · manifest hash <code>{arts["A0038-SimulationBatch"]["manifest_hash"]}</code> · input manifest <code>{man["input_manifest_hash"][:16]}…</code> · environment digest <code>{man["environment_digest"][:16]}…</code>'],
        ["Consumed", E(", ".join(man["consumed_artifact_ids"]))],
        ["Simulator", f'<code>studies/study-002/work/T0015/sim/p2sim.py</code> sha256 <code>{sim_sha}</code> {"✓ matches tool_version" if sim_sha in man["tool_version"] else "✕ differs from tool_version"}'],
        ["Prespecified spec", f'<code>work/amend/r4_common_spec.json</code> sha256 <code>{spec_sha}</code> {"✓" if spec_sha == Rp["meta"]["spec_sha256"] == Rf["meta"]["spec_sha256"] else "✕"}'],
        ["Patient data", f'<code>P2_SEEG_ts_fit.npz</code> sha256 <code>{npz_sha}</code> {"✓" if npz_sha == Rf["meta"]["npz_sha256"] else "✕"}'],
        ["Model samples", f'A0018 MAP optima: post {len(seeds["post"])} (L-BFGS seeds {seeds["post"][0]}–{seeds["post"][-1]}), full {len(seeds["full"])} (seeds {", ".join(map(str, seeds["full"]))})'],
        ["Seeds", E(P["seeds"]["dynamics"]) + "; " + E(P["seeds"]["seeg_observation_noise"])],
        ["Runtime", f'post {ru["post"]["wall_total_s"] / 60:.1f} min, full {ru["full"]["wall_total_s"] / 60:.1f} min wall ({ru["full"]["workers"]} workers, {E(ru["full"]["machine"])}). Per simulation, median / max: post {ru["post"]["per_sim_wall_s"]["median"]:.0f} / {ru["post"]["per_sim_wall_s"]["max"]:.0f} s, full {ru["full"]["per_sim_wall_s"]["median"]:.0f} / {ru["full"]["per_sim_wall_s"]["max"]:.0f} s'],
        ["Tasks", f'T0015 design and simulator {tasks["T0015"]["started_at"][11:16]}–{tasks["T0015"]["finished_at"][11:16]} UTC; T0017 simulations {tasks["T0017"]["started_at"][11:16]}–{tasks["T0017"]["finished_at"][11:16]} UTC (2026-11-01)'],
        ["Environment", f'Python {E(Rf["meta"]["python"])} on {E(Rf["meta"]["platform"])}; TVB 2.10.0; vep-stim @ 5367ef4'],
        ["This page", "Generated by <code>system/reports/r4_report.py</code> from the files above (read-only). Each effect's median and 5–95% range is recomputed from <code>*_runs.json</code> and asserted equal to the payload. <code>full_summary.json</code> / <code>post_summary.json</code> are p2sim's raw summaries; the payload marks them as superseded by its tie-aware recomputation, so they are not used for effects."]], raw_cols=(1,))}
<h3>Batch files (hash re-verified now)</h3>
{tbl(["File", "Bytes", "sha256 (manifest)", "Re-hash"], pr, raw_cols=(0, 2, 3), num_cols=(1,))}
<details><summary>Related artifacts ({len(ar)}) with gate status and manifest hashes</summary>{tbl(["Id", "Schema", "Producer", "Gate", "Title", "Manifest hash"], ar, raw_cols=(0, 3, 5))}</details>
<p class="fig-cap">Not shown: a 3D brain view (targets are whole atlas regions, there is no patient surface in the batch, and TI was not simulated), the 162-region maps for every optimum (only the median optimum's signals were saved), and the 12 full-window optima that were not simulated.</p>""")

    js = JS_SIG.replace("__ULO__", str(U_LO)).replace("__UHI__", str(U_HI))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Study-002 R4 Simulations</title><style>{sr.CSS}{CSS_EXTRA}</style></head><body><div class="wrap">{"".join(H)}</div>
<div id="tip" role="tooltip"></div><script type="application/json" id="sigdata">{json.dumps(SIG, separators=(",", ":"))}</script>
<script>{sr.JS}{js}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "reports" / "study-002-R4-simulations.html"))
    a = ap.parse_args(argv)
    print(build(Path(a.out)))


if __name__ == "__main__":
    main()
