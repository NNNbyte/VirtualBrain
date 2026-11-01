import json, numpy as np, sys
sys.path.insert(0,'work/T0020'); 
exec(open('work/T0020/diag.py').read().split('out={}')[0])
res={}
for arm in 'AB':
    x=np.load(f'work/T0011/results/{arm}_run2/x0_draws.npy').reshape(16,200,162)
    rh=np.array([rhat(x[:,:,j]) for j in range(162)])
    pm=x.reshape(-1,162).mean(0); order=np.argsort(-pm); top1=np.argmax(x.reshape(-1,162),1)
    res[arm]=dict(max_rhat=round(float(rh.max()),3), n_ge_105=int((rh>=1.05).sum()), top5=order[:5].tolist(), rank44=int(np.where(order==44)[0][0])+1,
      P44=round(float(np.mean(top1==44)),4), P40=round(float(np.mean(top1==40)),4), P42=round(float(np.mean(top1==42)),4),
      chains_ez_first=int(sum(np.argmax(x[c].mean(0))==44 for c in range(16))))
s=json.load(open('work/T0020/diag_out.json')); s['A0037_rhat_recomputed']=res; json.dump(s,open('work/T0020/diag_out.json','w'),indent=1)
print(res)
