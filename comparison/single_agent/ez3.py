import numpy as np, scipy.optimize as so
D='../../data/wang-5367ef4/data/'
d=np.load(D+'dataSim/Patient2/P2_SEEG_ts_fit.npz')
names=[l.split()[1] for l in open(D+'VepMrtrixLut.txt') if l.strip()][1:]
Y=d['seeg']; G=d['gain']; SC=d['SC']; ch=d['ch_names']
act=np.abs(np.diff(Y[:,100:950],axis=1)).sum(1)  # ictal activity per channel
dev=np.abs(Y[:,100:950].mean(1)-Y[:,1100:].mean(1))
f=act/act.max()
print('top channels',[ (str(ch[i]),round(f[i],2)) for i in np.argsort(-f)[:10]])
Gn=G/G.max()
a,_=so.nnls(np.vstack([Gn,0.05*np.eye(162)]),np.concatenate([f,np.zeros(162)]))
cr=(G/np.linalg.norm(G,axis=0)).T@(f/np.linalg.norm(f))
score=a/a.max()
o=np.argsort(-score)
print('NNLS fit r',np.corrcoef(Gn@a,f)[0,1].round(3))
for r,i in enumerate(o[:10]): print(r+1,i,names[i],round(score[i],3),'corr',round(cr[i],3))
np.save('ez_score.npy',score)
# --- simulations: 2D Epileptor network (same equations as vep_stim/stan/vep_mcmc.stan)
ez=o[:3]; pz=o[3:6]
def sim(x0,K=1.0,stim=None,keep=None,T=6000,dt=0.1):
    W=SC.copy()
    if keep is not None: W[~keep]=0; W[:,~keep]=0
    x=-1.98*np.ones(162); z=4.1*np.ones(162); I1=3.1; tau0=15.
    xs=np.empty((T,162))
    for k in range(T):
        gx=W@x - W.sum(1)*x
        I=I1+(stim if stim is not None else 0)
        dx=1-x**3-2*x**2-z+I; dz=(4*(x-x0)-z-K*gx)/tau0
        x=x+dt*dx; z=z+dt*dz; xs[k]=x
    return xs
def nseiz(xs,keep=None):
    s=(xs.max(0)>0)
    if keep is not None: s&=keep
    return s
x0=-2.5*np.ones(162); x0[ez]=-1.6; x0[pz]=-2.0
res={}
xs=sim(x0); res['baseline']=nseiz(xs)
for nm,idx in [('resect_top1',o[:1]),('resect_top3',ez),('resect_top6',o[:6])]:
    keep=np.ones(162,bool); keep[idx]=False
    x0r=x0.copy(); x0r[idx]=-3.0
    res[nm]=nseiz(sim(x0r,keep=keep),keep)
for amp in [-0.5,-1.0,-2.0]:
    st=np.zeros(162); st[ez]=amp
    res[f'stim_EZ_{amp}']=nseiz(sim(x0,stim=st))
    st=np.zeros(162); st[o[:1]]=amp
    res[f'stim_top1_{amp}']=nseiz(sim(x0,stim=st))
for k,v in res.items(): print(k,'n_seizing',int(v.sum()),[names[i] for i in np.where(v)[0]][:8])
