@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0launcher.py" %*
  exit /b !errorlevel!
)
if defined PAPER_LIBRARY_PYTHON (
  "%PAPER_LIBRARY_PYTHON%" "%~dp0launcher.py" %*
  exit /b !errorlevel!
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0launcher.py" %*
  exit /b !errorlevel!
)
where python >nul 2>nul
if not errorlevel 1 (
  python "%~dp0launcher.py" %*
  exit /b !errorlevel!
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "%~dp0launcher.py" %*
  exit /b !errorlevel!
)
echo Python was not found. Install supported Python 3.12 or newer, then retry.
exit /b 1
