"""Build presentation/pitch.html: a 5-slide, 3-minute judges' pitch, one judging criterion per slide.

    python presentation/build/build_pitch.py

Counts come from both study ledgers at build time; single- vs multi-agent scores are copied from
comparison/comparison.md (pre-registered criteria, comparison/criteria.sha256). Read-only everywhere else.
"""
import base64
import collections
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent

# comparison/comparison.md, "Scores" table (criteria fixed before the run; scorer blind to study outputs at that time)
SCORES = [("Finds the seizure-onset zone", 1, 0),
          ("Honest about uncertainty", 2, 3),
          ("Catches pipeline bugs (4 known)", 0, 3),
          ("Tests its method on known truth", 0, 3),
          ("Keeps the answer key sealed", 1, 3),
          ("Traceable and reproducible", 1, 3),
          ("Treatment advice backed by evidence", 1, 3)]


def ledger(study):
    ev = [json.loads(l) for l in open(ROOT / f"studies/{study}/ledger.jsonl", encoding="utf-8")]
    c = collections.Counter(e["type"] for e in ev)
    v = collections.Counter(e["verdict"] for e in ev if e["type"] == "gate_recorded")
    return {"tasks": c["task_admitted"], "artifacts": c["artifact_committed"], "gates": sum(v.values()),
            "not_passed": v["failed"] + v["indeterminate"], "repairs": c["repair_issued"], "refused": c["task_refused"],
            "needs": c["need_opened"], "frozen": c["predictions_frozen"], "first": ev[0]["ts"], "last": ev[-1]["ts"]}


def brain_jpeg():
    im = Image.open(ROOT / "presentation/demo/img/b_BASELINE_100.jpg").crop((230, 340, 1000, 870))
    im.thumbnail((980, 980))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def next_version(folder, stem):
    """Never overwrite: the unversioned <stem>.html counts as v1, so the next build is <stem>_v2.html, then _v3, ..."""
    n = 2
    while (folder / f"{stem}_v{n}.html").exists():
        n += 1
    return folder / f"{stem}_v{n}.html"


def main():
    s1, s2 = ledger("study-001"), ledger("study-002")
    tot = {k: s1[k] + s2[k] for k in ("tasks", "artifacts", "gates", "not_passed", "repairs", "refused", "needs")}
    data = {"s1": s1, "s2": s2, "tot": tot, "scores": SCORES,
            "sum_single": sum(a for _, a, _ in SCORES), "sum_multi": sum(b for _, _, b in SCORES)}
    html = (HERE / "pitch_template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data)).replace("__BRAIN__", brain_jpeg())
    out = next_version(ROOT / "presentation", "pitch")
    out.write_text(html, encoding="utf-8")
    print("wrote", out.name)
    print(json.dumps(data["tot"]), data["sum_single"], data["sum_multi"])
    print("study-002", json.dumps(s2))


if __name__ == "__main__":
    main()
