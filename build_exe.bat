@echo off
setlocal EnableExtensions
chcp 65001 >nul
title CS2 Clone - Build Standalone EXE

cd /d "%~dp0"

:: Проверяем и докачиваем все игровые компоненты (если уже стоят — пропускает)
call "%~dp0run_game.bat" --setup-only
if not "%ERRORLEVEL%"=="0" exit /b 1

:: Определяем рабочую команду Python (сначала python напрямую)
set "PY_CMD=python"
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :check_pyinstaller

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if "%ERRORLEVEL%"=="0" set "PY_CMD=py -3"

:check_pyinstaller
echo.
echo ==============================================================
echo   ПРОВЕРКА PYINSTALLER И СБОРКА В ОДИН .EXE ФАЙЛ
echo ==============================================================

%PY_CMD% -c "import PyInstaller" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :pyinstaller_ok

echo   [СКАЧИВАНИЕ] PyInstaller  --^>  %PY_CMD% -m pip install "pyinstaller>=6.11.1"
%PY_CMD% -m pip install "pyinstaller>=6.11.1" --disable-pip-version-check
if "%ERRORLEVEL%"=="0" goto :start_build

%PY_CMD% -m pip install --user "pyinstaller>=6.11.1" --disable-pip-version-check
if "%ERRORLEVEL%"=="0" goto :start_build

echo.
echo [ОШИБКА] Не удалось установить PyInstaller.
pause
exit /b 1

:pyinstaller_ok
echo   [ПРОПУСК] PyInstaller уже установлен.

:start_build
echo   [СБОРКА] %PY_CMD% -m PyInstaller --clean -y build.spec ...
%PY_CMD% -m PyInstaller --clean -y build.spec
if not "%ERRORLEVEL%"=="0" goto :build_failed

echo.
echo ==============================================================
echo   ГОТОВО! Исполняемый файл создан: "%~dp0dist\cs2_clone.exe"
echo ==============================================================
pause
exit /b 0

:build_failed
echo.
echo [ОШИБКА] Сборка .exe завершилась с ошибкой.
pause
exit /b 1
