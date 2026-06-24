#!/usr/bin/env python3
"""
One-shot updater for the India Climate Anomaly Atlas.
=====================================================
Runs the full "reproduce a future update" pipeline from PROCESS.md:

  1. Generate any newly-completed weeks   (weather_anomaly_dashboard_generation.py)
  2. Rebuild the offline standalone HTML   (build_standalone_dashboard.py)
  3. git add -A + commit (only if something changed)
  4. git push origin main
  5. Poll the live GitHub Pages manifest until it serves the new data

Run it whenever you want to refresh the published dashboard:

    python update_atlas.py

Useful flags:
    --no-push      do everything except commit & push (local dry run)
    --no-verify    skip the live-deployment poll at the end
    --no-build     skip rebuilding the 61 MB standalone HTML
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

# --- Configuration (matches PROCESS.md) -------------------------------------
HERE = Path(__file__).resolve().parent

# The `spi` conda env is the only one with the full working stack
# (imdlib / geopandas / exactextract / rioxarray). WEATHER_ANALYSIS is broken
# by the NumPy 2.0 / dask `np.round_` removal — do NOT use it.
SPI_PYTHON = Path(os.environ.get(
    "SPI_PYTHON", r"C:/ProgramData/anaconda3/envs/spi/python.exe"
))

GEN_SCRIPT = HERE / "weather_anomaly_dashboard_generation.py"
BUILD_SCRIPT = HERE / "build_standalone_dashboard.py"

RAIN_MANIFEST = HERE / "data" / "rainfall" / "manifest.json"
LIVE_MANIFEST_URL = (
    "https://santa1309.github.io/india-climate-anomaly-atlas/"
    "data/rainfall/manifest.json"
)

GIT_REMOTE = "origin"
GIT_BRANCH = "main"

# Verification poll settings
VERIFY_TIMEOUT_S = 300   # give Pages up to 5 min to rebuild
VERIFY_INTERVAL_S = 15


def log(msg: str) -> None:
    print(f"[update_atlas] {msg}", flush=True)


def run(cmd, *, env=None, check=True):
    """Run a subprocess, streaming its output, and return the CompletedProcess."""
    printable = " ".join(str(c) for c in cmd)
    log(f"$ {printable}")
    result = subprocess.run(cmd, cwd=HERE, env=env)
    if check and result.returncode != 0:
        sys.exit(f"[update_atlas] FAILED ({result.returncode}): {printable}")
    return result


def utf8_env() -> dict:
    """Env for the data scripts: force UTF-8 so the cp1252 console doesn't
    crash on the `->` (U+2192) character the generator prints."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def latest_local_week() -> str:
    """Read the newest week key from the local rainfall manifest."""
    manifest = json.loads(RAIN_MANIFEST.read_text(encoding="utf-8"))
    return manifest["weeks"][-1]["key"]


def git_has_changes() -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=HERE, capture_output=True, text=True, check=True,
    ).stdout.strip()
    return bool(out)


def verify_live(expected_week: str) -> bool:
    """Poll the live Pages manifest until it reports `expected_week`."""
    deadline = time.time() + VERIFY_TIMEOUT_S
    req = urllib.request.Request(
        LIVE_MANIFEST_URL,
        headers={"Accept-Encoding": "gzip", "Cache-Control": "no-cache"},
    )
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                manifest = json.loads(raw)
            live_week = manifest["weeks"][-1]["key"]
            n_weeks = len(manifest["weeks"])
            if live_week == expected_week:
                log(f"LIVE OK -> {live_week} ({n_weeks} weeks, "
                    f"generated {manifest.get('generated_at')})")
                return True
            log(f"live still old ({live_week}); waiting for {expected_week}...")
        except Exception as exc:  # network / Pages mid-rebuild
            log(f"poll error ({exc}); retrying...")
        time.sleep(VERIFY_INTERVAL_S)
    log(f"TIMEOUT: live manifest never reached {expected_week} "
        f"within {VERIFY_TIMEOUT_S}s (it may still update shortly).")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Update & deploy the Climate Atlas.")
    parser.add_argument("--no-push", action="store_true",
                        help="generate/build locally but do not commit or push")
    parser.add_argument("--no-build", action="store_true",
                        help="skip rebuilding the standalone HTML")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip polling the live deployment")
    args = parser.parse_args()

    # Sanity checks
    if not SPI_PYTHON.exists():
        sys.exit(f"[update_atlas] spi python not found: {SPI_PYTHON}\n"
                 f"Set the SPI_PYTHON env var to the correct interpreter.")
    for script in (GEN_SCRIPT, BUILD_SCRIPT):
        if not script.exists():
            sys.exit(f"[update_atlas] missing script: {script}")

    env = utf8_env()
    before = latest_local_week()
    log(f"latest local week before run: {before}")

    # 1. Generate new weeks (idempotent — only adds weeks where week_end < today)
    log("STEP 1/5  generating new weeks ...")
    run([str(SPI_PYTHON), str(GEN_SCRIPT)], env=env)

    after = latest_local_week()
    log(f"latest local week after run:  {after}")
    if after == before and not git_has_changes():
        log("No new data and no changes — already up to date. Nothing to deploy.")
        return

    # 2. Rebuild the offline standalone dashboard
    if args.no_build:
        log("STEP 2/5  skipped (--no-build)")
    else:
        log("STEP 2/5  rebuilding standalone HTML ...")
        run([str(SPI_PYTHON), str(BUILD_SCRIPT)], env=env)

    if args.no_push:
        log("STEP 3-5 skipped (--no-push). Local files are updated.")
        return

    if not git_has_changes():
        log("Nothing to commit after build — skipping push.")
        return

    # 3. Commit
    commit_msg = f"India Climate Anomaly Atlas: data through {after}"
    log(f"STEP 3/5  committing: {commit_msg!r}")
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", commit_msg])

    # 4. Push
    log("STEP 4/5  pushing to GitHub ...")
    run(["git", "push", GIT_REMOTE, GIT_BRANCH])

    # 5. Verify live deployment
    if args.no_verify:
        log("STEP 5/5  skipped (--no-verify)")
    else:
        log("STEP 5/5  verifying live deployment (Pages rebuild ~1-3 min) ...")
        verify_live(after)

    log(f"Done. Published data through {after} ({date.today().isoformat()}).")


if __name__ == "__main__":
    main()
