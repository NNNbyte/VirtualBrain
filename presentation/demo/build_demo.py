"""Assemble presentation/demo/index.html (auto-playing captioned walkthrough) from frames.json and img/.

    python presentation/demo/build_demo.py

Pacing lives here (seconds per frame); captions come from capture.py via frames.json.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACE = {"d1_agents": 7, "d2_timeline": 5, "d3_needs": 6, "d4_artifacts": 5, "d6_skills": 6,
        "r1_top": 5, "r2": 5, "r3": 6, "r4": 5, "s1_beforeafter": 8, "b_TI": 5}
CHAPTER = {"d": "A · Live dashboard (study-002)", "r": "B · Study-001 report", "s": "C · Virtual treatment (study-002)",
           "b": "C · Virtual treatment (study-002)"}

frames = json.loads((HERE / "frames.json").read_text(encoding="utf-8"))
for f in frames:
    name = Path(f["img"]).stem
    f["secs"] = PACE.get(name, 1.6)  # 3D frames cycle quickly, like an animation
    f["chapter"] = CHAPTER[name[0]]
    assert (HERE / f["img"]).exists(), f["img"]
total = sum(f["secs"] for f in frames)

html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ScienceClaw Demo Walkthrough</title>
<style>
:root{color-scheme:light;--ink:#111110;--ink2:#4c4b47;--muted:#7a7872;--accent:#eb6834}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#1b1b1a;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow:hidden}
#wrap{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
#stage{width:1920px;height:1080px;position:relative;flex:none;transform-origin:center;background:#fff;overflow:hidden}
#stage img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;opacity:0;transition:opacity .45s}
#stage img.on{opacity:1}#stage img.fast{transition:opacity .15s}
#cap{position:absolute;left:50%;bottom:44px;transform:translateX(-50%);width:1500px;background:rgba(17,17,16,.88);color:#fff;border-radius:16px;padding:18px 28px 20px;font-size:28px;line-height:1.38;box-shadow:0 10px 30px rgba(0,0,0,.25)}
#cap .ch{font-size:17px;font-weight:650;letter-spacing:.07em;text-transform:uppercase;color:#f0b44c;margin-bottom:4px}
#bar{position:absolute;left:0;right:0;bottom:0;height:8px;background:rgba(0,0,0,.12)}#bar i{display:block;height:100%;width:0;background:var(--accent)}
#badge{position:absolute;right:28px;top:22px;background:#fde9d9;color:#9a3b10;border:1.5px solid #f4b48f;border-radius:999px;padding:6px 14px;font:650 17px system-ui;letter-spacing:.04em;text-transform:uppercase;display:none}
#ctl{position:fixed;left:16px;bottom:14px;display:flex;gap:8px;align-items:center;color:#ddd;font:14px system-ui;z-index:5}
#ctl button{font:inherit;border:1px solid #555;background:#2a2a28;color:#eee;border-radius:8px;padding:6px 12px;cursor:pointer}
#start{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;background:rgba(255,255,255,.94);gap:18px}
#start h1{font-size:64px;margin:0;letter-spacing:-.02em}#start p{font-size:26px;color:#4c4b47;margin:0;max-width:1300px;text-align:center}
#start button{font:650 28px system-ui;background:#111;color:#fff;border:0;border-radius:999px;padding:16px 36px;cursor:pointer;margin-top:10px}
</style></head><body>
<div id="wrap"><div id="stage">
  <div id="imgs"></div>
  <div id="badge">exploratory · model not qualified</div>
  <div id="cap"><div class="ch"></div><div class="tx"></div></div>
  <div id="bar"><i></i></div>
  <div id="start"><h1>ScienceClaw Epilepsy Collective: demo</h1>
    <p>A __TOTAL__-second walkthrough: (A) the live controller dashboard for study-002, (B) the finished study-001 report, (C) virtual treatments and the 3D brain. Research evidence on virtual patients, not clinical recommendations.</p>
    <button id="go">▶ Play walkthrough</button></div>
</div></div>
<div id="ctl"><button id="pp">❚❚</button><button id="pv">◀</button><button id="nx">▶</button><span id="pos"></span><span id="clk"></span></div>
<script>
const F=__FRAMES__,TOTAL=F.reduce((a,f)=>a+f.secs,0);
const host=document.getElementById('imgs');
F.forEach(f=>{const im=new Image();im.src=f.img;im.alt=f.caption;if(f.img.includes('/b_')&&!f.img.includes('b_TI'))im.className='fast';host.appendChild(im);});
const ims=[...host.children];let i=0,playing=false,t0=0,timer=null,elapsedBefore=0;
function fit(){const s=Math.min(innerWidth/1920,innerHeight/1080);document.getElementById('stage').style.transform=`scale(${s})`;}addEventListener('resize',fit);fit();
function show(k){i=(k+F.length)%F.length;ims.forEach((im,j)=>im.classList.toggle('on',j===i));
  const f=F[i];document.querySelector('#cap .ch').textContent=f.chapter;document.querySelector('#cap .tx').textContent=f.caption;
  document.getElementById('badge').style.display=/study-002/.test(f.chapter)&&f.chapter.startsWith('C')?'block':'none';
  document.getElementById('pos').textContent=`${i+1} / ${F.length}`;elapsedBefore=F.slice(0,i).reduce((a,x)=>a+x.secs,0);t0=performance.now();
  clearTimeout(timer);if(playing)timer=setTimeout(()=>{if(i===F.length-1){playing=false;document.getElementById('pp').textContent='▶';return;}show(i+1);},f.secs*1000);}
function tick(){const e=playing?Math.min(F[i].secs,(performance.now()-t0)/1000):0;const p=(elapsedBefore+e)/TOTAL;document.querySelector('#bar i').style.width=(p*100)+'%';
  const s=Math.round(elapsedBefore+e);document.getElementById('clk').textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')} / ${Math.floor(TOTAL/60)}:${String(Math.round(TOTAL%60)).padStart(2,'0')}`;requestAnimationFrame(tick);}
function play(on){playing=on;document.getElementById('pp').textContent=on?'❚❚':'▶';show(i);}
document.getElementById('go').onclick=()=>{document.getElementById('start').style.display='none';play(true);};
document.getElementById('pp').onclick=()=>play(!playing);document.getElementById('pv').onclick=()=>show(i-1);document.getElementById('nx').onclick=()=>show(i+1);
addEventListener('keydown',e=>{if(e.key===' '){e.preventDefault();document.getElementById('start').style.display='none';play(!playing);}else if(e.key==='ArrowRight')show(i+1);else if(e.key==='ArrowLeft')show(i-1);});
const q=new URLSearchParams(location.search);if(q.has('autoplay')){document.getElementById('start').style.display='none';playing=true;}
show(+(q.get('f')||0));requestAnimationFrame(tick);
</script></body></html>
"""
html = html.replace("__FRAMES__", json.dumps(frames)).replace("__TOTAL__", str(round(total)))
(HERE / "index.html").write_text(html, encoding="utf-8")
print("index.html", len(frames), "frames", total, "s")
