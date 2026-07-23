#!/usr/bin/env python3
"""
Stand-alone Dashboard Compiler — SatSure Climate Anomaly Atlas
==============================================================
Compiles this folder's index.html + style.css + app.js together with all
JSON/GeoJSON data (from ../data/) into a single self-contained
dashboard_standalone.html that runs by double-clicking (file:// protocol),
with no local server and no CORS issues.
"""

import base64
import json
import os
import re
import sys
from pathlib import Path


def compile_dashboard():
    here = Path(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(here)

    print("==========================================================")
    print("   BUILDING STAND-ALONE  ·  SatSure Climate Anomaly Atlas")
    print("==========================================================")

    index_path = here / "index.html"
    style_path = here / "style.css"
    app_path = here / "app.js"
    output_path = here / "dashboard_standalone.html"

    for p in (index_path, style_path, app_path):
        if not p.exists():
            print(f"Error: required file missing: {p.name}")
            sys.exit(1)

    print("Reading layout files...")
    html = index_path.read_text(encoding="utf-8")
    css = style_path.read_text(encoding="utf-8")
    js = app_path.read_text(encoding="utf-8")

    # Data lives one level up (shared with the original dashboard).
    data_dir = here.parent / "data"
    print(f"\nReading data files from {data_dir} ...")

    geojson_path = data_dir / "districts.geojson"
    if not geojson_path.exists():
        print(f"Error: Base geometry districts.geojson not found at {geojson_path}")
        sys.exit(1)
    districts_geojson = json.loads(geojson_path.read_text(encoding="utf-8"))

    states_path = data_dir / "states.geojson"
    states_geojson = json.loads(states_path.read_text(encoding="utf-8")) if states_path.exists() else None
    if states_geojson is None:
        print("  Warning: states.geojson missing — state view will be disabled in the build.")

    def load_variable(name):
        vdir = data_dir / name
        manifest = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
        trends_path = vdir / "trends.json"
        trends = json.loads(trends_path.read_text(encoding="utf-8")) if trends_path.exists() else {}
        periods = {}
        for folder in ("weeks", "months", "seasons"):
            fdir = vdir / folder
            periods[folder] = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                               for p in fdir.glob("*.json")} if fdir.exists() else {}
        print(f"  {name}: {len(periods['weeks'])} weeks · "
              f"{len(periods['months'])} months · {len(periods['seasons'])} seasons")
        return {"manifest": manifest, "trends": trends, **periods}

    print("  Loading Rainfall data...")
    rainfall = load_variable("rainfall")
    print("  Loading Temperature data...")
    temperature = load_variable("temperature")

    embedded_data = {
        "districtsGeojson": districts_geojson,
        "statesGeojson": states_geojson,
        "rainfall": rainfall,
        "temperature": temperature,
    }

    print("\nSerializing database into Javascript object...")
    serialized_data = json.dumps(embedded_data, separators=(",", ":"), ensure_ascii=False)

    print("\nInlining CSS, Javascript and logo...")
    # Embed the SatSure logo as a data URI so the single file is self-contained.
    logo_path = here / "Satsure_Transparent_Bg_logo.png"
    if logo_path.exists():
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_uri = f"data:image/png;base64,{logo_b64}"
        html = html.replace('src="Satsure_Transparent_Bg_logo.png"', f'src="{logo_uri}"')
    else:
        print("  Warning: logo file not found; standalone will have no logo.")

    css_inline = f"<style>\n{css}\n</style>"
    html = re.sub(r'<link\s+rel="stylesheet"\s+href="style\.css"\s*/?>', lambda m: css_inline, html)

    js_inline = f"<script>\nconst EMBEDDED_DATA = {serialized_data};\n{js}\n</script>"
    html = re.sub(r'<script\s+src="app\.js"\s*></script>', lambda m: js_inline, html)

    print(f"\nWriting Standalone HTML to: {output_path.name}")
    output_path.write_text(html, encoding="utf-8")

    size_mb = output_path.stat().st_size / 1024 / 1024
    print("==========================================================")
    print("                   BUILD SUCCESSFUL!")
    print("==========================================================")
    print(f"File created: {output_path.name}")
    print(f"Total Size:   {size_mb:.2f} MB")
    print("Double-click it to run offline instantly — no server needed.")
    print("==========================================================")


if __name__ == "__main__":
    compile_dashboard()
