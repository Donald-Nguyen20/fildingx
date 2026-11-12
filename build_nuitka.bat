@echo off
rem build_nuitka.bat -- double-click to package fildingx with Nuitka.
rem Asks CPU or GPU, then the release name (build_nuitka.ps1 asks that, before
rem building, so any name Windows accepts gets through intact), and runs the
rem build in the repo's venv. The name names the folder and both exes, and the
rem version number in it becomes their file version: Finding9.6.3 gives
rem build_nuitka\Finding9.6.3\Finding9.6.3.exe (GPU: build_nuitka\gpu\...);
rem see build_nuitka.ps1 for the layout.
setlocal
title fildingx - Nuitka build
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo ERROR: no venv in %CD%
    echo Create it and install requirements.txt and nuitka into it first.
    pause
    exit /b 1
)
call "venv\Scripts\activate.bat"

echo.
choice /c CG /n /m "Build for [C]PU or [G]PU (GPU adds ~2.4 GB of CUDA DLLs)? "
if errorlevel 2 (set "VARIANT=-Gpu") else (set "VARIANT=")
echo.

echo Started  %date% %time%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_nuitka.ps1" %VARIANT%
set "RC=%ERRORLEVEL%"
echo.
echo Finished %date% %time%
if "%RC%"=="0" (echo Build OK.) else (echo Build FAILED - exit code %RC%, see the messages above.)
pause
exit /b %RC%
