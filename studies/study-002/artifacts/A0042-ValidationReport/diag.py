import json, hashlib, numpy as np, csv, os
from scipy.stats import rankdata, norm
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def zs(x):  # rank-normalise across all chains
    r = rankdata(x.ravel()).reshape(x.shape); return norm.ppf((r-0.375)/(x.size+0.25))
def rhat_basic(x):  # x: chains x draws, split
    n=x.shape[1]//2; x=np.concatenate([x[:,:n],x[:,n:2*n]],0)
    m,n=x.shape; W=x.var(1,ddof=1).mean(); B=n*x.mean(1).var(ddof=1)
    return np.sqrt(((n-1)/n*W+B/n)/W)
def rhat(x):
    f=np.abs(x-np.median(x)); return max(rhat_basic(zs(x)), rhat_basic(zs(f)))
out={}
# A0037 arm A: compare first-ref hashes to work/T0011/results/A_run2
env=json.load(open('artifacts/A0037-ModelBundle/manifest.json'))['payload_refs']
seen={}; firsts={}
for r in env:
    fn=r['uri'].split('/')[-1]
    if fn in seen: firsts[fn]=(seen[fn], r['sha256'])
    else: seen[fn]=r['sha256']
chk={}
for fn,(h1,h2) in firsts.items():
    pa=f'work/T0011/results/A_run2/{fn}'; pb=f'work/T0011/results/B_run2/{fn}'
    chk[fn]=dict(first_ref_matches_A_run2=os.path.exists(pa) and sha(pa)==h1, second_ref_matches_B_run2=os.path.exists(pb) and sha(pb)==h2,
                 stored_file_matches_second=sha(f'artifacts/A0037-ModelBundle/{fn}')==h2)
out['A0037_attachment_collision']=chk
for arm in ['A','B']:
    x=np.load(f'work/T0011/results/{arm}_run2/x0_draws.npy'); 
    out[f'A0037_arm{arm}_x0_draws_shape']=list(x.shape)
    if x.ndim==3:  # chains, draws, regions ?
        C,D,R=x.shape
        rh=np.array([rhat(x[:,:,j]) for j in range(R)])
        pm=x.reshape(-1,R).mean(0); order=np.argsort(-pm)
        top1=np.argmax(x.reshape(-1,R),1)
        out[f'A0037_arm{arm}']=dict(max_rhat=float(rh.max()), n_rhat_ge_1_05=int((rh>=1.05).sum()), top5_by_mean=order[:5].tolist(),
            rank_of_44=int(np.where(order==44)[0][0])+1, P_rank1_44=float(np.mean(top1==44)),
            per_chain_top1=[int(np.argmax(x[c].mean(0))) for c in range(C)])
# A0019 thinned draws
for w in ['post','full']:
    rows=list(csv.DictReader(open(f'artifacts/A0019-ModelBundle/nuts_posterior_P2_{w}.csv')))
    ch=np.array([int(r['chain']) for r in rows]); X=np.array([[float(r[f'x0_{j}']) for j in range(162)] for r in rows])
    cs=sorted(set(ch)); nmin=min((ch==c).sum() for c in cs)
    A=np.stack([X[ch==c][:nmin] for c in cs])
    rh=np.array([rhat(A[:,:,j]) for j in range(162)])
    pm=X.mean(0); order=np.argsort(-pm); top1=np.argmax(X,1)
    vals,cnt=np.unique(top1,return_counts=True); P=sorted(zip(cnt/len(top1),vals),reverse=True)[:5]
    out[f'A0019_{w}']=dict(n_draws=len(rows), chains=len(cs), draws_per_chain_used=int(nmin), max_rhat_thinned=float(rh.max()),
        median_rhat=float(np.median(rh)), n_rhat_ge_1_05=int((rh>=1.05).sum()), top5_by_mean=order[:5].tolist(),
        P_rank1_top=[(int(v),round(float(p),3)) for p,v in P], P_x0_gt_m2_06={int(j):round(float(np.mean(X[:,j]>-2.06)),3) for j in order[:5]})
# A0018 MAP ensembles
for w in ['post','full']:
    rows=list(csv.DictReader(open(f'artifacts/A0018-ModelBundle/map_ensemble_P2_{w}.csv')))
    X=np.array([[float(r[f'x0_{j}']) for j in range(162)] for r in rows]); lp=np.array([float(r['lp']) for r in rows])
    top1=np.argmax(X,1); vals,cnt=np.unique(top1,return_counts=True)
    med=np.median(X,0); order=np.argsort(-med)
    out[f'A0018_{w}']=dict(n=len(rows), lp_range=[float(lp.min()),float(lp.max())], top1_counts={int(v):int(c) for v,c in zip(vals,cnt)},
        median_x0_top5=[(int(j),round(float(med[j]),3)) for j in order[:5]], max_x0_overall=float(X.max()),
        n_supra_m2_06_median=int((med>-2.06).sum()), terminations=sorted(set(r['termination'] for r in rows)))
# A0040 pathfinder
for k in ['A','B','T11']:
    d=json.load(open(f'artifacts/A0040-ModelBundle/pathfinder_summary_{k}.json'))
    out[f'A0040_pf_{k}_keys']=list(d.keys())[:30]
    out[f'A0040_pf_{k}']={kk:d[kk] for kk in d if not isinstance(d[kk],list) or len(d[kk])<12}
out['A0040_verdict']=json.load(open('artifacts/A0040-ModelBundle/verdict.json'))
json.dump(out,open('work/T0020/diag_out.json','w'),indent=1,default=str)
print(json.dumps(out,indent=1,default=str)[:9000])
