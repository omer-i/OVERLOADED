@echo off
setlocal EnableDelayedExpansion
title Overloaded - Installer
color 0A

echo.
echo  ====================================================
echo       OVERLOADED  ^|  Game Installer
echo  ====================================================
echo.

:: ── Elevate to admin (required to write to Program Files) ─────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  Requesting administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "INSTALL_DIR=%ProgramFiles%\Overloaded"
set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

:: ── Step 1: Find or install Python 3 ──────────────────────────────
echo  [1/4] Checking for Python 3...
set "PYTHON="
for /f "tokens=*" %%C in ('where python 2^>nul') do if not defined PYTHON set "PYTHON=%%C"

if not defined PYTHON (
    echo         Not found. Installing Python 3.12 via winget...
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    :: Probe common install locations that winget uses
    for %%D in (
        "%LocalAppData%\Programs\Python\Python312"
        "%LocalAppData%\Programs\Python\Python311"
        "%LocalAppData%\Programs\Python\Python310"
        "C:\Python312"
        "C:\Python311"
        "%ProgramFiles%\Python312"
        "%ProgramFiles%\Python311"
    ) do (
        if not defined PYTHON if exist "%%~D\python.exe" set "PYTHON=%%~D\python.exe"
    )
)

if not defined PYTHON (
    echo.
    echo  ERROR: Could not find or install Python automatically.
    echo  Please install Python 3 from https://python.org then re-run this installer.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('"%PYTHON%" --version') do echo         Found: %%V

:: ── Step 2: Install pygame (skip if already present) ───────────────
echo.
echo  [2/4] Checking for pygame...
"%PYTHON%" -c "import pygame" >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=*" %%V in ('"%PYTHON%" -c "import pygame; print(pygame.version.ver)"') do echo         Already installed: pygame %%V
) else (
    echo         Not found. Installing pygame...
    "%PYTHON%" -m pip install --upgrade pip --quiet 2>nul
    "%PYTHON%" -m pip install -r "%SRC%\requirements.txt" --quiet
    if errorlevel 1 (
        echo  ERROR: Failed to install required packages.
        pause
        exit /b 1
    )
    echo         Done.
)

:: ── Step 3: Copy game files ────────────────────────────────────────
echo.
echo  [3/4] Copying game files to "%INSTALL_DIR%"...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
robocopy "%SRC%" "%INSTALL_DIR%" /E /XF install.bat build_exe.py overloaded.spec installer.iss /XD __pycache__ build dist /NFL /NDL /NJH /NJS /nc /ns /np >nul
echo         Done.

:: ── Step 4: Create shortcuts ───────────────────────────────────────
echo.
echo  [4/4] Creating shortcuts...

:: Prefer pythonw.exe (no console window when launching the game)
for %%F in ("%PYTHON%") do set "PYTHON_DIR=%%~dpF"
set "PYTHONW=%PYTHON_DIR%pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=%PYTHON%"

set "GAME_PATH=%INSTALL_DIR%\Game.py"
set "ICON_PATH=%INSTALL_DIR%\overloaded.ico"
set "SM=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Overloaded"

:: Use VBScript + SpecialFolders so the desktop resolves correctly
:: even when it is synced via OneDrive or moved to a custom location
echo Set oWS = WScript.CreateObject("WScript.Shell")          > "%TEMP%\mksc.vbs"
echo sDesk = oWS.SpecialFolders("Desktop")                   >> "%TEMP%\mksc.vbs"
echo Set oL = oWS.CreateShortcut(sDesk ^& "\Overloaded.lnk") >> "%TEMP%\mksc.vbs"
echo oL.TargetPath = "%PYTHONW%"                             >> "%TEMP%\mksc.vbs"
echo oL.Arguments = Chr(34) ^& "%GAME_PATH%" ^& Chr(34)      >> "%TEMP%\mksc.vbs"
echo oL.WorkingDirectory = "%INSTALL_DIR%"                   >> "%TEMP%\mksc.vbs"
echo oL.IconLocation = "%ICON_PATH%"                         >> "%TEMP%\mksc.vbs"
echo oL.Save                                                 >> "%TEMP%\mksc.vbs"

if not exist "%SM%" mkdir "%SM%"
echo Set oM = oWS.CreateShortcut("%SM%\Overloaded.lnk")      >> "%TEMP%\mksc.vbs"
echo oM.TargetPath = "%PYTHONW%"                             >> "%TEMP%\mksc.vbs"
echo oM.Arguments = Chr(34) ^& "%GAME_PATH%" ^& Chr(34)      >> "%TEMP%\mksc.vbs"
echo oM.WorkingDirectory = "%INSTALL_DIR%"                   >> "%TEMP%\mksc.vbs"
echo oM.IconLocation = "%ICON_PATH%"                         >> "%TEMP%\mksc.vbs"
echo oM.Save                                                 >> "%TEMP%\mksc.vbs"

cscript //nologo "%TEMP%\mksc.vbs"
del "%TEMP%\mksc.vbs" >nul 2>&1
echo         Done.

echo.
echo  ====================================================
echo    Installation complete!
echo    Launch Overloaded from your desktop shortcut.
echo  ====================================================
echo.
pause
