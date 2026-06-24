@echo off
REM ============================================================
REM  India Climate Anomaly Atlas - weekly one-click updater
REM  Double-click this file (or run it from a terminal) to
REM  generate the latest week and push it to GitHub.
REM
REM  Optional args are passed through, e.g.:
REM      update.bat --build       (also refresh local standalone)
REM      update.bat --no-push     (dry run, no commit/push)
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

"%SPI_PYTHON%" update_atlas.py %*
set RC=%ERRORLEVEL%

echo.
if %RC%==0 (
    echo [update] DONE - git repo updated.
) else (
    echo [update] FAILED with exit code %RC% - see messages above.
)

REM Keep the window open when double-clicked so you can read the output
pause
exit /b %RC%
