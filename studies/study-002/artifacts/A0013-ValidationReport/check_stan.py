import sys, os, subprocess, json, tempfile, shutil
sys.path.insert(0, ".tools"); import stan_env, cmdstanpy
out = {"cmdstan_path": cmdstanpy.cmdstan_path(), "cmdstan_version": cmdstanpy.utils.cmdstan_version()}
stanc = os.path.join(cmdstanpy.cmdstan_path(), "bin", "stanc" + (".exe" if os.name == "nt" else ""))
P = ".venv-model/Lib/site-packages/vep_stim/stan"
tmp = tempfile.mkdtemp()
for m in ["vep_mcmc", "vep_mm_mcmc"]:
    r = subprocess.run([stanc, os.path.join(P, m + ".stan"), "--o", os.path.join(tmp, m + ".hpp")], capture_output=True, text=True)
    out[m] = {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
v = subprocess.run([stanc, "--version"], capture_output=True, text=True)
out["stanc_version"] = v.stdout.strip()
shutil.rmtree(tmp)
print(json.dumps(out, indent=1))
