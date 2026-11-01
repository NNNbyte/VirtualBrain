"""Local dashboard for the epilepsy research agent system.

    python system/ui/server.py [--port 8765]

Serves http://127.0.0.1:<port>/ : live agent board, timeline, needs/gates,
artifacts, and an editor for skills, agent definitions and role profiles
(with version history). Binds to localhost only. Stdlib only.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import controller as ctl  # noqa: E402

ROOT = ctl.ROOT
HISTORY = ROOT / "system" / "history"
AGENTS_DIR = ROOT / ".claude" / "agents"


def editable_files():
    """All files the editor may touch, grouped by owning agent."""
    out = []
    profiles = ctl.live_profiles()
    agent_names = {
        "R1-evidence-scout": "r1-evidence-scout", "R2-case-curation": "r2-case-curation",
        "R3-virtual-patient": "r3-virtual-patient", "R4-intervention-design": "r4-intervention-design",
        "R5-independent-evaluation": "r5-independent-evaluation", "R6-improvement-research": "r6-improvement-research",
        "RV-clinical-engineering-review": "clinical-engineering-reviewer", "LEAD-study-lead": None,
    }
    for aid, prof in profiles.items():
        group = {"agent_id": aid, "display_name": prof.get("display_name", aid), "color": prof.get("color"),
                 "enabled": prof.get("enabled", True), "files": []}
        skill_dir = ctl.SKILLS / prof["skill"]
        if skill_dir.exists():
            for p in sorted(skill_dir.rglob("*")):
                if p.is_file():
                    kind = "skill" if p.name == "SKILL.md" else "reference"
                    group["files"].append({"path": p.relative_to(ROOT).as_posix(), "kind": kind})
        an = agent_names.get(aid)
        if an and (AGENTS_DIR / f"{an}.md").exists():
            group["files"].append({"path": f".claude/agents/{an}.md", "kind": "agent"})
        group["files"].append({"path": f"system/profiles/{aid}.json", "kind": "profile"})
        out.append(group)
    order = ["LEAD", "R1", "R2", "R3", "R4", "R5", "RV", "R6"]
    out.sort(key=lambda g: order.index(g["agent_id"].split("-")[0]) if g["agent_id"].split("-")[0] in order else 99)
    return out


def allowed_path(rel):
    allowed = {f["path"] for g in editable_files() for f in g["files"]}
    if rel not in allowed:
        raise PermissionError(f"{rel} is not an editable file")
    return ROOT / rel


def sha(b):
    return hashlib.sha256(b).hexdigest()


def history_dir(rel):
    return HISTORY / rel.replace("/", "__")


def save_file(rel, content, base_sha, note):
    p = allowed_path(rel)
    current = p.read_bytes() if p.exists() else b""
    if base_sha and base_sha != sha(current):
        return 409, {"ok": False, "error": "file changed on disk since you opened it; reload and re-apply"}
    if rel.endswith(".json"):
        try:
            obj = json.loads(content)
        except json.JSONDecodeError as e:
            return 400, {"ok": False, "error": f"invalid JSON: {e}"}
        if rel.startswith("system/profiles/") and obj.get("agent_id") != Path(rel).stem:
            return 400, {"ok": False, "error": "agent_id must match the profile file name"}
    if rel.endswith("SKILL.md") and not content.lstrip().startswith("---"):
        return 400, {"ok": False, "error": "SKILL.md must start with YAML frontmatter (---)"}
    hd = history_dir(rel)
    hd.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if current:
        (hd / f"{stamp}.prev").write_bytes(current)
    new = content.replace("\r\n", "\n").encode("utf-8")
    p.write_bytes(new)
    log = hd / "log.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": stamp, "note": note or "", "sha": sha(new), "prev": f"{stamp}.prev" if current else None}) + "\n")
    return 200, {"ok": True, "sha": sha(new), "live_release_id": ctl.compute_release_id()}


def file_history(rel):
    allowed_path(rel)
    log = history_dir(rel) / "log.jsonl"
    if not log.exists():
        return []
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    return list(reversed(rows))


def trimmed_state(study_id):
    d = ctl.study_dir(study_id)
    st = ctl.load_state(d)
    st["events"] = st["events"][-400:]
    for a in st["artifacts"].values():
        a.pop("gates", None)
    st["live_release_id"] = ctl.compute_release_id()
    try:
        man = json.loads((d / "release" / "manifest.json").read_text())
        changed = []
        for p in ctl.release_sources():
            r = p.relative_to(ROOT).as_posix()
            if man["files"].get(r) != ctl.sha256_file(p):
                changed.append(r)
        st["release_changed_files"] = changed
    except FileNotFoundError:
        st["release_changed_files"] = []
    return st


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/studies":
                return self.send(200, ctl.cmd_study_list(None))
            if u.path == "/api/state":
                return self.send(200, trimmed_state(q.get("study")))
            if u.path == "/api/artifact":
                d = ctl.study_dir(q.get("study"))
                st = ctl.load_state(d)
                art = st["artifacts"].get(q["id"])
                if not art:
                    return self.send(404, {"error": "not found"})
                payload = None
                if art["access_classification"] != "reserved":
                    pp = d / art["payload_refs"][0]["uri"]
                    txt = pp.read_text(encoding="utf-8")
                    try:
                        payload = json.loads(txt)
                    except json.JSONDecodeError:
                        payload = txt
                children = ctl.descendants(st, q["id"])
                return self.send(200, {"envelope": art, "payload": payload, "descendants": children})
            if u.path == "/api/editables":
                return self.send(200, {"groups": editable_files(), "live_release_id": ctl.compute_release_id()})
            if u.path == "/api/file":
                p = allowed_path(q["path"])
                b = p.read_bytes() if p.exists() else b""
                return self.send(200, {"path": q["path"], "content": b.decode("utf-8"), "sha": sha(b),
                                       "history": file_history(q["path"])})
            if u.path == "/api/history":
                allowed_path(q["path"])
                v = Path(q["version"]).name
                b = (history_dir(q["path"]) / v).read_bytes()
                return self.send(200, {"content": b.decode("utf-8")})
            if u.path == "/api/frozen":
                d = ctl.study_dir(q.get("study"))
                rel = q["path"]
                if rel.startswith(".claude/skills/"):
                    fp = d / "release" / "skills" / rel[len(".claude/skills/"):]
                elif rel.startswith("system/profiles/"):
                    fp = d / "release" / "profiles" / Path(rel).name
                else:
                    return self.send(404, {"error": "not part of a frozen release"})
                if not fp.exists():
                    return self.send(404, {"error": "not in this study's release"})
                return self.send(200, {"content": fp.read_text(encoding="utf-8")})
            return self.send(404, {"error": "not found"})
        except ctl.Refused as e:
            return self.send(404, {"error": "; ".join(e.reasons)})
        except PermissionError as e:
            return self.send(403, {"error": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        # only accept same-origin JSON posts from the dashboard
        origin = self.headers.get("Origin")
        if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
            return self.send(403, {"error": "cross-origin request refused"})
        try:
            if u.path == "/api/file":
                code, out = save_file(body["path"], body["content"], body.get("base_sha"), body.get("note"))
                return self.send(code, out)
            if u.path == "/api/profile/toggle":
                rel = f"system/profiles/{body['agent_id']}.json"
                p = allowed_path(rel)
                b = p.read_bytes()
                obj = json.loads(b)
                obj["enabled"] = not obj.get("enabled", True)
                code, out = save_file(rel, json.dumps(obj, indent=2) + "\n", sha(b),
                                      f"{'enabled' if obj['enabled'] else 'disabled'} from dashboard")
                return self.send(code, {**out, "enabled": obj["enabled"]})
            return self.send(404, {"error": "not found"})
        except PermissionError as e:
            return self.send(403, {"error": str(e)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Dashboard: http://127.0.0.1:{a.port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
