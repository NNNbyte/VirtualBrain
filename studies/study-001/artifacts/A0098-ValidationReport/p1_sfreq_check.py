"""T0031 (R5) cheap check: does the VBT-P1 recovery failure (T0026) depend on the 250-vs-100 Hz feature
recipe error and the likelihood channel-skip bug? Features: T0026 notebook recipe unchanged EXCEPT sfreq=100
(from time_steps, 10 ms). Model: T0029 patched likelihood (vep_mcmc_fixed.exe). A few short L-BFGS starts
only (no NUTS). Output: per-optimum Left-O2 rank by x0 and the supra-threshold set.
Usage: python p1_sfreq_check.py <sfreq> <n_starts> <seed0> <timeout_s>
"""
import sys, os, json, time, subprocess
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".tools"); import stan_env  # noqa
import numpy as np
from vep_stim.core import vep_prepare_op

sfreq, n_starts, seed0, tmo = float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
OUT = f"studies/study-001/work/T0031/p1_sfreq{int(sfreq)}"; os.makedirs(OUT, exist_ok=True)
EXE = os.path.abspath("studies/study-001/work/T0029/stan/vep_mcmc_fixed.exe")
LUT = [l.split()[1] for l in open(".venv-model/Lib/site-packages/vep_stim/core/util/data/VepMrtrixLut.txt")
       if l.strip() and not l.startswith('#')][1:]
O2 = LUT.index('Left-O2')

d = np.load("studies/study-001/artifacts/A0067-DatasetCard/P1_SEEG_SEEG_fit.npz", allow_pickle=False)
gain, seeg, SC, tts = d['gain'], d['seeg'], d['SC'], d['time_steps']
assert abs(1000.0 / np.diff(tts).mean() - 100.0) < 1e-9
rng = np.random.RandomState(20261101)
hpf, lpf, n_samples = 10, 1, 150
seg = seeg[:, 100:700]
s4f = -(seg - seg.mean(axis=0)) + rng.normal(0, 0.2, size=len(seg.T))
s4f = np.concatenate([rng.normal(0, 0.2, size=[len(seeg), 300]), s4f, rng.normal(0, 0.2, size=[len(seeg), 200])], axis=1)
data = vep_prepare_op.prepare_data_feature_op(SC, s4f.T, gain, sfreq, hpf, lpf)
df = data['slp']; ds = int(df.shape[0] / n_samples)
dfr = df[0:-1:ds] - np.min(df); dfr = dfr - np.min(dfr) + 1
U, s, Vh = np.linalg.svd(gain)
rd = {'ns': int(gain.shape[0]), 'nn': int(gain.shape[1]), 'nt': int(dfr.shape[0]), 'Obs': dfr.tolist(),
      'SC': SC.tolist(), 'gain': gain.tolist(), 'eig': Vh.T.tolist()}
DATA = f"{OUT}/data.json"; json.dump(rd, open(DATA, 'w'))
print('features', dict(sfreq=sfreq, nt=rd['nt'], ns=rd['ns'], ds=ds, Obs_max=float(dfr.max())), flush=True)


def one(j):
    seed = seed0 + j; csv = f"{OUT}/j{j:02d}.csv"; log = f"{OUT}/j{j:02d}.log"
    cmd = [EXE, f"id={j+1}", "optimize", "algorithm=lbfgs", "tol_param=1e-10", "tol_rel_grad=1e2", "tol_rel_obj=1e1",
           "iter=20000", "random", f"seed={seed}", "data", f"file={DATA}", "init=2", "output", f"file={csv}", "refresh=200"]
    t = time.time()
    with open(log, "w") as fh:
        try:
            rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=tmo)
        except subprocess.TimeoutExpired:
            rc = 'timeout'
    rec = dict(job=j, seed=seed, rc=rc, seconds=round(time.time() - t, 1))
    try:
        lines = [l for l in open(csv) if not l.startswith('#') and l.strip()]
        h = lines[0].strip().split(','); v = np.array([float(a) for a in lines[-1].strip().split(',')])
        c = {n: i for i, n in enumerate(h)}
        x0 = np.array([v[c[f'x0.{i+1}']] for i in range(len(LUT))])
        order = np.argsort(-x0)
        rec.update(lp=float(v[c['lp__']]), amp=float(v[c['amp']]), K=float(v[c['K']]), eps=float(v[c['eps']]),
                   O2_x0=float(x0[O2]), O2_rank=int(np.where(order == O2)[0][0] + 1),
                   n_gt_thr=int((x0 > -2.05).sum()), top5=[(LUT[i], round(float(x0[i]), 2)) for i in order[:5]])
        rec['converged'] = 'converged' in open(log, errors='ignore').read().lower()
    except Exception as e:
        rec['error'] = repr(e)[:200]
    print(json.dumps(rec), flush=True)
    return rec


with ThreadPoolExecutor(n_starts) as ex:
    res = list(ex.map(one, range(n_starts)))
json.dump(res, open(f"{OUT}/summary.json", "w"), indent=1)
