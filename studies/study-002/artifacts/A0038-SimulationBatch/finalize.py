"""Build the SimulationBatch payload from batch_post / batch_full outputs + qualitative check vs the P2 recording."""
import json, os, sys
import numpy as np
from scipy.signal import resample_poly, butter, filtfilt

W = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(W, *[os.pardir] * 4))
obs = np.load(os.path.join(ROOT, "data", "wang-5367ef4", "data", "dataSim", "Patient2", "P2_SEEG_ts_fit.npz"))
ch = [str(c) for c in obs["ch_names"]]
lut = [l.split()[1] for l in open(os.path.join(ROOT, "data", "wang-5367ef4", "data", "VepMrtrixLut.txt"))
       if l.strip() and l.split()[0].isdigit() and 1 <= int(l.split()[0]) <= 162]


def act(x, t, a, b, ref=(0.1, 0.5)):
    """per-channel activity: SD of 2-Hz high-passed signal in [a,b] s divided by SD in the ref window."""
    bb, aa = butter(3, 2 * 2.0 / 50.0, "highpass")
    y = filtfilt(bb, aa, x, axis=0)
    s1 = y[(t >= a) & (t < b)].std(0)
    s0 = y[(t >= ref[0]) & (t < ref[1])].std(0) + 1e-12
    return s1 / s0


# observed P2 (125 Hz) -> 50 Hz
xo = resample_poly(obs["seeg"].T, 2, 5, axis=0)
to = np.arange(xo.shape[0]) / 50.0 + 0.008
obs_post = act(xo, to, 3.6, 7.4)
top_obs = list(np.argsort(obs_post)[::-1][:10])

def recompute(R, C):
    """Effects over finite paired runs only; arms with any non-finite run are flagged; ties made explicit."""
    B = {b["sample_index"]: b for b in R["baselines"] if b["finite"]}
    q = lambda v: dict(median=float(np.median(v)), p05=float(np.percentile(v, 5)), p95=float(np.percentile(v, 95)))
    eff, failed, per = {}, {}, {}
    for c in C["candidates"]:
        rr = [r for r in R["candidates"] if r["candidate_id"] == c["id"]]
        bad = [r["sample_id"] for r in rr if not r["finite"]]
        if bad:
            failed[c["id"]] = dict(n_nonfinite=len(bad), n_runs=len(rr),
                                   status="numerical_failure (NaN/Inf during integration at dt 0.05 ms); arm excluded from effects and ranking")
            continue
        rr = [r for r in rr if r["sample_index"] in B]
        dn = [r["seizures"]["n_seizing_regions"] - B[r["sample_index"]]["seizures"]["n_seizing_regions"] for r in rr]
        dd = [r["seizures"]["total_seizure_duration_s"] - B[r["sample_index"]]["seizures"]["total_seizure_duration_s"] for r in rr]
        dc = [r["n_seeg_channels_exceeding"] - B[r["sample_index"]]["n_seeg_channels_exceeding"] for r in rr]
        do = [r["seizures"]["first_onset_ms"] - B[r["sample_index"]]["seizures"]["first_onset_ms"] for r in rr
              if r["seizures"]["first_onset_ms"] is not None and B[r["sample_index"]]["seizures"]["first_onset_ms"] is not None]
        ab = [r["seizures"]["n_seizing_regions"] == 0 for r in rr]
        abb = [r["seizures"]["n_seizing_regions"] == 0 for r in rr if B[r["sample_index"]]["seizures"]["n_seizing_regions"] > 0]
        eff[c["id"]] = dict(family=c["family"], n_samples=len(rr), d_n_seizing_regions=q(dn), d_total_seizure_duration_s=q(dd),
                            d_n_seeg_channels_exceeding=q(dc), d_first_onset_ms=q(do) if do else None,
                            frac_abolish_all=float(np.mean(ab)), frac_abolish_all_given_baseline_seizes=float(np.mean(abb)) if abb else None)
        per[c["id"]] = {r["sample_index"]: (dn[k], dd[k]) for k, r in enumerate(rr)}
    key = lambda k: (eff[k]["d_n_seizing_regions"]["median"], eff[k]["d_total_seizure_duration_s"]["median"])
    rank = sorted(eff, key=key)
    tied_first = [k for k in rank if key(k) == key(rank[0])]
    first = {k: 0.0 for k in eff}
    for i in B:
        vals = {k: per[k][i] for k in eff if i in per[k]}
        best = min(vals.values())
        for k, v in vals.items():
            if v == best:
                first[k] += 1
    base = list(B.values())
    return dict(baseline=dict(n_seizing_regions=q([b["seizures"]["n_seizing_regions"] for b in base]),
                              total_seizure_duration_s=q([b["seizures"]["total_seizure_duration_s"] for b in base]),
                              n_seeg_channels_exceeding=q([b["n_seeg_channels_exceeding"] for b in base])),
                effects=eff, numerically_failed_arms=failed, ranking=rank, tied_first=tied_first,
                rank_first_fraction={k: v / len(B) for k, v in first.items()},
                rank_note="rank-first counts every candidate tied for the best paired value in a sample (ties are explicit); "
                          "if tied_first contains many candidates the ranking is uninformative")


windows = [w for w in ("post", "full") if os.path.exists(os.path.join(W, f"batch_{w}", "summary.json"))]
payload = dict(label="PRELIMINARY - model not yet qualified (A0018 MAP ensemble; amendment A0015). Simulated results on a virtual patient; not clinical recommendations.",
               model_bundle_id="A0018-ModelBundle", scenario_set="A0034-InterventionScenarioSet", request="A0035-SimulationRequest",
               windows_run=windows, windows_not_run=[w for w in ("post", "full") if w not in windows])
per = {}
for w in windows:
    S = json.load(open(os.path.join(W, f"batch_{w}", "summary.json")))
    R = json.load(open(os.path.join(W, f"batch_{w}", "runs.json")))
    C = json.load(open(os.path.join(W, f"batch_{w}", "candidates.json")))
    m = S["meta"]
    S["summary"] = recompute(R, C)
    sig = np.load(os.path.join(W, f"batch_{w}", "signals_median_sample.npz"))
    t = sig["BASELINE__t_ms"] / 1000.0
    qual = {}
    for arm in ("BASELINE", "STIM-PT__amp1", "STIM-PT__amp4"):
        if f"{arm}__seeg" in sig.files:
            a = act(sig[f"{arm}__seeg"].astype(float), t, 3.6, min(7.4, t[-1]))
            top = list(np.argsort(a)[::-1][:10])
            qual[arm] = dict(top10_channels=[ch[i] for i in top], overlap_with_observed_top10=len(set(top) & set(top_obs)),
                             max_activity_ratio=float(a.max()))
    med = [b for b in R["baselines"] if b["sample_index"] == m["median_sample_index"]][0]
    per[w] = dict(
        horizon_ms=m["settings"]["horizon_ms"], n_samples=m["n_samples"], n_candidates=m["n_candidates"],
        ez_estimate=C["ez_estimate"], derived=dict(C["derived"], top1_name=lut[C["derived"]["top1"]],
                                                   pz_names=[lut[i] for i in C["derived"]["pz"]],
                                                   stim1_contact_name=ch[C["derived"]["stim1_contact"]],
                                                   stim2_contact_names=[ch[i] for i in C["derived"]["stim2_contacts"]]),
        baseline_summary=S["summary"]["baseline"], effects=S["summary"]["effects"], ranking=S["summary"]["ranking"],
        numerically_failed_arms=S["summary"]["numerically_failed_arms"], tied_first=S["summary"]["tied_first"], rank_note=S["summary"]["rank_note"],
        rank_first_fraction=S["summary"]["rank_first_fraction"],
        median_sample=dict(id=m["median_sample_id"], baseline_seizing_regions=[lut[i] for i in med["seizures"]["seizing_regions"]],
                           baseline_first_onset_ms=med["seizures"]["first_onset_ms"]),
        induced_response_STIM_PT={c["candidate_id"]: c["induced_response"]["n_regions_with_onset_in_window"]
                                  for c in R["candidates"] if c["sample_index"] == m["median_sample_index"] and "induced_response" in c},
        qualitative_check_vs_recording=dict(
            method="per-channel SD of 2-Hz high-passed SEEG (50 Hz) in 3.6-7.4 s relative to 0.1-0.5 s; top-10 channels compared with the observed P2 recording (which contains the 50 Hz train 0.5-3.5 s). Qualitative only; nothing tuned to the recording.",
            observed_top10=[ch[i] for i in top_obs], simulated=qual),
        meta=m)
payload.update(
    model_samples={w: f"A0018 window '{w}': {per[w]['n_samples']} MAP optima (studies/study-002/work/T0017/samples_{w}.json)" for w in windows},
    candidate_ids={w: ["BASELINE"] + [c["id"] for c in json.load(open(os.path.join(W, f"batch_{w}", "candidates.json")))["candidates"]]
                   for w in windows},
    seeds={"dynamics": "deterministic (HeunDeterministicAdapted, no noise): no seed", "seeg_observation_noise": "N(0, 0.02) added to SEEG for the log-power metric only; seed 1000 + sample_index, shared by each sample's baseline and candidates"},
    initial_states={"rule": "uncoupled, unstimulated SpatEpiStim equilibrium at x0 = -3.0 (m = 0), identical for every node, sample and arm",
                    "values_u1_u2_s_q1_q2_g_m": per[windows[0]]["meta"]["initial_state"] if windows else None},
    solver_settings={w: per[w]["meta"]["settings"] for w in windows},
    paired_baselines="every candidate run is paired with the no-intervention run of the same sample (same x0, K, initial state, horizon, dt, noise seed); effects = candidate - baseline per sample",
    output_refs={w: [f"studies/study-002/work/T0017/batch_{w}/{f}" for f in ("summary.json", "runs.json", "candidates.json", "signals_median_sample.npz")] for w in windows},
    numerical_checks={w: per[w]["meta"]["numerical_checks"] for w in windows},
    resource_use={w: dict(wall_total_s=per[w]["meta"]["wall_total_s"], per_sim_wall_s=per[w]["meta"]["per_sim_wall_s"],
                          workers=per[w]["meta"]["jobs"], machine=f"local, {per[w]['meta']['cpu_count']} logical cores") for w in windows},
    results=per,
    definitions=dict(seizure="region seizes when u1 > -1 (package Heaviside coupling threshold) recurs within 250 ms windows continuously for >= 1 s (TemporalAverage 4 ms)",
                     seeg_channel_metric="log-power (10 Hz HPF, 0.4 s moving mean square, 1 Hz LPF) > paired-baseline 250-750 ms mean + 3*max(SD, 0.1), sustained >= 1 s, after 750 ms",
                     ranking="median paired reduction in seizing regions, ties by total seizure duration"),
    limitations=["Preliminary MAP ensemble, model not qualified; predictions must not be frozen on this batch.",
                 "Generator/inverter mismatch: x0 from the 2D fit inserted into the 6D+m SpatEpiStim; coupling mapping a = 0.1*K is an R4 convention.",
                 "Stimulation amplitudes are model units (1 unit = Istim 0.01 at the max-gain region); raw gain weights were numerically infeasible.",
                 "Signals saved are 50 Hz block averages (the 50 Hz pulse artefact averages out)."])
json.dump(payload, open(os.path.join(W, "simulation_batch.json"), "w"), indent=1, default=float)
for w in windows:
    print(w, "baseline", per[w]["baseline_summary"]["n_seizing_regions"], "rank", per[w]["ranking"][:5], "tied_first", len(per[w]["tied_first"]), "failed", list(per[w]["numerically_failed_arms"]))
    print("  qual", per[w]["qualitative_check_vs_recording"]["simulated"])
print("observed top10", [ch[i] for i in top_obs])
