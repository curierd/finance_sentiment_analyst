"""Test if subprocess can find opencli via the wrapper."""
import subprocess
import os

env = os.environ.copy()
env["OPENCLI_WINDOW"] = "background"
r = subprocess.run(["opencli", "--version"], capture_output=True, text=True, env=env)
print(f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
