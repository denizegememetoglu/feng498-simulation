@echo off
REM FENG 498 defense deck (Windows). Installs Python automatically if missing.
set "ROOT=%~dp0"
set "URL=http://localhost:8000/web/presentation.html"
where python >/dev/null 2>/dev/null
if errorlevel 1 (
  echo Python not found, installing via winget...
  winget install -e --id Python.Python.3 >/dev/null 2>/dev/null || ( echo Install Python from https://www.python.org/downloads/ then re-run. & pause & exit /b 1 )
)
echo Serving at %URL%
start "" /min python -m http.server 8000 --directory "%ROOT%"
timeout /t 2 >/dev/null
start "" "%URL%"
echo Running. Close this window to stop.
pause
