@echo off
setlocal
cd /d "%~dp0"
set "STUDYWEAVE_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%STUDYWEAVE_PYTHON%" goto check_dependencies

echo Preparing the StudyWeave Python environment...
python -m venv "%~dp0.venv"
if errorlevel 1 (
  echo Could not create the environment. Install Python 3.11 or later with Tkinter first.
  goto failed
)

:check_dependencies
"%STUDYWEAVE_PYTHON%" -c "import tkinter, webview" >nul 2>nul
if errorlevel 1 (
  echo Installing StudyWeave dependencies into its own environment...
  "%STUDYWEAVE_PYTHON%" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 goto failed
  "%STUDYWEAVE_PYTHON%" -c "import tkinter, webview"
  if errorlevel 1 goto failed
)
if not exist "%~dp0web\dist\index.html" (
  echo The interface has not been built. In the web folder, run npm ci then npm run build.
  goto failed
)
if /i "%~1"=="--check" (
  echo StudyWeave dependencies and interface are ready.
  echo Python: %STUDYWEAVE_PYTHON%
  exit /b 0
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0desktop.py"
exit /b 0

:failed
echo StudyWeave could not start. The error above explains what needs fixing.
if /i not "%~1"=="--check" pause
exit /b 1
