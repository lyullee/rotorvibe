@echo off
setlocal
cd /d "%~dp0"
set "VIBRATION_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%VIBRATION_PYTHON%" (
  "%VIBRATION_PYTHON%" run.py %*
) else (
  py -3 run.py %*
)
pause

