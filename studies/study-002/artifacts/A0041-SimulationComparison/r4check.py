import json, numpy as np
A='artifacts/A0038-SimulationBatch/'
p=json.load(open(A+'payload.json'))
out={}
for w in ['post','full']:
    r=json.load(open(A+f'{w}_runs.json')); B={b['sample_index']:b for b in r['baselines']}
    s=json.load(open(A+f'samples_{w}.json'))['samples']
    issues=[]; nonfin={}
    for c in r['candidates']:
        b=B[c['sample_index']]
        for k in ['seeg_noise_seed','coupling_a','n_steps','sample_id']:
            if c[k]!=b[k]: issues.append((c['candidate_id'],c['sample_index'],k))
        if not c['finite']: nonfin[c['candidate_id']]=nonfin.get(c['candidate_id'],0)+1
    seeds_ok=all(B[i]['seeg_noise_seed']==1000+i for i in B)
    nb_nonfin=sum(not b['finite'] for b in B.values())
    steps=set(b['n_steps'] for b in B.values())
    # recompute effects over finite pairs
    eff={}
    by={}
    for c in r['candidates']:
        if c['finite']: by.setdefault(c['candidate_id'],[]).append(c)
    for cid,lst in by.items():
        d=[x['seizures']['n_seizing_regions']-B[x['sample_index']]['seizures']['n_seizing_regions'] for x in lst]
        dd=[x['seizures']['total_seizure_duration_s']-B[x['sample_index']]['seizures']['total_seizure_duration_s'] for x in lst]
        ab=np.mean([x['seizures']['n_seizing_regions']==0 for x in lst])
        eff[cid]=dict(n=len(lst),med=float(np.median(d)),p05=round(float(np.percentile(d,5)),2),p95=round(float(np.percentile(d,95)),2),med_dur=round(float(np.median(dd)),2),abolish=round(float(ab),3))
    base_n=[b['seizures']['n_seizing_regions'] for b in B.values()]
    out[w]=dict(n_baselines=len(B), n_samples_file=len(s), n_candidate_runs=len(r['candidates']), pairing_issues=issues[:5], n_pairing_issues=len(issues),
        seeds_1000_plus_i=seeds_ok, n_steps=sorted(steps), horizon=r['meta']['settings']['horizon_ms'], dt=r['meta']['settings']['dt_ms'],
        spec_sha=r['meta']['spec_sha256'], sim_sha=r['meta']['simulator_sha256'], baseline_nonfinite=nb_nonfin, nonfinite_by_candidate=nonfin,
        baseline_n_seizing=dict(median=float(np.median(base_n)),p05=float(np.percentile(base_n,5)),p95=float(np.percentile(base_n,95))),
        recomputed_effects={k:eff[k] for k in sorted(eff)})
out['payload_results_full_keys']=list(p['results']['full'].keys())
json.dump(out,open('work/T0020/r4check_out.json','w'),indent=1)
print(json.dumps(out,indent=1)[:7000])
