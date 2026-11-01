import numpy as np, scipy.optimize as so
D='../../data/wang-5367ef4/data/'
d=np.load(D+'dataSim/Patient2/P2_SEEG_ts_fit.npz')
names=[l.split()[1] for l in open(D+'VepMrtrixLut.txt') if l.strip()][1:]
assert len(names)==162
Y=d['seeg']; G=d['gain']; SC=d['SC']; t=d['time_steps']
print('cond(G)',np.linalg.cond(G))
# per-channel change from baseline
base=Y[:,:50].mean(1,keepdims=True); dY=Y-base
print('max |dY| per channel top:', np.sort(np.abs(dY).max(1))[-10:])
# region-level inversion with x(t) = a*? ; solve G x = Y (with offset per channel unknown) -> use dY
X,res,rk,sv=np.linalg.lstsq(G,dY,rcond=1e-6)
print('rank',rk,'resid rel',np.linalg.norm(G@X-dY)/np.linalg.norm(dY))
# NNLS on final change
amp=np.abs(dY).max(1)
# onset per region: time when inverted dX crosses half of its max
Xm=X.max(1); order=np.argsort(-Xm)
for i in order[:20]:
    on=np.argmax(X[i]>0.5*Xm[i]) if Xm[i]>0 else -1
    print(i,names[i],round(Xm[i],3),'onset_t',t[on] if on>=0 else None)
np.save('X_inv.npy',X)
