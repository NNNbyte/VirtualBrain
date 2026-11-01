"""Run study compute jobs on a GCP VM (set GCP_PROJECT / GCP_ZONE / GCP_VM) and bring results back.

    python .tools/gcp/gcp_run.py push  <local_path> <remote_rel>      # copy a file/dir to ~/aa/jobs/<remote_rel>
    python .tools/gcp/gcp_run.py run   <job_name> <remote_rel_dir> -- <command...>
                                                                       # start in background on the VM (nohup), cwd = that dir
    python .tools/gcp/gcp_run.py status [<job_name>]                   # running/finished + last log lines
    python .tools/gcp/gcp_run.py pull  <remote_rel> <local_path>       # copy results back
    python .tools/gcp/gcp_run.py ssh   -- <command...>                 # one-off command, prints output

Remote commands run with the pinned env (`source ~/aa/env.sh`): python 3.11, CmdStan 2.40 ($CMDSTAN),
cmdstanpy 1.3.0, tvb-library 2.10.0, vep-stim @ 5367ef4. Log every push/run/pull in your task log.

Guard: refuses to push anything under studies/*/vault or any path whose name mentions ground truth,
and anything outside this project. Only public Wang data, code and synthetic data may leave the machine.
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = os.environ.get("GCP_PROJECT", "")  # set GCP_PROJECT, GCP_ZONE, GCP_VM for your own VM
ZONE = os.environ.get("GCP_ZONE", "us-central1-a")
VM = os.environ.get("GCP_VM", "")
SDK = Path(os.environ.get("GCLOUD_SDK", str(Path.home() / "AppData" / "Local" / "Google" / "Cloud SDK" / "google-cloud-sdk")))
# Call gcloud's Python entry point directly: going through gcloud.cmd lets cmd.exe interpret
# '>', '&' and '|' inside the remote command.
GCLOUD = [str(SDK / "platform" / "bundledpython" / "python.exe"), str(SDK / "lib" / "gcloud.py")]
BASE = ["--project", PROJECT, "--zone", ZONE, "--quiet"]


def gcloud(*args, capture=False):
    cmd = [*GCLOUD, "compute", *args, *BASE]
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        sys.exit(f"gcloud failed ({r.returncode}): {' '.join(args[:2])}\n{(r.stderr or '')[-2000:]}")
    return r.stdout if capture else ""


def ssh(command, capture=False):
    return gcloud("ssh", VM, "--command", f"bash -lc {shlex.quote(command)}", capture=capture)


def guard(p: Path):
    rp = p.resolve()
    if ROOT not in rp.parents and rp != ROOT:
        sys.exit(f"refused: {p} is outside the project")
    low = str(rp).replace("\\", "/").lower()
    if "/vault" in low or "ground_truth" in low or "truth" in rp.name.lower():
        sys.exit(f"refused: {p} may contain sealed outcomes or ground truth")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    op, rest = argv[0], argv[1:]
    if op == "push":
        local, remote = Path(rest[0]), rest[1]
        guard(local)
        ssh(f"mkdir -p ~/aa/jobs/{shlex.quote(str(Path(remote).parent.as_posix()))}")
        gcloud("scp", "--recurse", str(local), f"{VM}:aa/jobs/{remote}")
        print(f"pushed {local} -> ~/aa/jobs/{remote}")
    elif op == "run":
        name, rdir = rest[0], rest[1]
        cmd = " ".join(rest[rest.index("--") + 1:])
        script = (f"{{ [ -f ~/aa/env.sh ] && source ~/aa/env.sh; }}; mkdir -p ~/aa/logs && cd ~/aa/jobs/{shlex.quote(rdir)} && "
                  f"nohup bash -c {shlex.quote(cmd + '; echo EXIT=$? >> ~/aa/logs/' + name + '.log')} "
                  f"> ~/aa/logs/{name}.log 2>&1 & echo $! > ~/aa/logs/{name}.pid; echo started {name} pid $(cat ~/aa/logs/{name}.pid)")
        print(ssh(script, capture=True).strip())
    elif op == "status":
        pat = rest[0] if rest else "*"
        print(ssh(f"cd ~/aa/logs 2>/dev/null || exit 0; for p in {pat}.pid; do [ -f \"$p\" ] || continue; n=${{p%.pid}}; "
                  f"if kill -0 $(cat $p) 2>/dev/null; then s=running; else s=finished; fi; echo \"== $n: $s\"; tail -n 5 $n.log; done; "
                  f"echo; uptime", capture=True))
    elif op == "pull":
        remote, local = rest[0], Path(rest[1])
        guard(local)
        local.parent.mkdir(parents=True, exist_ok=True)
        gcloud("scp", "--recurse", f"{VM}:aa/jobs/{remote}", str(local))
        print(f"pulled ~/aa/jobs/{remote} -> {local}")
    elif op == "ssh":
        print(ssh(" ".join(rest[rest.index("--") + 1:]), capture=True))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
