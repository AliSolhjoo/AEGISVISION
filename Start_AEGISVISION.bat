@echo off
setlocal
title AEGISVISION Launcher

REM Run this file from the AegisVision project root.
set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%PROJECT_DIR%backend"
set "FRONTEND_DIR=%PROJECT_DIR%frontend"

echo.
echo ==========================================
echo        AEGISVISION - DEV LAUNCHER
echo ==========================================
echo.

if not exist "%BACKEND_DIR%\manage.py" (
    echo [ERROR] Django project not found:
    echo "%BACKEND_DIR%\manage.py"
    echo.
    echo Place this BAT file in the AegisVision root folder.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] React/Vite project not found:
    echo "%FRONTEND_DIR%\package.json"
    echo.
    echo Place this BAT file in the AegisVision root folder.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found. Install Node.js LTS and reopen this window.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Frontend dependencies are missing.
    echo Installing them now. This may take a few minutes...
    pushd "%FRONTEND_DIR%"
    call npm.cmd install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        pause
        exit /b 1
    )
    popd
)

echo [INFO] Applying pending Django migrations...
echo.
pushd "%BACKEND_DIR%"
python manage.py migrate --noinput
if errorlevel 1 (
    echo [ERROR] Database migrations failed. No servers were started.
    popd
    pause
    exit /b 1
)
python manage.py check
if errorlevel 1 (
    echo [ERROR] Django system check failed.
    popd
    pause
    exit /b 1
)
popd

echo [INFO] Starting Django, live-camera engine and React...
echo.

start "AEGISVISION - Django Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && python manage.py runserver 127.0.0.1:8000"

timeout /t 3 /nobreak >nul

REM The live manager is a persistent background process. Its window starts minimized.
REM Worker output is retained in backend\logs for diagnosis without cluttering the UI.
if not exist "%BACKEND_DIR%\logs" mkdir "%BACKEND_DIR%\logs"
start "AEGISVISION - Live Camera Worker" /min cmd /c "cd /d ""%BACKEND_DIR%"" && python manage.py run_live_camera_workers >> logs\live_camera_worker.log 2>&1"

timeout /t 2 /nobreak >nul

start "AEGISVISION - React Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && call npm.cmd run dev"

echo [OK] Django, live-camera worker manager and React startup commands were launched.
echo.
echo Backend:  http://127.0.0.1:8000/
echo Frontend: http://localhost:5173/
echo Live camera worker: minimized background process (backend\logs\live_camera_worker.log)
echo.
echo Keep the backend, frontend and minimized worker process running.
echo Close those windows to stop the services.
echo.
pause
endlocal
