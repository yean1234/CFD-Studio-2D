@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CFD Studio

rem --- read port from studio_config.json (default 8712) ---
set "CFG=studio_config.json"
set "CFG_PORT="
set "PORT=8712"

for /f "delims=" %%a in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $cfg = Get-Content -Raw -Encoding UTF8 -Path '%CFG%' -ErrorAction Stop; $p = (ConvertFrom-Json $cfg).port; if($p){ Write-Output $p } } catch { }"') do set "CFG_PORT=%%a"

if defined CFG_PORT (
  set "PORT=%CFG_PORT%"
)

rem trim whitespace and keep only integer prefix
for /f "tokens=* delims= " %%a in ("%PORT%") do set "PORT=%%a"
for /f "tokens=1 delims=." %%a in ("%PORT%") do if not "%%a"=="" set "PORT=%%a"
if not defined PORT set "PORT=8712"
if defined CFG_PORT if not "%PORT%"=="%CFG_PORT%" echo [CFD Studio] port override: %CFG_PORT% to %PORT%

set "ORIG_PORT=%PORT%"
set /a "MAX_TRY_PORT=%ORIG_PORT%+80"
set "TRY_PORT=%ORIG_PORT%"
set "IS_CFD="

:RESOLVE_PORT
set "USED_PID="
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr /R /C:":!TRY_PORT! " ^| findstr /C:"LISTENING"') do set "USED_PID=%%p"

if not defined USED_PID goto :NO_USED_PID

set "IS_CFD=0"
set "PS1=%TEMP%\cfd_portcheck_%RANDOM%_%RANDOM%.ps1"
set "CFD_CHECK_PORT=!TRY_PORT!"
set "CFD_CHECK_PID=%USED_PID%"
set "IS_CMD="

>"%PS1%" echo $port = %CFD_CHECK_PORT%
>>"%PS1%" echo $targetPid = %CFD_CHECK_PID%
>>"%PS1%" echo $ans = 0
>>"%PS1%" echo try {
>>"%PS1%" echo   $cmd = Get-CimInstance Win32_Process -Filter "ProcessId=$targetPid" -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty CommandLine
>>"%PS1%" echo   if($cmd){
>>"%PS1%" echo     if($cmd -match 'app\.py' -or $cmd -match 'cfd_studio\\app\.py'){ $ans = 1 }
>>"%PS1%" echo   }
>>"%PS1%" echo   if($ans -eq 0){
>>"%PS1%" echo     try {
>>"%PS1%" echo       $u = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/info" -f $port) -TimeoutSec 2
>>"%PS1%" echo       if($u.app -eq 'cfd-studio'){ $ans = 1 }
>>"%PS1%" echo     } catch {}
>>"%PS1%" echo   }
>>"%PS1%" echo   Write-Output $ans
>>"%PS1%" echo } catch {
>>"%PS1%" echo   Write-Output 0
>>"%PS1%" echo }

for /f "delims=" %%q in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"') do set "IS_CMD=%%~q"
if defined IS_CMD (
  if "!IS_CMD!"=="1" set "IS_CFD=1"
)
del "%PS1%" >nul 2>&1

if /I "%IS_CFD%"=="1" (
  echo !USED_PID!|findstr /R "^[0-9][0-9]*$" >nul
  if !errorlevel! EQU 0 (
    taskkill /F /PID !USED_PID! >nul 2>&1
    if !errorlevel! EQU 0 (
      echo [CFD Studio] previous instance on port !TRY_PORT! stopped
    ) else (
      echo [CFD Studio] cannot stop process !USED_PID! on port !TRY_PORT!
      echo [CFD Studio] skip this port.
      set "IS_CFD=0"
    )
  ) else (
    echo [CFD Studio] invalid process id format on port !TRY_PORT! ^(!USED_PID!^)
    set "IS_CFD=0"
  )
)

if /I "%IS_CFD%"=="1" goto :PORT_OK

:NO_USED_PID

if !TRY_PORT! GEQ !MAX_TRY_PORT! (
  echo [CFD Studio] no free port found up to !MAX_TRY_PORT!.
  pause
  goto :eof
)

if defined USED_PID (
  echo [CFD Studio] port !TRY_PORT! is used by another program ^(PID !USED_PID!^) - switching to next port.
  set /a TRY_PORT+=1
  set "IS_CFD="
  goto :RESOLVE_PORT
)

:PORT_OK
set "PORT=!TRY_PORT!"
set "CFD_STUDIO_PORT=!PORT!"
if not "!PORT!"=="!ORIG_PORT!" echo [CFD Studio] port !ORIG_PORT! was in use. switched to !PORT!

echo [CFD Studio] starting ... (port !PORT!)

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
"%CFD_PYTHON%" app.py
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
echo [CFD Studio] stopped. You can close this window.
pause
