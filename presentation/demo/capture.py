"""Capture the demo walkthrough as 1920x1080 JPEG frames by driving the local Chrome headlessly over CDP.

    python presentation/demo/capture.py

Read-only: it only navigates, switches dashboard tabs, opens a skill in the editor (no Save), scrolls the
study-001 report, and steps the slides' 3D viewer. Needs the dashboard (8765), reports (8770) and
presentation (8771) servers running. Writes presentation/demo/img/*.jpg and presentation/demo/frames.json.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

OUT = Path(__file__).resolve().parent / "img"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
DASH, REPORTS, DECK = "http://127.0.0.1:8765/", "http://127.0.0.1:8770/", "http://127.0.0.1:8771/"


class Tab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self.i = 0

    def send(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    def goto(self, url, wait=2.5):
        self.send("Page.navigate", url=url)
        time.sleep(wait)

    def shot(self, name):
        data = self.send("Page.captureScreenshot", format="jpeg", quality=86)["data"]
        (OUT / f"{name}.jpg").write_bytes(base64.b64decode(data))
        print("shot", name)


def main():
    OUT.mkdir(exist_ok=True)
    prof = tempfile.mkdtemp(prefix="cdp-profile-", dir=os.environ.get("CAPTURE_TMP"))
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
                             "--window-size=1920,1080", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
                             "--disable-background-networking", "--disable-sync", "--disable-extensions",
                             "--force-color-profile=srgb", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "about:blank"])
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except Exception:
                time.sleep(0.3)
        page = [t for t in targets if t["type"] == "page"][0]
        t = Tab(page["webSocketDebuggerUrl"])
        t.send("Page.enable")
        t.send("Emulation.setDeviceMetricsOverride", width=1920, height=1080, deviceScaleFactor=1, mobile=False)
        t.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
        frames = []

        def add(name, caption, secs):
            frames.append({"img": f"img/{name}.jpg", "caption": caption, "secs": secs})

        # ---- (a) live dashboard, study-002 ----
        t.goto(DASH, 3)
        t.js("""(()=>{const s=document.getElementById('study');s.value='study-002';s.dispatchEvent(new Event('change'));})()""")
        time.sleep(2.5)
        for tab, name, cap, secs in [
            ("agents", "d1_agents", "Live dashboard, study-002: the Agents board. Each role is a separate agent with its own budget, running and finished tasks.", 7),
            ("timeline", "d2_timeline", "Timeline: every task the controller admitted, refused or finished, read from the append-only ledger.", 7),
            ("needs", "d3_needs", "Needs & gates: unmet needs agents posted for others to claim, and gate verdicts recorded by a role other than the producer.", 7),
            ("artifacts", "d4_artifacts", "Artifacts: every committed record with its schema, producer, validation state and provenance.", 7)]:
            t.js(f"document.querySelector('nav#tabs [data-t=\"{tab}\"]').click()")
            time.sleep(1.8)
            t.shot(name)
            add(name, cap, secs)
        t.js("document.querySelector('nav#tabs [data-t=\"skills\"]').click()")
        time.sleep(1.5)
        t.js("openSkillFor('R5-independent-evaluation')")
        time.sleep(2)
        t.shot("d6_skills")
        add("d6_skills", "Skills & agents: each role's operating procedure is editable with history. Studies run on a frozen copy, so edits only affect future studies.", 8)
        t.js("try{localStorage.setItem('tab','agents')}catch(e){}")

        # ---- (b) study-001 HTML report ----
        t.goto(REPORTS + "study-001-summary.html", 3)
        t.shot("r1_top")
        add("r1_top", "Study-001 report (finished): built from committed, gated records only. Every number links to an artifact.", 7)
        for k, (anchor, cap) in enumerate([
                ("workflow", "Phases and their outcome: the model gate failed, so intervention design and blinded evaluation were not run."),
                ("modeling", "Virtual-patient modelling: R5 re-derived convergence from the raw draws. No region's excitability converged, so the pipeline was not qualified."),
                ("quality", "Quality controls: outcome blinding, independent checking, and the open needs the agents left for the next study.")]):
            t.goto(REPORTS + f"study-001-summary.html#{anchor}", 2.5)
            time.sleep(1.2)
            t.shot(f"r{k + 2}")
            add(f"r{k + 2}", cap, 7)

        # ---- (c) before/after simulation and the 3D brain (from the slides) ----
        t.goto(DECK + "slides.html#6", 3)
        t.shot("s1_beforeafter")
        add("s1_beforeafter", "Study-002, exploratory: virtual treatments on blinded virtual Patient 2. Ablating the estimated zone stopped simulated seizures in 5 of 12 fits; pulse-train stimulation did not.", 9)
        t.goto(DECK + "slides.html#5", 3)
        for mode, lab in [("BASELINE", "before treatment"), ("RES-EZpPZ__ablation", "after ablating the estimated EZ + PZ"), ("STIM-PT__amp1", "with SEEG pulse-train stimulation")]:
            t.js(f"__v3d.setMode('{mode}')")
            for f in (40, 100, 160):
                t.js(f"__v3d.setFrame({f})")
                time.sleep(0.5)
                name = f"b_{mode.split('__')[0]}_{f}"
                t.shot(name)
                add(name, f"Patient 2's own cortex and 205 SEEG contacts. Simulated region activity {lab} (t = {f * 0.04:.1f} s).", 1.6)
        t.js("__v3d.setMode('TI')")
        time.sleep(0.8)
        t.shot("b_TI")
        add("b_TI", "Temporal-interference stimulation field from Wang 2025, on the fsaverage5 template. Mapping it onto Patient 2 is an open need.", 6)
        (OUT.parent / "frames.json").write_text(json.dumps(frames, indent=1), encoding="utf-8")
        print("frames", len(frames), "total s", sum(f["secs"] for f in frames))
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
