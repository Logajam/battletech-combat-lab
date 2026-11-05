@echo off
rem Combat Lab Workbench: double-click to start. Keep this window open while you use the page; close it to stop.
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo Python 3 is not installed on this computer.
  echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then double-click this file again.
  pause
  exit /b 1
)
echo Checking the libraries the builder needs ^(the first time this downloads them; it can take a few minutes^)...
%PY% -m pip install --quiet --disable-pip-version-check --no-warn-script-location numpy scipy trimesh python-fcl
if errorlevel 1 (
  echo Some libraries did not install. The workbench may still run; the "Run checks" button needs python-fcl.
)
start "" cmd /c "timeout /t 6 >nul & start http://127.0.0.1:8765/"
%PY% tools\token_workbench.py --host 127.0.0.1 --port 8765
pause
