@echo off
setlocal EnableExtensions
chcp 65001 >nul
title CS2 Clone - Build Standalone EXE

cd /d "%~dp0"

:: Сначала проверяем/докачиваем Python, .venv, зависимости и ассеты (если уже есть — пропускает)
call "%~dp0run_game.bat" --setup-only
if errorlevel 1 exit /b 1

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

echo.
echo ==============================================================
echo   ПРОВЕРКА PYINSTALLER И СБОРКА В ОДИН .EXE ФАЙЛ
echo ==============================================================

"%VENV_PY%" -c "import PyInstaller" >nul 2>&1
if not errorlevel 1 goto :pyinstaller_ok

echo [СКАЧИВАНИЕ] Установка PyInstaller...
"%VENV_PY%" -m pip install pyinstaller==6.11.1 --disable-pip-version-check
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить PyInstaller.
    pause
    exit /b 1
)
goto :start_build

:pyinstaller_ok
echo [ПРОПУСК] PyInstaller уже установлен.

:start_build
echo [СБОРКА] Компиляция dist\cs2_clone.exe через build.spec...
"%VENV_PY%" -m PyInstaller --clean -y build.spec
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сборка .exe завершилась с ошибкой.
    pause
    exit /b 1
)

echo.
echo ==============================================================
echo   ГОТОВО! Исполняемый файл создан: "%~dp0dist\cs2_clone.exe"
echo ==============================================================
pause
exit /b 0
