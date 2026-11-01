// study-002 T0011 patched copy of vep_stim/stan/vep_mcmc.stan (vep-stim 0.1.0a1 @5367ef4).
// Changes (see vep_ar1.diff and README in the ModelBundle):
//  - Obs is the log-power feature and is NOT logged again (vep_mcmc.stan:27 double log)
//  - likelihood covers every (time, channel) element; the column-major `10*ns` skip that dropped whole
//    channels is removed (vep_mcmc.stan:119)
//  - AR(1) residual likelihood (phi estimated; ar1=0 gives the iid model) instead of iid Normal
//  - each region starts ON its resting branch for its z_init (x_init solved, was fixed -1.98), and the
//    offsets are data-centred: mu = amp * gain * (x - x_init) + u, u ~ N(u_mu (channel baseline), u_sd)
//  - log-normal amp prior centred on the data range / (gain, x excursion); sigma prior centred on data
//  - coupling unchanged (diffusive, vep_mcmc.stan:104-107) but vectorised; tau0 (time scale) and K estimated
//  - v2: z_init centred on each region's isolated equilibrium z_eq(softmin(x0, x0_cap)) (sd z0_sd), so a
//    healthy region starts at rest and onset time cannot be traded freely against x0
//  - x0 prior N(x0_mu, x0_sd) with identity in place of the undocumented `eig` matrix
//  - generated quantities use the SAME likelihood (log_lik per time point) - fixes log_lik_sum scale defect
//  - unused transformed data (wt, wtm) removed
functions {
  // x on the left (resting) branch of the x-nullcline for a given z: root of f(x) = x^3 + 2x^2 + z - (I1 + 1)
  // with x < -4/3. f is increasing and concave there, so Newton from x = -3 increases monotonically to the
  // root without overshoot (20 steps). Below the knee value z_k = I1 + 1 - 32/27 there is no resting root
  // and the region starts at the knee x = -4/3 (it seizes immediately).
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
  // isolated-node equilibrium slow variable for x0s <= critical: x solves x^3 + 2x^2 + 4x - 4 x0s - (I1 + 1) = 0
  // (derivative 3x^2 + 4x + 4 > 0, unique root; 15 Newton steps from x = -2), z_eq = 4 (x - x0s)
  // softmin(x0, cap) = -(1/k) log(exp(-k x0) + exp(-k cap)); returned negated
  vector log_sum_exp_vec(vector x0, real cap, real k) {
    int n = rows(x0);
    vector[n] out;
    for (i in 1:n) out[i] = log_sum_exp(-k * x0[i], -k * cap) / k;
    return out;
  }
  vector z_eq(vector x0s, real I1) {
    int n = rows(x0s);
    vector[n] x = rep_vector(-2.0, n);
    for (k in 1:15) x -= (x .* x .* x + 2.0 * x .* x + 4.0 * x - 4.0 * x0s - (I1 + 1.0)) ./ (3.0 * x .* x + 4.0 * x + 4.0);
    return 4.0 * (x - x0s);
  }
  matrix epi2d(vector x0, vector z_init, real K, real tau0, matrix SC, vector SCrow,
               real dt, int nsub, int nt, real I1) {
    int nn = rows(x0);
    matrix[nn, nt] X;
    vector[nn] x = x_rest(z_init, I1);
    vector[nn] z = z_init;
    X[:, 1] = x;
    for (t in 2:nt) {
      for (k in 1:nsub) {
        vector[nn] gx = SC * x - SCrow .* x;
        vector[nn] dx = 1.0 - x .* x .* x - 2.0 * x .* x - z + I1;
        vector[nn] dz = (4.0 * (x - x0) - z - K * gx) / tau0;
        x += dt * dx;
        z += dt * dz;
      }
      X[:, t] = x;
    }
    return X;
  }
}
data {
  int<lower=1> nn;
  int<lower=2> nt;
  int<lower=1> ns;
  matrix[nt, ns] Obs;
  matrix[nn, nn] SC;
  matrix[ns, nn] gain;
  real<lower=0> dt;
  int<lower=1> nsub;
  real I1;
  real x0_mu;
  real<lower=0> x0_sd;
  real x0_cap;          // soft cap (just below the bifurcation) used to centre z_init
  real<lower=0> cap_k;  // softmin sharpness
  real<lower=0> z0_sd;
  real logK_mu;
  real<lower=0> logK_sd;
  real logtau_mu;
  real<lower=0> logtau_sd;
  real logamp_mu;
  real<lower=0> logamp_sd;
  vector[ns] u_mu;
  real<lower=0> u_sd;
  real logsig_mu;
  real<lower=0> logsig_sd;
  int<lower=0, upper=1> ar1;
}
transformed data {
  vector[nn] SCrow = SC * rep_vector(1.0, nn);
}
parameters {
  vector[nn] x0_star;
  vector[nn] z_init_star;
  real logK_star;
  real logtau_star;
  real logamp_star;
  vector[ns] u_star;
  real logsig_star;
  real<lower=-1, upper=1> phi_raw;
}
transformed parameters {
  vector[nn] x0 = x0_mu + x0_sd * x0_star;
  vector[nn] x0s = -log_sum_exp_vec(x0, x0_cap, cap_k);
  vector[nn] z_init = z_eq(x0s, I1) + z0_sd * z_init_star;
  real K = exp(logK_mu + logK_sd * logK_star);
  real tau0 = exp(logtau_mu + logtau_sd * logtau_star);
  real amp = exp(logamp_mu + logamp_sd * logamp_star);
  vector[ns] u = u_mu + u_sd * u_star;
  real sigma = exp(logsig_mu + logsig_sd * logsig_star);
  real phi = ar1 == 1 ? phi_raw : 0.0;
}
model {
  matrix[nn, nt] x = epi2d(x0, z_init, K, tau0, SC, SCrow, dt, nsub, nt, I1);
  matrix[nt, ns] r = Obs - (amp * (gain * (x - rep_matrix(x[:, 1], nt))))' - rep_matrix(u', nt);
  target += std_normal_lpdf(x0_star);
  target += std_normal_lpdf(z_init_star);
  target += std_normal_lpdf(logK_star);
  target += std_normal_lpdf(logtau_star);
  target += std_normal_lpdf(logamp_star);
  target += std_normal_lpdf(u_star);
  target += std_normal_lpdf(logsig_star);
  // phi_raw: uniform on (-1, 1)
  target += normal_lpdf(r[1] | 0, sigma / sqrt(1 - square(phi)));
  target += normal_lpdf(to_vector(r[2:nt]) | to_vector(phi * r[1:(nt - 1)]), sigma);
}
generated quantities {
  vector[nt] log_lik;
  array[nn] int seizing;
  real resid_lag1_ac;
  {
    matrix[nn, nt] x = epi2d(x0, z_init, K, tau0, SC, SCrow, dt, nsub, nt, I1);
    matrix[nt, ns] r = Obs - (amp * (gain * (x - rep_matrix(x[:, 1], nt))))' - rep_matrix(u', nt);
    matrix[nt, ns] e;
    e[1] = r[1] * sqrt(1 - square(phi));
    for (t in 2:nt) e[t] = r[t] - phi * r[t - 1];
    for (t in 1:nt) log_lik[t] = normal_lpdf(e[t] | 0, sigma);   // innovations; Jacobian of e(r) is 1 for t>1
    log_lik[1] += 0.5 * ns * log1m(square(phi));
    for (i in 1:nn) seizing[i] = max(x[i]) > -1.0;
    {
      // lag-1 autocorrelation of the whitened innovations, pooled over channels
      real num = 0; real den = 0;
      for (t in 2:nt) { num += dot_product(e[t], e[t - 1]); }
      for (t in 1:nt) { den += dot_self(e[t]); }
      resid_lag1_ac = num / den;
    }
  }
}
