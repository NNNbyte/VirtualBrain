import numpy as np, scipy.optimize as so, json
D='../../data/wang-5367ef4/data/'
d=np.load(D+'dataSim/Patient2/P2_SEEG_ts_fit.npz')
names=[l.split()[1] for l in open(D+'VepMrtrixLut.txt') if l.strip()][1:]
Y=d['seeg']; G=d['gain']; t=d['time_steps']; ch=d['ch_names']
base=Y[:,:20].mean(1,keepdims=True); dY=Y-base
A=np.abs(dY).max(1)
top=np.argsort(-A)[:15]
for c in top:
    tr=dY[c]; on=np.argmax(np.abs(tr)>0.5*A[c]); print(ch[c], round(A[c],3), 'sign',np.sign(tr[np.argmax(np.abs(tr))]),'t50',t[on])
# feature: signed final change (late window) & early
late=dY[:,-200:].mean(1)
# NNLS with ridge: min ||G a - late||^2 + lam||a||^2, a>=0 (seizure amplitude per region)
for lam in [1e-2,1e-1,1.0]:
    Gr=np.vstack([G,np.sqrt(lam)*np.eye(162)]); yr=np.concatenate([np.abs(late) if False else late, np.zeros(162)])
    a,_=so.nnls(Gr,yr)
    o=np.argsort(-a)[:10]; print('lam',lam,'fit r', np.corrcoef(G@a,late)[0,1].round(3), [(int(i),names[i],round(a[i],3)) for i in o])
# correlation ranking: normalized gain column vs feature
Gn=G/np.linalg.norm(G,axis=0); cr=Gn.T@(np.abs(late)/np.linalg.norm(late))
o=np.argsort(-cr)[:10]; print('corr',[(int(i),names[i],round(cr[i],3)) for i in o])
