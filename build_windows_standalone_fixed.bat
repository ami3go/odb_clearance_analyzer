@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM ODB++ Clearance Analyzer - Windows standalone build script
REM Builds an EXE that does not require Python or pip packages on
REM the target PC.
REM
REM Usage:
REM   build_windows_standalone_fixed.bat
REM   build_windows_standalone_fixed.bat onefile
REM   build_windows_standalone_fixed.bat onedir
REM   build_windows_standalone_fixed.bat console
REM
REM Defaults to onefile/windowed.
REM ============================================================

set "APP_NAME=ODBClearanceAnalyzer"
set "LAUNCHER=_pyinstaller_gui_launcher.py"
set "BUILD_MODE=onefile"
set "WINDOW_MODE=windowed"

if /I "%~1"=="onedir" set "BUILD_MODE=onedir"
if /I "%~1"=="onefile" set "BUILD_MODE=onefile"
if /I "%~1"=="console" set "WINDOW_MODE=console"

echo.
echo ============================================================
echo ODB++ Clearance Analyzer standalone Windows build
echo ============================================================
echo Build mode : %BUILD_MODE%
echo UI mode    : %WINDOW_MODE%
echo.

REM ------------------------------------------------------------
REM Check that this BAT is being run from the repository/package root.
REM ------------------------------------------------------------
if not exist "pyproject.toml" (
    echo ERROR: pyproject.toml was not found.
    echo.
    echo Run this BAT from the package root folder, for example:
    echo   cd C:\path\to\odb_clearance_analyzer_pkg_v0414
    echo   build_windows_standalone_fixed.bat
    echo.
    exit /b 1
)

if not exist "odb_clearance_analyzer\gui.py" (
    echo ERROR: odb_clearance_analyzer\gui.py was not found.
    echo.
    echo This script must be run from the folder that contains:
    echo   pyproject.toml
    echo   odb_clearance_analyzer\
    echo.
    exit /b 1
)

REM ------------------------------------------------------------
REM Find Python.
REM ------------------------------------------------------------
set "PYTHON_EXE=python"
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    set "PYTHON_EXE=py"
    %PYTHON_EXE% --version >nul 2>&1
)
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3.10+ and make sure "python" or "py" works in CMD.
    exit /b 1
)

echo Using Python:
%PYTHON_EXE% --version
echo.

REM ------------------------------------------------------------
REM Install/upgrade build tools and project dependencies.
REM This affects only the build PC. The output EXE is standalone.
REM ------------------------------------------------------------
echo Installing build dependencies...
%PYTHON_EXE% -m pip install --upgrade pip
if errorlevel 1 goto :fail

%PYTHON_EXE% -m pip install --upgrade pyinstaller
if errorlevel 1 goto :fail

echo Installing project in editable mode...
%PYTHON_EXE% -m pip install -e .
if errorlevel 1 goto :fail

REM ------------------------------------------------------------
REM Create robust temporary launcher using Python, not CMD echo.
REM This avoids broken redirection caused by parentheses and quotes.
REM ------------------------------------------------------------
echo Creating temporary GUI launcher...
%PYTHON_EXE% -c "from pathlib import Path; Path(r'%LAUNCHER%').write_text('from odb_clearance_analyzer.gui import main\n\nif __name__ == \"__main__\":\n    main()\n', encoding='utf-8')"
if errorlevel 1 goto :fail

if not exist "%LAUNCHER%" (
    echo ERROR: Failed to create %LAUNCHER%.
    goto :fail
)

echo Launcher created:
type "%LAUNCHER%"
echo.

REM ------------------------------------------------------------
REM Clean previous build output.
REM ------------------------------------------------------------
echo Cleaning previous build output...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

REM ------------------------------------------------------------
REM Build options.
REM ------------------------------------------------------------
set "PYI_MODE=--onefile"
if /I "%BUILD_MODE%"=="onedir" set "PYI_MODE=--onedir"

set "PYI_WINDOW=--windowed"
if /I "%WINDOW_MODE%"=="console" set "PYI_WINDOW=--console"

REM ------------------------------------------------------------
REM Run PyInstaller.
REM Notes:
REM - --collect-all odb_clearance_analyzer includes assets/data.
REM - --collect-all shapely includes GEOS DLLs and metadata.
REM - --collect-all openpyxl and et_xmlfile include Excel dependencies.
REM - Tkinter DLLs are usually handled by PyInstaller hooks, but hidden
REM   imports are included to make failures less likely.
REM ------------------------------------------------------------
echo.
echo Building standalone executable...
%PYTHON_EXE% -m PyInstaller ^
  --clean ^
  --noconfirm ^
  %PYI_MODE% ^
  %PYI_WINDOW% ^
  --name "%APP_NAME%" ^
  --collect-all odb_clearance_analyzer ^
  --collect-all shapely ^
  --collect-all openpyxl ^
  --collect-all et_xmlfile ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  --hidden-import shapely ^
  --hidden-import shapely.geometry ^
  --hidden-import shapely.ops ^
  --hidden-import shapely.strtree ^
  --hidden-import openpyxl ^
  --hidden-import et_xmlfile ^
  "%LAUNCHER%"

if errorlevel 1 goto :fail

REM ------------------------------------------------------------
REM Validate build output.
REM ------------------------------------------------------------
echo.
echo ============================================================
echo Build completed successfully.
echo ============================================================

if /I "%BUILD_MODE%"=="onefile" (
    if exist "dist\%APP_NAME%.exe" (
        echo Output:
        echo   dist\%APP_NAME%.exe
        echo.
        echo You can copy this single EXE to another Windows PC.
    ) else (
        echo WARNING: Expected output dist\%APP_NAME%.exe was not found.
    )
) else (
    if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
        echo Output folder:
        echo   dist\%APP_NAME%\
        echo.
        echo Copy the WHOLE dist\%APP_NAME%\ folder to another PC.
        echo Do not copy only the EXE from an onedir build.
    ) else (
        echo WARNING: Expected output folder dist\%APP_NAME%\ was not found.
    )
)

echo.
echo Cleaning temporary launcher...
if exist "%LAUNCHER%" del /q "%LAUNCHER%"

echo Done.
exit /b 0

:fail
echo.
echo ============================================================
echo Build failed.
echo ============================================================
echo.
echo Common fixes:
echo   1. Run this BAT from the package root, where pyproject.toml exists.
echo   2. Make sure Python 3.10+ is installed and available in PATH.
echo   3. Try console mode to see runtime errors:
echo        build_windows_standalone_fixed.bat console
echo   4. If onefile is blocked by antivirus, build folder mode:
echo        build_windows_standalone_fixed.bat onedir
echo   5. For onedir mode, copy the whole dist\%APP_NAME%\ folder.
echo.
if exist "%LAUNCHER%" del /q "%LAUNCHER%"
exit /b 1
