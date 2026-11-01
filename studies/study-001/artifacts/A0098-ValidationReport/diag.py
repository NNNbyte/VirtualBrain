"""T0031 (R5) independent recomputation of NUTS diagnostics, EZ ranks and false positives
from the stored CmdStan CSV draws of T0026 and T0029. Own implementation of rank-normalised
split R-hat and bulk/tail ESS (Vehtari et al. 2021), not R3's analysis code.

usage: python diag.py <label> <truth_ez_idx0> <comma-separated pz idx0 or -> <out.json> <chain.csv>...
"""
import sys, json
import numpy as np
from scipy.stats import norm, rankdata

LUT = [l.split()[1] for l in open(".venv-model/Lib/site-packages/vep_stim/core/util/data/VepMrtrixLut.txt")
       if l.strip() and not l.startswith('#')][1:]
THR = -2.05


def read_csv(path):
    with open(path) as f:
        lines = [l for l in f if not l.startswith('#') and l.strip()]
    header = lines[0].strip().split(',')
    arr = np.array([[float(v) for v in l.strip().split(',')] for l in lines[1:]]) if len(lines) > 1 else np.zeros((0, len(header)))
    meta = {}
    with open(path) as f:
        for l in f:
            if l.startswith('#') and '=' in l:
                k, v = l[1:].split('=', 1); meta.setdefault(k.strip(), v.strip())
    return header, arr, meta


def split_chains(x):  # x: (chains, draws)
    n = x.shape[1] // 2
    return np.concatenate([x[:, :n], x[:, -n:]], axis=0)


def rhat_basic(x):
    m, n = x.shape
    cm = x.mean(1); cv = x.var(1, ddof=1)
    B = n * cm.var(ddof=1); W = cv.mean()
    if W <= 0:
        return np.nan
    var = (n - 1) / n * W + B / n
    return np.sqrt(var / W)


def z_scale(x):
    r = rankdata(x, method='average').reshape(x.shape)
    return norm.ppf((r - 3 / 8) / (x.size + 1 / 4))


def rhat_rank(x):
    s = split_chains(x)
    r1 = rhat_basic(z_scale(s))
    f = np.abs(s - np.median(s))
    r2 = rhat_basic(z_scale(f))
    return max(r1, r2)


def autocov(x):
    n = len(x)
    xc = x - x.mean()
    nfft = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(xc, nfft)
    ac = np.fft.irfft(f * np.conj(f), nfft)[:n] / n
    return ac


def ess(x):  # x: (chains, draws); Geyer initial-positive + monotone (as in Stan/arviz)
    m, n = x.shape
    if np.all(x.var(1) == 0):
        return np.nan
    acov = np.array([autocov(c) for c in x])
    chain_mean = x.mean(1); chain_var = acov[:, 0] * n / (n - 1)
    mean_var = chain_var.mean()
    var_plus = mean_var * (n - 1) / n
    if m > 1:
        var_plus += chain_mean.var(ddof=1)
    rho = np.zeros(n)
    rho_even = 1.0; rho[0] = rho_even
    rho_odd = 1 - (mean_var - acov[:, 1].mean()) / var_plus; rho[1] = rho_odd
    t = 1
    while t < n - 3 and (rho_even + rho_odd) > 0:
        rho_even = 1 - (mean_var - acov[:, t + 1].mean()) / var_plus
        rho_odd = 1 - (mean_var - acov[:, t + 2].mean()) / var_plus
        if rho_even + rho_odd >= 0:
            rho[t + 1] = rho_even; rho[t + 2] = rho_odd
        t += 2
    max_t = t - 2
    if rho_even > 0:
        rho[max_t + 1] = rho_even
    t = 1
    while t <= max_t - 2:
        if rho[t + 1] + rho[t + 2] > rho[t - 1] + rho[t]:
            rho[t + 1] = (rho[t - 1] + rho[t]) / 2; rho[t + 2] = rho[t + 1]
        t += 2
    tau = -1 + 2 * rho[:max_t + 1].sum() + rho[max_t + 1:max_t + 2].sum()
    tau = max(tau, 1 / np.log10(m * n))
    return m * n / tau


def ess_bulk(x):
    return ess(z_scale(split_chains(x)))


def ess_tail(x):
    s = split_chains(x)
    q05, q95 = np.quantile(s, [0.05, 0.95])
    return min(ess(z_scale((s <= q05).astype(float))), ess(z_scale((s >= q95).astype(float))))


def main():
    label, ez, pz, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    pz = [] if pz == '-' else [int(v) for v in pz.split(',')]
    files = sys.argv[5:]
    chains, metas, names = [], [], None
    for f in files:
        h, a, meta = read_csv(f)
        if a.shape[0] == 0:
            print('EMPTY', f); continue
        names = h; chains.append(a); metas.append((f, meta))
    ndraw = min(c.shape[0] for c in chains)
    chains = [c[:ndraw] for c in chains]
    D = np.stack(chains)  # (m, n, p)
    col = {n: i for i, n in enumerate(names)}
    x0_cols = [col['x0.%d' % (i + 1)] for i in range(len(LUT))]
    X0 = D[:, :, x0_cols]  # (m, n, nn)
    m, n, nn = X0.shape
    res = dict(label=label, files=[f for f, _ in metas], n_chains=m, draws_per_chain=n)
    # sampler diagnostics
    td = D[:, :, col['treedepth__']]; div = D[:, :, col['divergent__']]
    maxdepth = [int(meta.get('max_depth', -1)) for _, meta in metas]
    res['max_depth_cfg'] = maxdepth
    res['divergences_per_chain'] = div.sum(1).astype(int).tolist()
    res['treedepth_mean'] = float(td.mean())
    res['n_at_max_depth'] = int(sum((td[i] >= maxdepth[i]).sum() for i in range(m)))
    res['stepsize_per_chain'] = D[:, 0, col['stepsize__']].tolist()
    res['accept_stat_mean'] = float(D[:, :, col['accept_stat__']].mean())
    res['lp_mean_per_chain'] = D[:, :, col['lp__']].mean(1).round(2).tolist()
    # R-hat / ESS
    rh = np.array([rhat_rank(X0[:, :, i]) for i in range(nn)])
    eb = np.array([ess_bulk(X0[:, :, i]) for i in range(nn)])
    et = np.array([ess_tail(X0[:, :, i]) for i in range(nn)])
    res['x0_rhat_max'] = float(np.nanmax(rh)); res['x0_rhat_median'] = float(np.nanmedian(rh))
    res['x0_n_rhat_gt_1_05'] = int((rh > 1.05).sum()); res['x0_n_rhat_gt_1_01'] = int((rh > 1.01).sum())
    res['x0_ess_bulk_min'] = float(np.nanmin(eb)); res['x0_ess_bulk_median'] = float(np.nanmedian(eb))
    res['x0_ess_tail_min'] = float(np.nanmin(et))
    for p in ['lp__', 'K', 'amp', 'eps']:
        v = D[:, :, col[p]]
        res['rhat_' + p] = float(rhat_rank(v)); res['ess_bulk_' + p] = float(ess_bulk(v))
        res['mean_' + p] = float(v.mean()); res['mean_per_chain_' + p] = v.mean(1).round(5).tolist()
    res['EZ'] = LUT[ez]; res['EZ_rhat'] = float(rh[ez]); res['EZ_ess_bulk'] = float(eb[ez])
    # recovery
    pm = X0.reshape(-1, nn).mean(0)
    order = np.argsort(-pm)
    res['EZ_rank_pooled_mean'] = int(np.where(order == ez)[0][0] + 1)
    res['EZ_x0_mean'] = float(pm[ez]); res['EZ_x0_sd'] = float(X0[:, :, ez].std())
    res['EZ_rank_per_chain'] = [int(np.where(np.argsort(-X0[c].mean(0)) == ez)[0][0] + 1) for c in range(m)]
    res['EZ_x0_mean_per_chain'] = X0[:, :, ez].mean(1).round(3).tolist()
    draws = X0.reshape(-1, nn)
    res['EZ_P_rank1'] = float((draws.argmax(1) == ez).mean())
    pg = (draws > THR).mean(0)
    res['EZ_P_gt_thr'] = float(pg[ez])
    above = [i for i in np.argsort(-pg) if pg[i] > 0.5]
    res['regions_P_gt_thr_above_0_5'] = [dict(region=LUT[i], P=round(float(pg[i]), 4), mean=round(float(pm[i]), 4)) for i in above]
    res['false_positives_excl_EZ_PZ'] = [LUT[i] for i in above if i != ez and i not in pz]
    res['false_positives_excl_EZ_only'] = [LUT[i] for i in above if i != ez]
    res['top10_pooled_mean'] = [(LUT[i], round(float(pm[i]), 3), round(float(rh[i]), 3)) for i in order[:10]]
    res['top5_per_chain'] = [[LUT[i] for i in np.argsort(-X0[c].mean(0))[:5]] for c in range(m)]
    res['n_regions_P_gt_thr_gt_0_5_per_chain'] = [int(((X0[c] > THR).mean(0) > 0.5).sum()) for c in range(m)]
    for i in pz:
        res.setdefault('PZ', []).append(dict(region=LUT[i], mean=float(pm[i]), rank=int(np.where(order == i)[0][0] + 1), P_gt_thr=float(pg[i])))
    # between-chain spread of top regions (mode vs mixing)
    json.dump(res, open(out, 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
