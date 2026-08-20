@echo off
setlocal
cd /d "%~dp0"

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL2 is required. Install WSL2 and Docker Desktop, then run setup.bat again.
  exit /b 1
)

for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%CD%"`) do set "BIST_WSL_PROJECT=%%I"
if not defined BIST_WSL_PROJECT (
  echo Failed to resolve the repository path in WSL2.
  exit /b 1
)

wsl.exe --cd "%BIST_WSL_PROJECT%" bash -lc "chmod +x setup.sh deploy/kubernetes/local.sh && ./setup.sh"
if errorlevel 1 exit /b %errorlevel%

echo Setup completed successfully.
endlocal
