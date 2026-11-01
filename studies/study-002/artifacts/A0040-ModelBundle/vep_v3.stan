// study-002 T0018 model v3 (derived from T0011 v2 vep_ar1.stan sha f15d0a54; diff in vep_v3_vs_v2.diff).
// Changes vs v2:
//  - x0 free only for nf prespecified regions (SEEG-visible + strongest SC neighbours); the rest are fixed at
//    x0_fixed (healthy) but still simulated
//  - z_init pinned to each region's isolated resting equilibrium z_eq(softmin(x0, x0_cap)) (no free z_init)
//  - per-channel offsets u removed; the likelihood is on k principal components of the baseline-centred feature
//    (Y = (Obs - base) V, V orthonormal [ns x k]); the model mean is projected the same way (GV = V' gain);
//    one constant offset b_j per PC with prior N(0, b_sd^2) is marginalised analytically under the AR(1) model
//  - per-PC noise scale sigma_j (diagonal whitening in the PC basis), shared AR(1) coefficient phi
//  - Laplacian L = SC - diag(rowsum(SC)) precomputed (one mat-vec per Euler step)
functions {
  vector x_rest(vector z, real I1) {
    int n = rows(z);
    vector[n] x;
    real zk = I1 + 1.0 - 32.0 / 27.0;
    for (i in 1:n) {
      if (z[i] <= zk + 1e-3) {
        x[i] = -4.0 / 3.0;
      } else {
        real xi = -3.0;
        for (k in 1:20) xi -= (xi^3 + 2.0 * xi^2 + z[i] - (I1 + 1.0)) / (3.0 * xi^2 + 4.0 * xi);
        x[i] = xi;
      }
    }
    return x;
  }
  vector softmin_cap(vector x0, real cap, real k) {
    int n = rows(x0);
    vector[n] out;
    for (i in 1:n) out[i] = -log_sum_exp(-k * x0[i], -k * cap) / k;
    return out;
  }
  vector z_eq(vector x0s, real I1) {
    int n = rows(x0s);
    vector[n] x = rep_vector(-2.0, n);
    for (k in 1:15) x -= (x .* x .* x + 2.0 * x .* x + 4.0 * x - 4.0 * x0s - (I1 + 1.0)) ./ (3.0 * x .* x + 4.0 * x + 4.0);
    return 4.0 * (x - x0s);
  }
  // returns X - X[:,1]  (nn x nt)
  matrix epi2d(vector x0, vector z_init, real K, real tau0, matrix L, real dt, int nsub, int nt, real I1) {
    int nn = rows(x0);
    matrix[nn, nt] X;
    vector[nn] x1 = x_rest(z_init, I1);
    vector[nn] x = x1;
    vector[nn] z = z_init;
    real a = dt / tau0;
    X[:, 1] = rep_vector(0.0, nn);
    for (t in 2:nt) {
      for (k in 1:nsub) {
        vector[nn] gx = L * x;
        vector[nn] dx = 1.0 - x .* x .* x - 2.0 * x .* x - z + I1;
        vector[nn] dz = 4.0 * (x - x0) - z - K * gx;
        x += dt * dx;
        z += a * dz;
      }
      X[:, t] = x - x1;
    }
    return X;
  }
  // AR(1) Gaussian log likelihood of each column of r (nt x k) with per-column scale sig[j] and a constant
  // column offset b_j ~ N(0, b_sd^2) integrated out analytically
  real ar1_marg_lpdf(matrix r, real phi, vector sig, real b_sd) {
    int nt = rows(r);
    int k = cols(r);
    real s1 = sqrt(1 - square(phi));
    matrix[nt, k] a;
    a[1] = s1 * r[1];
    a[2:nt] = r[2:nt] - phi * r[1:(nt - 1)];
    real cc = square(s1) + (nt - 1) * square(1 - phi);
    row_vector[k] ca = s1 * a[1] + (1 - phi) * (rep_row_vector(1.0, nt - 1) * a[2:nt]);
    row_vector[k] aa = columns_dot_self(a);
    vector[k] inv_s2 = inv_square(sig);
    vector[k] A = cc * inv_s2 + inv_square(b_sd);
    vector[k] B = ca' .* inv_s2;
    vector[k] C = aa' .* inv_s2;
    return -nt * sum(log(sig)) - 0.5 * nt * k * log(2 * pi()) + 0.5 * k * log1m(square(phi))
           - k * log(b_sd) - 0.5 * sum(log(A)) - 0.5 * sum(C - square(B) ./ A);
  }
}
data {
  int<lower=1> nn;
  int<lower=2> nt;
  int<lower=1> k;              // number of PCs
  matrix[nt, k] Y;             // (Obs - base) V
  matrix[k, nn] GV;            // V' gain
  matrix[nn, nn] SC;
  int<lower=1> nf;
  array[nf] int<lower=1, upper=nn> free_idx;
  vector[nn] x0_fixed;         // value used for the non-free regions (entries at free_idx ignored)
  real<lower=0> dt;
  int<lower=1> nsub;
  real I1;
  real x0_mu;
  real<lower=0> x0_sd;
  real x0_cap;
  real<lower=0> cap_k;
  real logK_mu;
  real<lower=0> logK_sd;
  real logtau_mu;
  real<lower=0> logtau_sd;
  real logamp_mu;
  real<lower=0> logamp_sd;
  vector[k] logsig_mu;
  real<lower=0> logsig_sd;
  real<lower=0> b_sd;
}
transformed data {
  matrix[nn, nn] L = add_diag(SC, -SC * rep_vector(1.0, nn));
}
parameters {
  vector[nf] x0_star;
  real logK_star;
  real logtau_star;
  real logamp_star;
  vector[k] logsig_star;
  real<lower=-1, upper=1> phi;
}
transformed parameters {
  vector[nf] x0f = x0_mu + x0_sd * x0_star;
  real K = exp(logK_mu + logK_sd * logK_star);
  real tau0 = exp(logtau_mu + logtau_sd * logtau_star);
  real amp = exp(logamp_mu + logamp_sd * logamp_star);
  vector[k] sigma = exp(logsig_mu + logsig_sd * logsig_star);
}
model {
  vector[nn] x0 = x0_fixed;
  x0[free_idx] = x0f;
  {
    vector[nn] z_init = z_eq(softmin_cap(x0, x0_cap, cap_k), I1);
    matrix[nn, nt] X = epi2d(x0, z_init, K, tau0, L, dt, nsub, nt, I1);
    matrix[nt, k] r = Y - amp * (GV * X)';
    target += ar1_marg_lpdf(r | phi, sigma, b_sd);
  }
  target += std_normal_lpdf(x0_star);
  target += std_normal_lpdf(logK_star);
  target += std_normal_lpdf(logtau_star);
  target += std_normal_lpdf(logamp_star);
  target += std_normal_lpdf(logsig_star);
}
generated quantities {
  vector[nn] x0 = x0_fixed;
  array[nn] int seizing;
  x0[free_idx] = x0f;
  {
    vector[nn] z_init = z_eq(softmin_cap(x0, x0_cap, cap_k), I1);
    matrix[nn, nt] X = epi2d(x0, z_init, K, tau0, L, dt, nsub, nt, I1);
    vector[nn] x1 = x_rest(z_init, I1);
    for (i in 1:nn) seizing[i] = max(X[i] + x1[i]) > -1.0;
  }
}
