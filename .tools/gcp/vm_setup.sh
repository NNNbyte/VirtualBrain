#!/usr/bin/env bash
# One-time setup of the GCP compute VM with the same pinned stack as the local .venv-model.
# Idempotent: re-running skips finished steps. Logs to ~/aa/setup.log.
set -euo pipefail
mkdir -p ~/aa && cd ~/aa
exec > >(tee -a ~/aa/setup.log) 2>&1

if [ ! -x ~/aa/bin/micromamba ]; then
  mkdir -p ~/aa/bin
  curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/2.0.5 | tar -xj -C ~/aa bin/micromamba
fi
export MAMBA_ROOT_PREFIX=~/aa/mamba
if [ ! -d ~/aa/mamba/envs/vbt ]; then
  ~/aa/bin/micromamba create -y -n vbt -c conda-forge python=3.11 cmdstan=2.40.0 make cxx-compiler git
fi
PY=~/aa/mamba/envs/vbt/bin/python
$PY -m pip install -q numpy==2.4.6 scipy==1.17.1 pandas==3.1.0 cmdstanpy==1.3.0 tvb-library==2.10.0 \
  numba==0.68.1 nibabel==5.4.2 matplotlib==3.11.2 \
  "vep-stim @ git+https://github.com/HuifangWang/VBT_INS_Stimulation@5367ef4afb976271ecc6297b70a95dd3d944af61"

cat > ~/aa/env.sh <<'EOF'
export MAMBA_ROOT_PREFIX=~/aa/mamba
export PATH=~/aa/mamba/envs/vbt/bin:$PATH
export CMDSTAN=$(ls -d ~/aa/mamba/envs/vbt/bin/cmdstan 2>/dev/null || ls -d ~/aa/mamba/envs/vbt/opt/cmdstan* | head -1)
EOF
source ~/aa/env.sh
$PY - <<'EOF'
import cmdstanpy, os, numpy, tvb
cmdstanpy.set_cmdstan_path(os.environ["CMDSTAN"])
print("cmdstan", cmdstanpy.cmdstan_version(), "numpy", numpy.__version__)
EOF
nproc
echo SETUP_OK
