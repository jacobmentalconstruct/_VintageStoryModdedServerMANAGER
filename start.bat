@echo off
title Vintage Story Server Manager (Prototype 2)
echo ===================================================
echo   VS SERVER MANAGER - PROTOTYPE 2
echo ===================================================
echo.
echo Launching application...
echo.

:: Run as a module from the root directory
python -m src.app

:: If the app crashes, keep the window open so we can read the error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] The application closed unexpectedly.
    echo Please review the errors above.
    pause
)
