import hashlib, csv, os, json, sys
import numpy as np, nibabel as nib
root = "data/wang-5367ef4"
man = {r[0]:(int(r[1]),r[2]) for r in csv.reader(open("data/wang-5367ef4-manifest.csv")) if r}
out = {"hash": {}, "npz": {}, "mgh": {}}
local = []
for d,_,fs in os.walk(root):
    for f in fs: local.append(os.path.relpath(os.path.join(d,f), root).replace("\\","/"))
out["n_local"]=len(local); out["n_manifest"]=len(man)
out["extra"]=sorted(set(local)-set(man)); out["missing"]=sorted(set(man)-set(local))
for p in sorted(man):
    b=open(os.path.join(root,p),"rb").read()  # bytes only; hashing reserved files does not parse them
    h=hashlib.sha256(b).hexdigest()
    out["hash"][p]={"sha256":h,"bytes":len(b),"match":h==man[p][1] and len(b)==man[p][0]}
scs={}
for p in sorted(x for x in man if x.endswith(".npz")):
    z=np.load(os.path.join(root,p))
    info={}
    for k in z.files:
        a=z[k]; info[k]={"shape":list(a.shape),"dtype":str(a.dtype)}
        if a.dtype.kind in "fi":
            info[k].update(min=float(a.min()),max=float(a.max()),nan=int(np.isnan(a).sum()) if a.dtype.kind=="f" else 0)
    t=z["time_steps"]; d=np.diff(t)
    info["t_first_last"]=[float(t[0]),float(t[-1])]; info["dt_unique"]=sorted(set(np.round(d,6).tolist()))
    SC=z["SC"]; info["SC_sym"]=bool(np.allclose(SC,SC.T)); info["SC_diag0"]=bool(np.all(np.diag(SC)==0)); info["SC_max"]=float(SC.max())
    info["SC_sha12"]=hashlib.sha256(np.ascontiguousarray(SC).tobytes()).hexdigest()[:12]
    if "ch_names" in z.files:
        c=z["ch_names"]; info["ch_first_last"]=[str(c[0]),str(c[-1])]
    out["npz"][p]=info
for p in sorted(x for x in man if x.endswith(".mgh")):
    im=nib.load(os.path.join(root,p)); a=np.asanyarray(im.dataobj)
    out["mgh"][p]={"shape":list(a.shape),"dtype":str(im.get_data_dtype()),"min":float(a.min()),"max":float(a.max()),"nan":int(np.isnan(a).sum()),"zooms":[float(x) for x in im.header.get_zooms()]}
lut=open(os.path.join(root,"data/VepMrtrixLut.txt")).read().splitlines()
lut=[l for l in lut if l.strip() and not l.startswith("#")]
out["lut"]={"n":len(lut),"first":lut[0][:60],"second":lut[1][:60],"last":lut[-1][:60]}
out["license_head"]=open(os.path.join(root,"LICENSE")).read()[:120]
json.dump(out,open(sys.argv[1],"w"),indent=1)
print(json.dumps(out,indent=1))
