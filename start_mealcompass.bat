@echo off
rem ============================================================
rem  MealCompass one-click launcher (Windows)
rem
rem  Double-click this file: it starts backend + frontend and
rem  prints the URLs. All checks and diagnostics live in
rem  scripts\start_mealcompass.ps1.
rem
rem  Usage from a terminal:
rem    start_mealcompass.bat          start and print URLs
rem    start_mealcompass.bat check    preflight checks only
rem    start_mealcompass.bat status   show service status
rem    start_mealcompass.bat stop     stop services started before
rem    start_mealcompass.bat open     start and open the browser
rem    start_mealcompass.bat reload   start with backend hot reload
rem ============================================================
setlocal
cd /d "%~dp0"

set "COMMAND=%~1"
if "%COMMAND%"=="" set "COMMAND=start"

set "PSEXE="
where pwsh.exe >nul 2>nul && set "PSEXE=pwsh.exe"
if not defined PSEXE (
  where powershell.exe >nul 2>nul && set "PSEXE=powershell.exe"
)
if not defined PSEXE (
  echo [MealCompass] PowerShell was not found. Please install PowerShell 5.1+.
  pause
  exit /b 1
)

"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_mealcompass.ps1" -Command "%COMMAND%"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo [MealCompass] launcher exited with code %RC%
  pause
)
exit /b %RC%
