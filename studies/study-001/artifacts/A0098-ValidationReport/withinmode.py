"""R-hat within groups of chains sharing the same L-BFGS init (within-mode) vs across all chains."""
import sys, json
sys.path.insert(0, 'studies/study-001/work/T0031'); import diag
import numpy as np
W = 'studies/study-001/work'
groups = {
 'T0026': (W + '/T0026/out/nuts/chain%d.csv', [[1, 2], [3, 4], [5, 6], [7, 8]]),
 'T0029A': (W + '/T0029/out/nuts_A/chain%d.csv', [[1, 2], [5, 6]]),
 'T0029B': (W + '/T0029/out/nuts_B/chain%d.csv', [[1, 2], [3, 4], [5, 6]]),
}
out = {}
for lab, (pat, gs) in groups.items():
    data = {}
    for g in gs:
        for c in g:
            h, a, _ = diag.read_csv(pat % c); data[c] = (h, a)
    h = data[gs[0][0]][0]; col = {n: i for i, n in enumerate(h)}
    xc = [col['x0.%d' % (i + 1)] for i in range(162)]
    res = {}
    for g in gs:
        n = min(data[c][1].shape[0] for c in g)
        X = np.stack([data[c][1][:n][:, xc] for c in g])
        rh = np.array([diag.rhat_rank(X[:, :, i]) for i in range(162)])
        lp = np.stack([data[c][1][:n][:, col['lp__']] for c in g])
        # first-half vs second-half drift of lp within chains
        res[str(g)] = dict(x0_rhat_max=round(float(rh.max()), 3), x0_rhat_median=round(float(np.median(rh)), 3),
                           n_gt_1_05=int((rh > 1.05).sum()), lp_rhat=round(float(diag.rhat_rank(lp)), 3),
                           lp_first_half_mean=[round(float(l[:n//2].mean()), 1) for l in lp],
                           lp_second_half_mean=[round(float(l[n//2:].mean()), 1) for l in lp])
    out[lab] = res
print(json.dumps(out, indent=1))
json.dump(out, open(W + '/T0031/withinmode.json', 'w'), indent=1)
