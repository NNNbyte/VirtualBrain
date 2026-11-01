"""Study-002 SEEG log-power feature (patched re-implementation of vep_stim compute_slp_sim).

Changes vs vep_prepare_sim.compute_slp_sim / seeg_log_power (vep-stim 0.1.0a1 @5367ef4), see A0006:
  1. sampling rate read from the file's time_steps (ms) - never assumed (A0006 defect 'fs hard-coded 250 Hz')
  2. log-power moving window is CENTRED and length is in seconds (1.0 s), edges use reflect padding
     instead of zero padding at the end (A0006 defect 'end zero-padding biases log power by up to log(100)')
  3. the two 2-SD outlier clamps are removed: they replace every sample > 2 SD (i.e. the seizure itself)
     by the channel mean, in place on the caller's array (A0006 'other observations')
  4. the output is decimated (after the 1 Hz low-pass) to `target_hz` to reduce the serial correlation the
     likelihood has to absorb; residual AR(1) is still modelled in the Stan likelihood
  5. the feature is returned on the log scale and is NOT logged again in the Stan model (vep_mcmc.stan:27
     logged it a second time)
High-pass 10 Hz (Butterworth order 3, filtfilt) and the 1 Hz low-pass (order 3, filtfilt) are kept as in the
package. Per-channel baseline offset and a global scale are reported (used only for data-centred priors).
"""
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d


def sfreq_from_time_steps(time_steps_ms):
    step = np.diff(np.asarray(time_steps_ms, float))
    if not np.allclose(step, step[0], rtol=1e-6):
        raise ValueError("non-uniform time steps")
    return 1000.0 / step[0]


def bfilt(x, fs, fc, mode, order=3):
    b, a = signal.butter(order, 2.0 * fc / fs, mode)
    return signal.filtfilt(b, a, x, axis=0)


def log_power(x, fs, win_s=1.0):
    w = int(round(win_s * fs))
    return np.log(uniform_filter1d(x ** 2, size=w, axis=0, mode="reflect"))


def compute_feature(seeg, time_steps_ms, hpf=10.0, lpf=1.0, win_s=1.0, target_hz=4.0):
    """seeg [ns x nt] raw-like signal -> (feature [nt_dec x ns], t_dec seconds, fs)."""
    fs = sfreq_from_time_steps(time_steps_ms)
    x = np.array(seeg, float).T.copy()                   # [nt x ns], never modify the caller's array
    x = bfilt(x, fs, hpf, "highpass")
    lp = log_power(x, fs, win_s)
    lp = bfilt(lp, fs, lpf, "lowpass")
    q = int(round(fs / target_hz))
    t = np.asarray(time_steps_ms, float) / 1000.0
    return lp[::q], t[::q], fs
