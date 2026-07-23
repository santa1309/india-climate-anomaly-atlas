@echo off
REM ============================================================
REM  Climate Change at a Glance - one-click updater
REM  Double-click this file (or run it from a terminal) to:
REM    1. generate the latest week(s) + refresh the in-progress season
REM    2. publish the data + dashboard to GitHub Pages (live site):
REM         https://santa1309.github.io/climate_change_at_glance/
REM    3. commit + push the SOURCE code repo (pipeline, dashboard, batch)
REM         https://github.com/santa1309/india-climate-anomaly-atlas
REM
REM  Optional args are passed through, e.g.:
REM      update_satsure.bat --build      (also refresh local standalone)
REM      update_satsure.bat --no-push    (dry run, no commit/push)
REM      update_satsure.bat --no-verify  (skip polling the live site)
REM ============================================================
setlocal
cd /d "%~dp0"

REM Force UTF-8 so the generator's special chars don't crash the console
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM The `spi` conda env has the full working stack (imdlib/geopandas/etc).
REM Override by setting SPI_PYTHON before running if your path differs.
if "%SPI_PYTHON%"=="" set SPI_PYTHON=C:\ProgramData\anaconda3\envs\spi\python.exe

if not exist "%SPI_PYTHON%" (
    echo [update] ERROR: spi python not found at "%SPI_PYTHON%"
    echo [update] Set the SPI_PYTHON env var to your interpreter and retry.
    pause
    exit /b 1
)

"%SPI_PYTHON%" publish_satsure.py %*
set RC=%ERRORLEVEL%

echo.
if %RC%==0 (
    echo [update] DONE - Climate Change at a Glance updated.
) else (
    echo [update] FAILED with exit code %RC% - see messages above.
)

REM Keep the window open when double-clicked so you can read the output
pause
exit /b %RC%
