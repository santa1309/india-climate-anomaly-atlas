"""
Bihar district-wise weekly rainfall departure for every kharif since 2021.

Same deliverables as bihar_weekly_report.py — one PNG map per week, a long
district-wise CSV, a per-week category summary — just a different week list:
kharif is Jun 1 - Sep 30 (gen.SEASONS), so months 06-09, W1-W4.

Run:  C:\ProgramData\anaconda3\envs\spi\python.exe bihar_kharif_report.py
"""
from pathlib import Path

from bihar_weekly_report import DATA, run

OUT = Path(r"D:\Satsure\satsure_codes1\dashboard\bihar_kharif_report")
START_YEAR = 2021

WEEKS = sorted(p.stem for p in (DATA / "rainfall" / "weeks").glob("*.json")
               if int(p.stem[:4]) >= START_YEAR and p.stem[5:7] in ("06", "07", "08", "09"))

if __name__ == "__main__":
    run(WEEKS, OUT,
        f"bihar_rainfall_districtwise_kharif_{WEEKS[0][:4]}_{WEEKS[-1][:4]}.csv",
        "bihar_rainfall_kharif_category_summary.csv")
