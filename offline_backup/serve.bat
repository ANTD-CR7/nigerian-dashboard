@echo off
cd /d "%~dp0"
echo.
echo   ============================================================
echo     NPEDATA offline server
echo     Opening http://localhost:8850 in your browser...
echo     Keep this window OPEN during your defence.
echo     Close it (or press Ctrl+C) when you are finished.
echo   ============================================================
echo.
start "" http://localhost:8850/index.html
py -3 -m http.server 8850 2>nul || python -m http.server 8850 2>nul || "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m http.server 8850
pause
