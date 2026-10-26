@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto projectpython
where py >nul 2>nul
if not errorlevel 1 goto pythree
where python >nul 2>nul
if not errorlevel 1 goto systempython
echo Install Python 3.12 from python.org, then open this launcher again.
pause
exit /b 1
:projectpython
".venv\Scripts\python.exe" "launch_weights.py" %*
goto done
:pythree
py -3 "launch_weights.py" %*
goto done
:systempython
python "launch_weights.py" %*
:done
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
