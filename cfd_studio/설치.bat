@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CFD Studio setup
echo ============================================
echo   CFD Studio setup (WSL + OpenFOAM + case)
echo   Safe to run more than once.
echo ============================================
echo.

rem Use the bundled runtime from the stable ASCII-only Setup path.
set "CFD_PYTHON=%~dp0Setup\Python312\python.exe"
if not defined CFD_PYTHON goto python_missing
"%CFD_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3,12,10) and sys.maxsize.bit_length() == 63 else 1)" >nul 2>&1
if errorlevel 1 goto python_wrong
echo [setup] Python runtime: 3.12.10 x64 ^(bundled^)

set "CFD_STUDIO_WSL_EXE="
for /f "delims=" %%P in ('where wsl.exe 2^>nul') do if not defined CFD_STUDIO_WSL_EXE set "CFD_STUDIO_WSL_EXE=%%P"
if not defined CFD_STUDIO_WSL_EXE if exist "%SystemRoot%\System32\wsl.exe" set "CFD_STUDIO_WSL_EXE=%SystemRoot%\System32\wsl.exe"
if not defined CFD_STUDIO_WSL_EXE if exist "%SystemRoot%\Sysnative\wsl.exe" set "CFD_STUDIO_WSL_EXE=%SystemRoot%\Sysnative\wsl.exe"
if not defined CFD_STUDIO_WSL_EXE set "CFD_STUDIO_WSL_EXE=wsl.exe"

"%CFD_PYTHON%" "%~dp0setup_bridge.py"
if errorlevel 1 (
  echo.
  echo [error] Setup did not finish. Review the message above and run this file again.
  pause
  goto :eof
)
pause
goto :eof

:python_missing
echo [error] Bundled Python runtime folder was not found.
echo         Required exactly: Setup\Python312 ^(Python 3.12.10 x64^).
pause
goto :eof

:python_wrong
echo [error] Bundled Python version mismatch. Required: Python 3.12.10 x64
pause
