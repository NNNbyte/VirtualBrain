"""Self-contained WebGL viewer of the fsaverage5 cortex with per-vertex scalar overlays (no external JS).

    html = brain_viewer_html(overlays, elem_id="brain1")

`overlays` is a list of dicts {"name", "values" (len 20484: lh then rh), "unit", "cmap": "seq"|"div"}.
Run with the model venv (nilearn bundles the fsaverage5 meshes).
"""
import base64
import json

import numpy as np

N_HEMI = 10242


def fsaverage5():
    from nilearn import datasets, surface
    fs = datasets.fetch_surf_fsaverage("fsaverage5")
    vs, fs_ = [], []
    off = 0
    for h in ("left", "right"):
        mesh = surface.load_surf_mesh(fs[f"pial_{h}"])
        vs.append(np.asarray(mesh.coordinates, dtype=np.float32))
        fs_.append(np.asarray(mesh.faces, dtype=np.int64) + off)
        off += len(mesh.coordinates)
    return np.vstack(vs), np.vstack(fs_).astype(np.uint16)


def _b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def brain_viewer_html(overlays, elem_id="brain", height=460, caption_controls=True, mesh=None, points=None):
    """mesh: optional (vertices, faces) instead of fsaverage5. points: optional list of {"xyz": (n,3) in mesh
    coordinates, "color": css var name, "label": str} drawn as dots (e.g. SEEG contacts)."""
    v, f = mesh if mesh is not None else fsaverage5()
    v = np.asarray(v, dtype=np.float32)
    f = np.asarray(f).astype(np.uint16)
    c = v.mean(0)
    v = v - c
    scale = float(np.abs(v).max())
    v = v / scale
    pts = [{"xyz": _b64(((np.asarray(p["xyz"], dtype=np.float32) - c) / scale).astype(np.float32)),
            "color": p.get("color", "--ink"), "label": p.get("label", ""), "size": p.get("size", 5)}
           for p in (points or [])]
    ov = []
    for o in overlays:
        vals = np.asarray(o["values"], dtype=np.float32)
        assert vals.shape == (len(v),), (o["name"], vals.shape)
        # Colour limits from percentiles so a few hot vertices don't wash out the map; values beyond saturate.
        if o.get("cmap") == "div":
            m = float(np.nanpercentile(np.abs(vals), 99)) or 1.0
            lo, hi = -m, m
        else:
            lo, hi = float(np.nanmin(vals)), float(np.nanpercentile(vals, 99))
        ov.append({"name": o["name"], "unit": o.get("unit", ""), "cmap": o.get("cmap", "seq"),
                   "lo": lo, "hi": hi, "data": _b64(vals)})
    payload = json.dumps({"v": _b64(v), "f": _b64(f), "ov": ov, "pts": pts})
    opts = "".join(f'<option value="{i}">{o["name"]}</option>' for i, o in enumerate(ov))
    legend_pts = "".join(f'<span class="b3d-pt"><span style="background:var({p["color"]})"></span>{p["label"]}</span>'
                         for p in pts if p["label"])
    return f"""
<div class="b3d" id="{elem_id}">
  <div class="b3d-bar"><label>Overlay <select class="b3d-sel">{opts}</select></label>
  <span class="b3d-views"><button data-v="left">Left</button><button data-v="right">Right</button><button data-v="top">Top</button><button data-v="front">Front</button></span>
  <span class="b3d-scale"><span class="b3d-lo"></span><span class="b3d-grad"></span><span class="b3d-hi"></span></span>{legend_pts}</div>
  <canvas class="b3d-cv" style="width:100%;height:{height}px" aria-label="3D cortex surface; drag to rotate, wheel to zoom"></canvas>
  <div class="b3d-hint">Drag to rotate · wheel to zoom · colour limits are the 99th percentile (values beyond saturate)</div>
</div>
<script>(function(){{
const P={payload};
const root=document.getElementById('{elem_id}'),cv=root.querySelector('.b3d-cv');
const dec=(s,T)=>{{const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new T(u.buffer);}};
const V=dec(P.v,Float32Array),F=dec(P.f,Uint16Array),nv=V.length/3;
const N=new Float32Array(V.length);
for(let i=0;i<F.length;i+=3){{const a=F[i]*3,b=F[i+1]*3,c=F[i+2]*3;
 const ux=V[b]-V[a],uy=V[b+1]-V[a+1],uz=V[b+2]-V[a+2],wx=V[c]-V[a],wy=V[c+1]-V[a+1],wz=V[c+2]-V[a+2];
 const nx=uy*wz-uz*wy,ny=uz*wx-ux*wz,nz=ux*wy-uy*wx;for(const k of[a,b,c]){{N[k]+=nx;N[k+1]+=ny;N[k+2]+=nz;}}}}
const gl=cv.getContext('webgl');if(!gl){{cv.replaceWith(Object.assign(document.createElement('p'),{{textContent:'WebGL is not available in this browser.'}}));return;}}
const vs=`attribute vec3 p;attribute vec3 n;attribute vec3 c;uniform mat4 M;uniform mat4 Pm;varying vec3 vc;varying float l;
void main(){{vec4 q=M*vec4(p,1.);gl_Position=Pm*q;vec3 nn=normalize((M*vec4(n,0.)).xyz);l=.35+.65*abs(nn.z);vc=c;}}`;
const fs=`precision mediump float;varying vec3 vc;varying float l;void main(){{gl_FragColor=vec4(vc*l,1.);}}`;
const sh=(t,s)=>{{const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);return o;}};
const pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,vs));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,fs));gl.linkProgram(pr);gl.useProgram(pr);
const buf=(d,name,k)=>{{const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,d,gl.STATIC_DRAW);const loc=gl.getAttribLocation(pr,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,k,gl.FLOAT,false,0,0);return b;}};
buf(V,'p',3);buf(N,'n',3);const C=new Float32Array(V.length);const cb=buf(C,'c',3);
const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,F,gl.STATIC_DRAW);
gl.enable(gl.DEPTH_TEST);
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const hex=h=>{{h=h.replace('#','');return[0,2,4].map(i=>parseInt(h.substr(i,2),16)/255);}};
const mix=(a,b,t)=>a.map((x,i)=>x+(b[i]-x)*t);
let cur=0,vals=null;
function paint(){{const o=P.ov[cur];vals=dec(o.data,Float32Array);
 const base=hex(css('--brain')||'#c9c7c0'),pos=hex(css('--s2')||'#eb6834'),neg=hex(css('--s1')||'#2a78d6'),seqLo=hex(css('--seq-lo')||'#f3e3c3');
 for(let i=0;i<nv;i++){{let col;const x=vals[i];
  if(o.cmap==='div'){{const t=Math.max(-1,Math.min(1,x/o.hi));col=t>=0?mix(base,pos,t):mix(base,neg,-t);}}
  else{{const t=Math.max(0,Math.min(1,(x-o.lo)/((o.hi-o.lo)||1)));col=t<0.04?base:mix(seqLo,pos,Math.pow(t,.8));}}
  C[i*3]=col[0];C[i*3+1]=col[1];C[i*3+2]=col[2];}}
 gl.bindBuffer(gl.ARRAY_BUFFER,cb);gl.bufferData(gl.ARRAY_BUFFER,C,gl.STATIC_DRAW);
 root.querySelector('.b3d-lo').textContent=o.lo.toPrecision(2);root.querySelector('.b3d-hi').textContent=o.hi.toPrecision(2)+' '+o.unit;
 root.querySelector('.b3d-grad').style.background=o.cmap==='div'?`linear-gradient(90deg,${{css('--s1')}},${{css('--brain')}},${{css('--s2')}})`:`linear-gradient(90deg,${{css('--brain')}},${{css('--s2')}})`;draw();}}
let rx=-1.4,rz=-1.57,zoom=2.6;
function mat(){{const cx=Math.cos(rx),sx=Math.sin(rx),cz=Math.cos(rz),sz=Math.sin(rz);
 return new Float32Array([cz,sz*cx,sz*sx,0,-sz,cz*cx,cz*sx,0,0,-sx,cx,0,0,0,-zoom,1]);}}
function draw(){{const w=cv.clientWidth*devicePixelRatio,h=cv.clientHeight*devicePixelRatio;if(cv.width!==w||cv.height!==h){{cv.width=w;cv.height=h;}}
 gl.viewport(0,0,w,h);const bg=hex(css('--surface')||'#fcfcfb');gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
 const a=w/h,f=1/Math.tan(.35),nn=.1,ff=20;
 gl.uniformMatrix4fv(gl.getUniformLocation(pr,'Pm'),false,new Float32Array([f/a,0,0,0,0,f,0,0,0,0,(ff+nn)/(nn-ff),-1,0,0,2*ff*nn/(nn-ff),0]));
 gl.uniformMatrix4fv(gl.getUniformLocation(pr,'M'),false,mat());gl.drawElements(gl.TRIANGLES,F.length,gl.UNSIGNED_SHORT,0);
 drawPts(w,h);}}
// contact dots: projected with the same matrices and drawn on a 2D overlay canvas (always visible)
const ov2=document.createElement('canvas');ov2.style.cssText='position:absolute;left:0;top:0;pointer-events:none';
cv.parentNode.style.position='relative';cv.parentNode.insertBefore(ov2,cv.nextSibling);
const PTS=P.pts.map(p=>({{xyz:dec(p.xyz,Float32Array),color:p.color,size:p.size,label:p.label}}));
function drawPts(w,h){{ov2.width=w;ov2.height=h;ov2.style.width=cv.clientWidth+'px';ov2.style.height=cv.clientHeight+'px';ov2.style.top=cv.offsetTop+'px';ov2.style.left=cv.offsetLeft+'px';
 const g2=ov2.getContext('2d');g2.clearRect(0,0,w,h);if(!PTS.length)return;const M=mat(),a=w/h,f=1/Math.tan(.35);
 for(const p of PTS){{g2.fillStyle=css(p.color)||p.color;g2.strokeStyle=css('--surface')||'#fff';g2.lineWidth=1.5*devicePixelRatio;
  for(let i=0;i<p.xyz.length;i+=3){{const x=p.xyz[i],y=p.xyz[i+1],z=p.xyz[i+2];
   const ex=M[0]*x+M[4]*y+M[8]*z+M[12],ey=M[1]*x+M[5]*y+M[9]*z+M[13],ez=M[2]*x+M[6]*y+M[10]*z+M[14];
   const sx=(f/a*ex/-ez*.5+.5)*w,sy=(1-(f*ey/-ez*.5+.5))*h;g2.beginPath();g2.arc(sx,sy,p.size*devicePixelRatio,0,6.3);g2.fill();g2.stroke();}}}}}}
let drag=null;cv.addEventListener('mousedown',e=>drag=[e.clientX,e.clientY]);addEventListener('mouseup',()=>drag=null);
addEventListener('mousemove',e=>{{if(!drag)return;rz+=(e.clientX-drag[0])*.01;rx+=(e.clientY-drag[1])*.01;drag=[e.clientX,e.clientY];draw();}});
cv.addEventListener('wheel',e=>{{e.preventDefault();zoom=Math.max(1.4,Math.min(6,zoom*(1+e.deltaY*.001)));draw();}},{{passive:false}});
const views={{left:[-1.4,-1.57],right:[-1.4,1.57],top:[0,-1.57],front:[-1.4,3.14]}};
root.querySelectorAll('[data-v]').forEach(b=>b.addEventListener('click',()=>{{[rx,rz]=views[b.dataset.v];draw();}}));
root.querySelector('.b3d-sel').addEventListener('change',e=>{{cur=+e.target.value;paint();}});
new ResizeObserver(draw).observe(cv);matchMedia('(prefers-color-scheme: dark)').addEventListener('change',paint);
new MutationObserver(paint).observe(document.documentElement,{{attributes:true,attributeFilter:['data-theme']}});
paint();
}})();</script>"""


BRAIN_CSS = """
.b3d{border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:10px}
.b3d-bar{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:13px;color:var(--ink2);margin-bottom:6px}
.b3d-bar select,.b3d-bar button{font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:6px;padding:3px 8px;cursor:pointer}
.b3d-views{display:inline-flex;gap:4px}.b3d-scale{display:inline-flex;align-items:center;gap:6px;font-variant-numeric:tabular-nums}
.b3d-grad{display:inline-block;width:120px;height:10px;border-radius:5px}.b3d-cv{display:block;cursor:grab;border-radius:8px}
.b3d-hint{font-size:12px;color:var(--muted);margin-top:4px}
.b3d-pt{display:inline-flex;align-items:center;gap:5px}.b3d-pt span{width:10px;height:10px;border-radius:50%;display:inline-block}
"""


def ti_overlays(emf_dir):
    """E1, E2 normal fields and the TI modulation depth 2*min(|E1n|,|E2n|) (collinear-component approximation)."""
    import nibabel as nib
    g = {}
    for k in ("E1", "E2"):
        g[k] = np.concatenate([np.squeeze(np.asarray(nib.load(f"{emf_dir}/{h}.{k}_normal_field_fs_ico5.mgh").get_fdata()))
                               for h in ("lh", "rh")]).astype(np.float32)
    depth = 2 * np.minimum(np.abs(g["E1"]), np.abs(g["E2"]))
    return [{"name": "TI modulation depth 2·min(|E1|,|E2|)", "values": depth, "unit": "(file units)", "cmap": "seq"},
            {"name": "Field E1 (1000 Hz pair), normal component", "values": g["E1"], "unit": "(file units)", "cmap": "div"},
            {"name": "Field E2 (1005 Hz pair), normal component", "values": g["E2"], "unit": "(file units)", "cmap": "div"}]
