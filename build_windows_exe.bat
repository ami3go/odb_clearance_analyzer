@echo off
setlocal enabledelayedexpansion

rem Build a standalone Windows desktop application for ODB++ Clearance Analyzer.
rem Run this file from the repository/package root on Windows.
rem The output will be in: dist\ODBClearanceAnalyzer\ODBClearanceAnalyzer.exe

set APP_NAME=ODBClearanceAnalyzer
set LAUNCHER=run_gui.py
set BUILD_MODE=--onedir

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set PYTHON=py
) else (
    set PYTHON=python
)

echo Using Python command: %PYTHON%
echo Installing package and build tools...
%PYTHON% -m pip install --upgrade pip
if %ERRORLEVEL% neq 0 goto :error

%PYTHON% -m pip install -e .
if %ERRORLEVEL% neq 0 goto :error

%PYTHON% -m pip install pyinstaller
if %ERRORLEVEL% neq 0 goto :error

echo Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %APP_NAME%.spec del /q %APP_NAME%.spec

echo Building %APP_NAME%...
%PYTHON% -m PyInstaller ^
  %BUILD_MODE% ^
  --windowed ^
  --clean ^
  --noconfirm ^
  --name %APP_NAME% ^
  --collect-all shapely ^
  --collect-all openpyxl ^
  --hidden-import=tkinter ^
  %LAUNCHER%

if %ERRORLEVEL% neq 0 goto :error

echo.
echo Build completed successfully.
echo Start application from:
echo   dist\%APP_NAME%\%APP_NAME%.exe
echo.
echo Note: this is a standalone folder build. Copy the whole dist\%APP_NAME% folder to another PC.
pause
exit /b 0

:error
echo.
echo Build failed. Check the messages above.
pause
exit /b 1
