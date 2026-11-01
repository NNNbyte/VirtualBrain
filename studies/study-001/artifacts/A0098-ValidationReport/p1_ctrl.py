"""Controls for the P1 check: (a) patched model started from T0026's best package-model optimum (job 11);
(b) package model (T0026 vep_mcmc_nogq.exe) with init=2 on the same T0026 features (seeds 3100..), to separate
the likelihood fix from the init radius. Short L-BFGS only."""
import sys, os, json, time, subprocess
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".tools"); import stan_env  # noqa
import numpy as np
W = "studies/study-001/work"; OUT = f"{W}/T0031/p1_ctrl"; os.makedirs(OUT, exist_ok=True)
LUT = [l.split()[1] for l in open(".venv-model/Lib/site-packages/vep_stim/core/util/data/VepMrtrixLut.txt")
       if l.strip() and not l.startswith('#')][1:]
O2 = LUT.index('Left-O2')
DATA = os.path.abspath(f"{W}/T0031/p1_sfreq250/data.json")
FIX = os.path.abspath(f"{W}/T0029/stan/vep_mcmc_fixed.exe"); PKG = os.path.abspath(f"{W}/T0026/stan/vep_mcmc_nogq.exe")
INIT11 = os.path.abspath(f"{W}/T0026/out/nuts/init_b0_optjob11.json")
jobs = [("fix_from_job11", FIX, INIT11, 4100), ("fix_from_job11_b", FIX, INIT11, 4101)] + \
       [(f"pkg_init2_s{s}", PKG, "2", s) for s in (3100, 3101, 3102, 3103)]


def one(job):
    name, exe, init, seed = job; csv = f"{OUT}/{name}.csv"; log = f"{OUT}/{name}.log"
    cmd = [exe, "optimize", "algorithm=lbfgs", "tol_param=1e-10", "tol_rel_grad=1e2", "tol_rel_obj=1e1", "iter=20000",
           "random", f"seed={seed}", "data", f"file={DATA}", f"init={init}", "output", f"file={csv}", "refresh=200"]
    t = time.time()
    for attempt in range(3):
        with open(log, "w") as fh:
            try:
                rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=540)
            except subprocess.TimeoutExpired:
                rc = 'timeout'
        if rc != 3221225477:
            break
        time.sleep(2)
    rec = dict(name=name, seed=seed, rc=rc, seconds=round(time.time() - t, 1))
    txt = open(log, errors='ignore').read()
    rec['terminated_normally'] = 'Optimization terminated normally' in txt
    try:
        lines = [l for l in open(csv) if not l.startswith('#') and l.strip()]
        h = lines[0].strip().split(','); v = np.array([float(a) for a in lines[-1].strip().split(',')])
        c = {n: i for i, n in enumerate(h)}
        x0 = np.array([v[c[f'x0.{i+1}']] for i in range(len(LUT))]); order = np.argsort(-x0)
        rec.update(lp=float(v[c['lp__']]), amp=float(v[c['amp']]), K=float(v[c['K']]), eps=float(v[c['eps']]),
                   O2_x0=float(x0[O2]), O2_rank=int(np.where(order == O2)[0][0] + 1), n_gt_thr=int((x0 > -2.05).sum()),
                   top5=[(LUT[i], round(float(x0[i]), 2)) for i in order[:5]])
    except Exception as e:
        rec['error'] = repr(e)[:200]
    print(json.dumps(rec), flush=True); return rec


with ThreadPoolExecutor(len(jobs)) as ex:
    res = list(ex.map(one, jobs))
json.dump(res, open(f"{OUT}/summary.json", "w"), indent=1)
