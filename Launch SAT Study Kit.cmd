@echo off
setlocal
cd /d "%~dp0"
set "SAT_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%SAT_PYTHON%" goto check_dependencies

echo Preparing the SAT Study Kit Python environment...
python -m venv "%~dp0.venv"
if errorlevel 1 (
  echo Could not create the environment. Install Python 3.11 or later with Tkinter first.
  goto failed
)

:check_dependencies
"%SAT_PYTHON%" -c "import tkinter, webview" >nul 2>nul
if errorlevel 1 (
  echo Installing SAT Study Kit dependencies into its own environment...
  "%SAT_PYTHON%" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 goto failed
  "%SAT_PYTHON%" -c "import tkinter, webview"
  if errorlevel 1 goto failed
)
if not exist "%~dp0web\dist\index.html" (
  echo The interface has not been built. In the web folder, run npm ci then npm run build.
  goto failed
)
if /i "%~1"=="--check" (
  echo SAT Study Kit dependencies and interface are ready.
  echo Python: %SAT_PYTHON%
  exit /b 0
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0desktop.py"
exit /b 0

:failed
echo SAT Study Kit could not start. The error above explains what needs fixing.
if /i not "%~1"=="--check" pause
exit /b 1
