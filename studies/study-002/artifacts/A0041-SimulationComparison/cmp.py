import json
o=json.load(open('artifacts/A0038-SimulationBatch/full_runs.json')); n=json.load(open('work/T0020/rerun/full_s0/runs.json'))
O={(r['candidate_id'],r['sample_id']):r for r in o['baselines']+o['candidates']}
keys=['finite','n_steps','coupling_a','max_abs_state','m_max','seeg_noise_seed','n_seeg_channels_exceeding']
rows=[]
for r in n['baselines']+n['candidates']:
    a=O[(r['candidate_id'],r['sample_id'])]
    d=dict(candidate=r['candidate_id'],sample=r['sample_id'])
    d['seizing_regions_equal']=a['seizures']['seizing_regions']==r['seizures']['seizing_regions']
    d['n_seizing']=[a['seizures']['n_seizing_regions'],r['seizures']['n_seizing_regions']]
    d['total_dur_s']=[a['seizures']['total_seizure_duration_s'],r['seizures']['total_seizure_duration_s']]
    d['onsets_equal']=a['seizures']['onset_ms_by_region']==r['seizures']['onset_ms_by_region']
    d['max_abs_state_absdiff']=abs(a['max_abs_state']-r['max_abs_state'])
    d['other_fields_equal']=all(a.get(k)==r.get(k) for k in keys if k!='max_abs_state')
    d['seeg_channels_equal']=a['seeg_channels_exceeding']==r['seeg_channels_exceeding']
    d['wall_s']=round(r['wall_s'],1)
    rows.append(d)
res=dict(meta=dict(sim_sha=n['meta']['simulator_sha256'],spec_sha=n['meta']['spec_sha256'],npz_sha=n['meta']['npz_sha256'],horizon=n['meta']['settings']['horizon_ms'],
   settings_equal=n['meta']['settings']==o['meta']['settings']), rows=rows,
   all_exact=all(x['seizing_regions_equal'] and x['onsets_equal'] and x['other_fields_equal'] and x['seeg_channels_equal'] and x['n_seizing'][0]==x['n_seizing'][1] and x['total_dur_s'][0]==x['total_dur_s'][1] and x['max_abs_state_absdiff']==0 for x in rows))
json.dump(res,open('work/T0020/rerun_comparison.json','w'),indent=1); print(json.dumps(res,indent=1))
