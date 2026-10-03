@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CFD Studio

rem Reuse an existing Studio server without terminating processes
set "CFD_STUDIO_WSL_EXE="
for /f "delims=" %%p in ('where wsl.exe 2^>nul') do if not defined CFD_STUDIO_WSL_EXE set "CFD_STUDIO_WSL_EXE=%%p"
if not defined CFD_STUDIO_WSL_EXE if exist "%SystemRoot%\System32\wsl.exe" set "CFD_STUDIO_WSL_EXE=%SystemRoot%\System32\wsl.exe"
if not defined CFD_STUDIO_WSL_EXE if exist "%SystemRoot%\Sysnative\wsl.exe" set "CFD_STUDIO_WSL_EXE=%SystemRoot%\Sysnative\wsl.exe"
if not defined CFD_STUDIO_WSL_EXE set "CFD_STUDIO_WSL_EXE=wsl.exe"
if not exist "%CFD_STUDIO_WSL_EXE%" set "CFD_STUDIO_WSL_EXE=wsl.exe"
"%CFD_STUDIO_WSL_EXE%" --status >nul 2>&1
if errorlevel 1 echo [note] Initialize WSL2 Ubuntu first. See README.md.

rem --- CFD Studio ships and uses one tested runtime. System Python/Conda/Store aliases are ignored. ---
set "CFD_PYTHON=%~dp0Setup\Python312\python.exe"
if not exist "%CFD_PYTHON%" goto python_missing
"%CFD_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3,12,10) else 1)" >nul 2>&1
if errorlevel 1 goto python_wrong
echo [CFD Studio] Python 3.12.10 x64 bundled runtime
"%CFD_PYTHON%" internal\studio_launcher.py
goto done

:python_missing
echo [CFD Studio] bundled Python runtime not found.
echo   Required: Python 3.12.10 x64
echo   Restore the folder: Setup\Python312
echo   Download the complete repository again if runtime files are missing.
pause
goto :eof

:python_wrong
echo [CFD Studio] bundled Python version mismatch.
echo   Required exactly: Python 3.12.10 x64
echo   Restore Setup\Python312 from the original CFD Studio folder.
pause
goto :eof

:done
echo.
echo [CFD Studio] launcher finished. You can close this window.
pause
