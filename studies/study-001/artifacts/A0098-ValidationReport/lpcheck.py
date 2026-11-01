"""T0031 (R5) independent log-density checks (no fitting).
1. Patch P1: numpy re-implementation of the model (own code) vs Stan log_prob of the patched exe
   (T0029/stan/vep_mcmc_fixed.exe) and of the package model (T0026/stan/vep_mcmc_nogq.exe, model block
   identical to vep_stim/stan/vep_mcmc.stan sha 5368394c...) at several parameter points.
2. Decompose log posterior (prior vs likelihood) at the planted truth and at stored NUTS draws of
   arm A/B, to see whether the posterior itself prefers the wrong configuration (pipeline-level) or the
   sampler simply failed to reach the truth (run-level).
"""
import sys, os, json
sys.path.insert(0, ".tools"); import stan_env  # noqa
import numpy as np
import cmdstanpy
cmdstanpy.set_cmdstan_path(os.environ["CMDSTAN"])
import logging; logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

W = "studies/study-001/work"
OUT = f"{W}/T0031"
LUT = [l.split()[1] for l in open(".venv-model/Lib/site-packages/vep_stim/core/util/data/VepMrtrixLut.txt")
       if l.strip() and not l.startswith('#')][1:]


def forward(d, p):
    nn, nt = d['nn'], d['nt']
    SC = np.asarray(d['SC']); gain = np.asarray(d['gain']); eig = np.asarray(d['eig'])
    x0 = -3.0 + 0.3 * eig @ p['x0_star']; z = 4.1 + 0.1 * eig @ p['z_init_star']
    K = 1.0 + p['K_star']; amp = 0.005 + 0.01 * p['amp_star']; u = 2.0 + p['u_star']
    eps = np.exp(0.33 * p['log_eps_sq'] - 3.0)
    x = np.empty((nn, nt)); x[:, 0] = -1.98; xt = x[:, 0].copy(); zt = z.copy()
    for t in range(nt - 1):
        gx = SC @ xt - SC.sum(1) * xt
        xn = xt + 0.1 * (1.0 - xt ** 3 - 2.0 * xt ** 2 - zt + 3.1)
        zt = zt + 0.1 * ((1 / 15.0) * (4 * (xt - x0) - zt - K * gx))
        xt = xn; x[:, t + 1] = xt
    xhat = (amp * (gain @ x)).T + u[None, :]  # (nt, ns)
    return xhat, eps, dict(x0=x0, K=K, amp=amp, eps=eps, x=x)


def logpdf(y, m, s):
    return -0.5 * ((y - m) / s) ** 2 - np.log(s) - 0.5 * np.log(2 * np.pi)


def numpy_lp(d, p, mask):
    """mask: 'time' (patched: drop first 10 rows for every channel) or 'colmajor' (package)."""
    y = np.log(np.asarray(d['Obs'])); xhat, eps, _ = forward(d, p)
    nt, ns = y.shape
    if mask == 'time':
        M = np.zeros_like(y, bool); M[10:, :] = True
    else:
        flat = np.zeros(nt * ns, bool); flat[10 * ns:] = True
        M = flat.reshape((ns, nt)).T  # column-major vectorisation of an (nt, ns) matrix
    ll = logpdf(y[M], xhat[M], eps).sum()
    pri = (-0.5 * (np.sum(p['x0_star'] ** 2) + np.sum(p['z_init_star'] ** 2) + p['K_star'] ** 2 + p['amp_star'] ** 2
                  + np.sum(p['u_star'] ** 2)) - 0.5 * p['log_eps_sq'] ** 2 / 100.0)
    dropped = sorted(set(np.where(~M.all(0) & ~M.any(0))[0].tolist()))
    partial = sorted(set(np.where(~M.all(0) & M.any(0))[0].tolist()))
    return dict(loglik_full_const=float(ll), prior_kernel=float(pri), n_terms=int(M.sum()),
                channels_fully_dropped=dropped, channels_partly_dropped={int(c): int((~M[:, c]).sum()) for c in partial})


def draw_params(csv, k, ns, nn):
    lines = [l for l in open(csv) if not l.startswith('#') and l.strip()]
    h = lines[0].strip().split(','); v = np.array([float(a) for a in lines[1:][k].strip().split(",")])
    c = {n: i for i, n in enumerate(h)}
    g = lambda name, n: np.array([v[c[f'{name}.{i + 1}']] for i in range(n)])
    return dict(x0_star=g('x0_star', nn), z_init_star=g('z_init_star', nn), K_star=float(v[c['K_star']]),
                amp_star=float(v[c['amp_star']]), u_star=g('u_star', ns), log_eps_sq=float(v[c['log_eps_sq']]),
                lp__=float(v[c['lp__']]))


def stan_lp(exe, data_file, p, tag):
    m = cmdstanpy.CmdStanModel(exe_file=exe)
    pj = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in p.items() if k != 'lp__'}
    pf = f"{OUT}/lp_params_{tag}.json"; json.dump(pj, open(pf, 'w'))
    r = m.log_prob(params=pf, data=data_file, jacobian=False)
    return float(r['lp__'].iloc[0])


def main():
    res = {}
    t0 = json.load(open(f"{W}/T0029/out/synth/truth_params_unconstrained.json"))
    truth = {k: (np.array(v) if isinstance(v, list) else v) for k, v in t0.items()}
    # independent check that truth_params_unconstrained encodes the planted x0 / amp / K / u
    tr = json.load(open(f"{W}/T0029/out/synth/truth.json"))
    for arm in ['A', 'B']:
        df = f"{W}/T0029/out/synth/data_arm{arm}.json"; d = json.load(open(df))
        ns, nn = d['ns'], d['nn']
        if arm == 'A':
            _, _, aux = forward(d, truth)
            res['truth_param_consistency'] = dict(max_abs_x0_diff=float(np.abs(aux['x0'] - np.array(tr['x0'])).max()),
                                                  amp=aux['amp'], K=aux['K'], eps=float(aux['eps']),
                                                  max_abs_u_diff=float(np.abs(2.0 + truth['u_star'] - np.array(tr['u'])).max()))
        pts = {'truth': truth}
        chains = sorted(f for f in os.listdir(f"{W}/T0029/out/nuts_{arm}") if f.startswith('chain') and f.endswith('.csv'))
        for cf in chains:
            path = f"{W}/T0029/out/nuts_{arm}/{cf}"
            try:
                pts[cf.replace('.csv', '') + '_last'] = draw_params(path, -1, ns, nn)
            except Exception:
                pass
        out = {}
        for name, p in pts.items():
            r = dict(patched_numpy=numpy_lp(d, p, 'time'), package_numpy=numpy_lp(d, p, 'colmajor'))
            if 'lp__' in p:
                r['stored_lp__'] = p['lp__']
            out[name] = r
        # Stan comparisons on two points (truth, first chain last draw)
        for name in ['truth', [k for k in pts if k != 'truth'][0]]:
            p = pts[name]
            sp = stan_lp(f"{W}/T0029/stan/vep_mcmc_fixed.exe", df, p, f"{arm}_{name}_fixed")
            sk = stan_lp(f"{W}/T0026/stan/vep_mcmc_nogq.exe", df, p, f"{arm}_{name}_pkg")
            npat = out[name]['patched_numpy']; npkg = out[name]['package_numpy']
            const = 0.5 * np.log(2 * np.pi) * npat['n_terms']
            out[name]['stan_patched_lp'] = sp
            out[name]['stan_package_lp'] = sk
            # patched uses '~' (drops -0.5 log 2pi per term); package uses target += normal_lpdf (keeps it)
            out[name]['diff_stan_patched_vs_numpy_time_mask'] = sp - (npat['loglik_full_const'] + const + npat['prior_kernel'])
            out[name]['diff_stan_package_vs_numpy_colmajor_mask'] = sk - (npkg['loglik_full_const'] + npkg['prior_kernel'])
            out[name]['diff_stan_package_vs_numpy_time_mask'] = sk - (npat['loglik_full_const'] + npat['prior_kernel'])
        res[arm] = out
    json.dump(res, open(f"{OUT}/lpcheck.json", 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
