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
import re
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
    if not repo_git_ok(SOURCE) and not repair_repo(SOURCE):
        sys.exit("[publish_satsure] SOURCE git store is corrupt and could not be "
                 "repaired. Deploy/Pages is already updated; fix the source repo "
                 "by hand (it has uncommitted work, so do NOT re-clone it).")
    git_src(["add", "-A"])
    git_src(["commit", "-m", f"Pipeline + dashboard update: data through {after}"])
    push = git_src(["push", "origin", GIT_BRANCH], check=False)
    if push.returncode != 0:
        log("source push rejected -- pull --rebase and retry ...")
        git_src(["pull", "--rebase", "origin", GIT_BRANCH])
        git_src(["push", "origin", GIT_BRANCH])


# `git fsck` reports an unreadable loose object as:
#   error: unable to unpack header of .git/objects/de/761ebe...
BAD_OBJ_RE = re.compile(r"unable to unpack header of (\S+)")
assert BAD_OBJ_RE.findall("error: unable to unpack header of .git/objects/de/761e") == [".git/objects/de/761e"]


def repo_git_ok(repo: Path) -> bool:
    """True if the repo's git store is fully readable (not NTFS-corrupted).
    `git status` is not enough: it never touches the object store, so corrupt
    objects sailed past this check and only blew up later at `git add`. fsck
    actually reads them (~5s per repo)."""
    return subprocess.run(
        ["git", "-C", str(repo), "fsck", "--no-dangling"],
        capture_output=True, text=True).returncode == 0


def repair_repo(repo: Path) -> bool:
    """Heal a corrupt git store in place rather than re-cloning ~350 MB: a damaged
    loose object shadows the good copy in the pack, so delete the ones fsck names
    and re-download. Working tree and uncommitted changes are untouched.
    True if the repo is clean afterwards."""
    fsck = subprocess.run(["git", "-C", str(repo), "fsck", "--no-dangling"],
                          capture_output=True, text=True)
    bad = BAD_OBJ_RE.findall(fsck.stderr)
    if not bad:
        return False
    log(f"{repo.name}: {len(bad)} corrupt git object(s) -- repairing in place ...")
    for rel in bad:
        obj = repo / rel
        if obj.exists():
            obj.chmod(0o600)  # git stores loose objects read-only; Windows enforces it
            obj.unlink()
    run(["git", "-C", str(repo), "fetch", "--refetch", GIT_REMOTE], check=False)
    return repo_git_ok(repo)


def ensure_deploy_repo() -> None:
    """Clone the deploy repo if missing, or re-clone it if its git store got
    corrupted (the '.git/objects: Function not implemented' failure). The data
    is only a mirror of ../data, so a fresh clone loses nothing."""
    if not (DEPLOY / ".git").exists():
        log(f"deploy repo missing -- cloning fresh into {DEPLOY} ...")
        run(["git", "clone", DEPLOY_URL, str(DEPLOY)])
        return
    if repo_git_ok(DEPLOY):
        return
    if repair_repo(DEPLOY):
        log("deploy repo repaired in place.")
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

    if args.no_push:
        log("STEP 3-5 skipped (--no-push). Deploy repo updated locally only.")
        return

    # 3. Commit the deploy mirror (it can already be current when only code
    #    changed -- the source repo below still needs pushing either way).
    if git_has_changes():
        commit_msg = f"Climate Change at a Glance: data through {after}"
        log(f"STEP 3/5  committing: {commit_msg!r}")
        git(["add", "-A"])
        git(["commit", "-m", commit_msg])

        # 4. Push deploy (Pages) repo
        log("STEP 4/5  pushing to GitHub ...")
        push = git(["push", GIT_REMOTE, GIT_BRANCH], check=False)
        if push.returncode != 0:
            log("push rejected -- syncing (pull --rebase) and retrying ...")
            git(["pull", "--rebase", GIT_REMOTE, GIT_BRANCH])
            git(["push", GIT_REMOTE, GIT_BRANCH])
    else:
        log("STEP 3-4  deploy mirror already up to date -- nothing to publish there.")

    # ... then the source code repo, which changes on its own (code edits)
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
