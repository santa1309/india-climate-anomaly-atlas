#!/usr/bin/env python3
r"""
One-shot updater for "Climate Change at a Glance" (SatSure design build).
========================================================================
Run this (normally via update_satsure.bat) to refresh the published dashboard:

    python publish_satsure.py

What it does:

  1. Generate any newly-completed weeks   (weather_anomaly_dashboard_generation.py)
  2. Mirror data/ + the dashboard files into the deploy repo
     (../../climate_change_at_glance)
  3. git add -A + commit  (only if something changed)
  4. git push origin main
  5. Poll the live GitHub Pages manifest until it serves the new data

The data pipeline writes into the shared ../data folder (the same one the
original atlas uses); this script copies that into the separate deploy repo so
the new site has its own self-contained copy.

Useful flags:
    --build        also rebuild the local offline dashboard_standalone.html
    --no-push      generate + sync locally but do not commit or push (dry run)
    --no-verify    skip polling the live deployment
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

# --- Configuration ----------------------------------------------------------
HERE = Path(__file__).resolve().parent                 # .../weather_dashboard/satsure_dashboard
WD = HERE.parent                                       # .../weather_dashboard
DEPLOY = Path(os.environ.get(
    "DEPLOY_DIR", WD.parent / "climate_change_at_glance"))  # sibling deploy repo
SOURCE = WD                                            # pipeline/code repo (git)

# The `spi` conda env is the only one with the full working stack
# (imdlib / geopandas / exactextract / rioxarray).
SPI_PYTHON = Path(os.environ.get(
    "SPI_PYTHON", r"C:/ProgramData/anaconda3/envs/spi/python.exe"))

GEN_SCRIPT   = WD / "weather_anomaly_dashboard_generation.py"
BUILD_SCRIPT = HERE / "build_standalone.py"

DATA_SRC      = WD / "data"
RAIN_MANIFEST = DATA_SRC / "rainfall" / "manifest.json"

# Files that make up the served dashboard (copied into DEPLOY/satsure_dashboard)
DASH_FILES = ["index.html", "style.css", "app.js", "Satsure_Transparent_Bg_logo.png"]

LIVE_MANIFEST_URL = (
    "https://santa1309.github.io/climate_change_at_glance/"
    "data/rainfall/manifest.json"
)

GIT_NAME  = "santa1309"
GIT_EMAIL = "santoshgeo22@gmail.com"
GIT_REMOTE = "origin"
GIT_BRANCH = "main"
DEPLOY_URL = "https://github.com/santa1309/climate_change_at_glance.git"

VERIFY_TIMEOUT_S = 300
VERIFY_INTERVAL_S = 15


def log(msg: str) -> None:
    print(f"[publish_satsure] {msg}", flush=True)


def run(cmd, *, cwd=None, env=None, check=True):
    printable = " ".join(str(c) for c in cmd)
    log(f"$ {printable}")
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if check and result.returncode != 0:
        sys.exit(f"[publish_satsure] FAILED ({result.returncode}): {printable}")
    return result


def utf8_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def latest_local_week() -> str:
    manifest = json.loads(RAIN_MANIFEST.read_text(encoding="utf-8"))
    return manifest["weeks"][-1]["key"]


def git(args, *, check=True):
    return run(["git", "-C", str(DEPLOY),
                "-c", f"user.name={GIT_NAME}", "-c", f"user.email={GIT_EMAIL}",
                *args], check=check)


def git_src(args, *, check=True):
    return run(["git", "-C", str(SOURCE),
                "-c", f"user.name={GIT_NAME}", "-c", f"user.email={GIT_EMAIL}",
                *args], check=check)


def publish_source(after: str) -> None:
    """Commit + push the SOURCE code repo (generator, dashboard source, batch,
    and its own data copy) so all code changes reach GitHub, not just the Pages
    mirror. No-op if SOURCE isn't a git repo or has nothing to commit."""
    is_repo = subprocess.run(
        ["git", "-C", str(SOURCE), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True).returncode == 0
    if not is_repo:
        log("source repo: not a git work tree -- skipping code push")
        return
    changed = subprocess.run(
        ["git", "-C", str(SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True).stdout.strip()
    if not changed:
        log("source repo: no code/data changes to push")
        return
    log("pushing SOURCE code repo to GitHub ...")
    git_src(["add", "-A"])
    git_src(["commit", "-m", f"Pipeline + dashboard update: data through {after}"])
    push = git_src(["push", "origin", GIT_BRANCH], check=False)
    if push.returncode != 0:
        log("source push rejected -- pull --rebase and retry ...")
        git_src(["pull", "--rebase", "origin", GIT_BRANCH])
        git_src(["push", "origin", GIT_BRANCH])


def deploy_git_ok() -> bool:
    """True if the deploy repo's git store is readable (not NTFS-corrupted)."""
    return subprocess.run(
        ["git", "-C", str(DEPLOY), "status", "--porcelain"],
        capture_output=True, text=True).returncode == 0


def ensure_deploy_repo() -> None:
    """Clone the deploy repo if missing, or re-clone it if its git store got
    corrupted (the '.git/objects: Function not implemented' failure). The data
    is only a mirror of ../data, so a fresh clone loses nothing."""
    if not (DEPLOY / ".git").exists():
        log(f"deploy repo missing -- cloning fresh into {DEPLOY} ...")
        run(["git", "clone", DEPLOY_URL, str(DEPLOY)])
        return
    if deploy_git_ok():
        return
    aside = DEPLOY.with_name(f"{DEPLOY.name}_CORRUPT_{int(time.time())}")
    log(f"deploy repo git is unreadable (corrupt) -- moving aside to {aside.name} "
        f"and re-cloning ...")
    DEPLOY.rename(aside)
    run(["git", "clone", DEPLOY_URL, str(DEPLOY)])
    log(f"re-cloned OK. Delete the old copy when convenient: {aside}")


def git_has_changes() -> bool:
    out = subprocess.run(["git", "-C", str(DEPLOY), "status", "--porcelain"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return bool(out)


def sync_to_deploy() -> None:
    """Mirror data/ and copy the dashboard files into the deploy repo."""
    log("syncing data/ -> deploy (robocopy /MIR) ...")
    # robocopy returns 0-7 on success (>=8 is a real error).
    rc = subprocess.run(
        ["robocopy", str(DATA_SRC), str(DEPLOY / "data"),
         # Skip the legacy weekly series: the SatSure site uses trends.json.
         # (The original atlas repo still needs timeseries.json, so the
         #  generator keeps writing it locally — we just don't publish it here.)
         "/MIR", "/XF", "timeseries.json",
         "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
    ).returncode
    if rc >= 8:
        sys.exit(f"[publish_satsure] robocopy failed (code {rc})")

    log("copying dashboard files -> deploy ...")
    (DEPLOY / "satsure_dashboard").mkdir(parents=True, exist_ok=True)
    for name in DASH_FILES:
        src = HERE / name
        if not src.exists():
            sys.exit(f"[publish_satsure] missing dashboard file: {src}")
        shutil.copy2(src, DEPLOY / "satsure_dashboard" / name)


def verify_live(expected_week: str) -> bool:
    deadline = time.time() + VERIFY_TIMEOUT_S
    req = urllib.request.Request(
        LIVE_MANIFEST_URL,
        headers={"Accept-Encoding": "gzip", "Cache-Control": "no-cache"})
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                manifest = json.loads(raw)
            live_week = manifest["weeks"][-1]["key"]
            if live_week == expected_week:
                log(f"LIVE OK -> {live_week} ({len(manifest['weeks'])} weeks)")
                return True
            log(f"live still old ({live_week}); waiting for {expected_week} ...")
        except Exception as exc:
            log(f"poll error ({exc}); retrying ...")
        time.sleep(VERIFY_INTERVAL_S)
    log(f"TIMEOUT: live manifest never reached {expected_week} "
        f"within {VERIFY_TIMEOUT_S}s (Pages may still update shortly).")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Update & deploy Climate Change at a Glance.")
    parser.add_argument("--build", action="store_true",
                        help="also rebuild the local offline dashboard_standalone.html")
    parser.add_argument("--no-push", action="store_true",
                        help="generate + sync locally but do not commit or push")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip polling the live deployment")
    args = parser.parse_args()

    # Sanity checks
    if not SPI_PYTHON.exists():
        sys.exit(f"[publish_satsure] spi python not found: {SPI_PYTHON}\n"
                 f"Set the SPI_PYTHON env var to the correct interpreter.")
    if not GEN_SCRIPT.exists():
        sys.exit(f"[publish_satsure] missing generator: {GEN_SCRIPT}")

    # Clone the deploy repo if it's missing, or auto-heal it if its git store
    # got NTFS-corrupted (the failure that broke the one-click updater before).
    ensure_deploy_repo()

    env = utf8_env()
    before = latest_local_week()
    log(f"latest local week before run: {before}")

    # 1. Generate new weeks (idempotent)
    log("STEP 1/5  generating new weeks ...")
    run([str(SPI_PYTHON), str(GEN_SCRIPT)], cwd=WD, env=env)

    after = latest_local_week()
    log(f"latest local week after run:  {after}")

    # Optional: refresh the local offline build
    if args.build:
        log("        rebuilding local standalone HTML (--build) ...")
        run([str(SPI_PYTHON), str(BUILD_SCRIPT)], cwd=HERE, env=env)

    # 2. Sync into the deploy repo
    log("STEP 2/5  syncing into deploy repo ...")
    sync_to_deploy()

    if not git_has_changes():
        log("No changes to publish -- already up to date. Nothing to deploy.")
        return

    if args.no_push:
        log("STEP 3-5 skipped (--no-push). Deploy repo updated locally only.")
        return

    # 3. Commit
    commit_msg = f"Climate Change at a Glance: data through {after}"
    log(f"STEP 3/5  committing: {commit_msg!r}")
    git(["add", "-A"])
    git(["commit", "-m", commit_msg])

    # 4. Push deploy (Pages) repo, then the source code repo
    log("STEP 4/5  pushing to GitHub ...")
    push = git(["push", GIT_REMOTE, GIT_BRANCH], check=False)
    if push.returncode != 0:
        log("push rejected -- syncing (pull --rebase) and retrying ...")
        git(["pull", "--rebase", GIT_REMOTE, GIT_BRANCH])
        git(["push", GIT_REMOTE, GIT_BRANCH])
    publish_source(after)

    # 5. Verify live deployment
    if args.no_verify:
        log("STEP 5/5  skipped (--no-verify)")
    else:
        log("STEP 5/5  verifying live deployment (Pages rebuild ~1-3 min) ...")
        verify_live(after)

    log(f"Done. Published data through {after} ({date.today().isoformat()}).")
    log("Live: https://santa1309.github.io/climate_change_at_glance/")


if __name__ == "__main__":
    main()
