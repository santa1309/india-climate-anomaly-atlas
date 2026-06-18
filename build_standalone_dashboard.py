#!/usr/bin/env python3
"""
Stand-alone Dashboard Compiler for India Climate Anomaly Atlas
=============================================================
Compiles all HTML, CSS, JS, and JSON/GeoJSON database files into a single,
self-contained dashboard_standalone.html file. 

This file can be shared with anyone and runs perfectly by simply double-clicking 
it (using the file:// protocol) without needing any local server or facing CORS issues!
"""

import json
import os
import re
import sys
from pathlib import Path


def compile_dashboard():
    # Set directory context
    root_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)

    print("==========================================================")
    print("      BUILDING STAND-ALONE CLIMATE ANOMALY ATLAS")
    print("==========================================================")

    # 1. Read layout files
    index_path = root_dir / "index.html"
    style_path = root_dir / "style.css"
    app_path = root_dir / "app.js"
    output_path = root_dir / "dashboard_standalone.html"

    if not index_path.exists() or not style_path.exists() or not app_path.exists():
        print("Error: index.html, style.css, or app.js is missing from the directory!")
        sys.exit(1)

    print("Reading layout files...")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    with open(style_path, "r", encoding="utf-8") as f:
        css = f.read()
    with open(app_path, "r", encoding="utf-8") as f:
        js = f.read()

    # 2. Compile database
    print("\nReading data files...")
    data_dir = root_dir / "data"

    # GeoJSON
    geojson_path = data_dir / "districts.geojson"
    if not geojson_path.exists():
        print(f"Error: Base geometry districts.geojson not found at {geojson_path}")
        sys.exit(1)
    with open(geojson_path, "r", encoding="utf-8") as f:
        districts_geojson = json.load(f)

    # Rainfall
    print("  Loading Rainfall data...")
    rain_dir = data_dir / "rainfall"
    with open(rain_dir / "manifest.json", "r", encoding="utf-8") as f:
        rain_manifest = json.load(f)
    with open(rain_dir / "timeseries.json", "r", encoding="utf-8") as f:
        rain_timeseries = json.load(f)

    rain_weeks = {}
    for p in (rain_dir / "weeks").glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            rain_weeks[p.stem] = json.load(f)

    # Temperature
    print("  Loading Temperature data...")
    temp_dir = data_dir / "temperature"
    with open(temp_dir / "manifest.json", "r", encoding="utf-8") as f:
        temp_manifest = json.load(f)
    with open(temp_dir / "timeseries.json", "r", encoding="utf-8") as f:
        temp_timeseries = json.load(f)

    temp_weeks = {}
    for p in (temp_dir / "weeks").glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            temp_weeks[p.stem] = json.load(f)

    # Assembly into single dictionary
    embedded_data = {
        "districtsGeojson": districts_geojson,
        "rainfall": {
            "manifest": rain_manifest,
            "timeseries": rain_timeseries,
            "weeks": rain_weeks,
        },
        "temperature": {
            "manifest": temp_manifest,
            "timeseries": temp_timeseries,
            "weeks": temp_weeks,
        },
    }

    print("\nSerializing database into Javascript object...")
    # Serialize to highly compact minified JSON
    serialized_data = json.dumps(
        embedded_data, separators=(",", ":"), ensure_ascii=False
    )

    # 3. Assemble Standalone HTML
    print("\nInlining CSS and Javascript...")
    # Replace style.css link
    css_inline = f"<style>\n{css}\n</style>"
    # Use lambda to treat replacement text as literal (avoids bad escape issues)
    html = re.sub(
        r'<link\s+rel="stylesheet"\s+href="style\.css"\s*/?>', lambda m: css_inline, html
    )

    # Replace app.js script
    js_inline = (
        f"<script>\n"
        f"const EMBEDDED_DATA = {serialized_data};\n"
        f"{js}\n"
        f"</script>"
    )
    html = re.sub(r'<script\s+src="app\.js"\s*></script>', lambda m: js_inline, html)

    # 4. Save output
    print(f"\nWriting Standalone HTML to: {output_path.name}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print("==========================================================")
    print("                   BUILD SUCCESSFUL!")
    print("==========================================================")
    print(f"File created: {output_path.name}")
    print(f"Total Size:   {size_mb:.2f} MB")
    print("You can now share this single file with ANYONE!")
    print("They can double-click it to run offline instantly.")
    print("==========================================================")


if __name__ == "__main__":
    compile_dashboard()
