"""T0004: verify CmdStan availability and stanc transpilation of the vep_stim Stan models (no C++ compile)."""
import sys, os, json, subprocess, hashlib, shutil, tempfile
sys.path.insert(0, ".tools")
import stan_env  # noqa: F401  (sets CMDSTAN/PATH for conda-forge toolchain)
import cmdstanpy
out = {"cmdstanpy": cmdstanpy.__version__, "CMDSTAN": os.environ.get("CMDSTAN")}
out["cmdstan_path"] = cmdstanpy.cmdstan_path()
out["cmdstan_version"] = list(cmdstanpy.utils.cmdstan_version())
stanc = os.path.join(out["cmdstan_path"], "bin", "stanc.exe")
out["stanc_version"] = subprocess.run([stanc, "--version"], capture_output=True, text=True).stdout.strip()
pkg = ".venv-model/Lib/site-packages/vep_stim/stan"
tmp = tempfile.mkdtemp()
res = {}
for m in ["vep_mcmc", "vep_mm_mcmc"]:
    src = os.path.join(pkg, m + ".stan")
    sha = hashlib.sha256(open(src, "rb").read()).hexdigest()
    dst = os.path.join(tmp, m + ".hpp")
    r = subprocess.run([stanc, src, "--o", dst], capture_output=True, text=True)
    res[m] = {"stan_sha256": sha, "returncode": r.returncode,
              "stderr_tail": r.stderr.strip()[-600:], "hpp_written": os.path.exists(dst)}
shutil.rmtree(tmp)
out["transpile"] = res
for m in ["vep_mcmc", "vep_mm_mcmc"]:
    with open(os.path.join(pkg, m + ".hpp"), encoding="utf-8", errors="replace") as f:
        out.setdefault("shipped_hpp_header", {})[m] = [next(f).strip(), next(f).strip()]
print(json.dumps(out, indent=1))
