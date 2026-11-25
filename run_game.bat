@echo off
setlocal EnableExtensions
chcp 65001 >nul
title CS2 Clone - Auto Installer ^& Launcher

:: Переходим в папку, где лежит этот .bat (поддерживает пробелы и кириллицу)
cd /d "%~dp0"

echo ==============================================================
echo   COUNTER-STRIKE 2 CLONE  ^|  ПРОВЕРКА КОМПОНЕНТОВ И ЗАПУСК
echo ==============================================================
echo.

set "PY_CMD="

:: --------------------------------------------------------------
:: ШАГ 1. Поиск рабочего Python (сначала команда python!)
:: --------------------------------------------------------------
echo [1/3] Проверка Python в системе...
call :find_working_python
if defined PY_CMD goto :python_ok

echo Python не найден. Автоматическое скачивание и установка Python 3.11.9 (x64)...
call :install_python_auto
call :find_working_python
if defined PY_CMD goto :python_ok

echo.
echo [ОШИБКА] Python 3.10+ не найден в системе.
echo Скачайте и установите Python с https://www.python.org/downloads/
echo (обязательно отметьте галочку "Add python.exe to PATH") и запустите run_game.bat снова.
pause
exit /b 1

:python_ok
for /f "delims=" %%V in ('%PY_CMD% -c "import sys; print(sys.version.split()[0])"') do set "PY_VER=%%V"
echo [OK] Найден Python %PY_VER% (команда: %PY_CMD%)
echo.

:: Проверяем наличие самого модуля pip (python -m pip)
%PY_CMD% -m pip --version >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :pip_module_ok

echo [ПОДГОТОВКА] Активация встроенного pip (%PY_CMD% -m ensurepip)...
%PY_CMD% -m ensurepip --upgrade
if not "%ERRORLEVEL%"=="0" goto :pip_boot_error

:pip_module_ok
:: --------------------------------------------------------------
:: ШАГ 2. Пошаговая проверка каждого компонента (если есть — пропуск, нет — python -m pip install)
:: --------------------------------------------------------------
echo [2/3] Проверка библиотек игры (команды через %PY_CMD% -m pip)...

call :ensure_pkg "panda3d.core" "panda3d>=1.10.16"          "Panda3D (3D-ядро)"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "gltf"         "panda3d-gltf>=1.3.0"       "panda3d-gltf (загрузчик .glb)"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "simplepbr"    "panda3d-simplepbr>=0.13.1" "panda3d-simplepbr (PBR-шейдеры)"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "PIL"          "pillow>=10.0.0"            "Pillow (текстуры PNG/JPG)"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "numpy"        "numpy>=1.26.0"             "NumPy (математика и звук)"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "pyperclip"    "pyperclip>=1.9.0"          "pyperclip"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "screeninfo"   "screeninfo>=0.8.1"         "screeninfo"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "ursina"       "ursina>=7.0.0"             "Ursina Engine"
if not "%ERRORLEVEL%"=="0" goto :install_failed

call :ensure_pkg "pygame"       "pygame-ce>=2.5.2"          "Pygame Audio"
if not "%ERRORLEVEL%"=="0" goto :try_classic_pygame
goto :all_pkgs_ok

:try_classic_pygame
call :ensure_pkg "pygame"       "pygame>=2.5.0"             "Pygame Audio (fallback)"
if not "%ERRORLEVEL%"=="0" goto :install_failed

:all_pkgs_ok
echo.

:: --------------------------------------------------------------
:: ШАГ 3. Проверка ассетов в папке assets/ (.glb, .png, .wav)
:: --------------------------------------------------------------
echo [3/3] Проверка игровых ассетов в папке assets/...
if not exist "assets\models\ak47.glb" goto :gen_assets
if not exist "assets\models\m4a1.glb" goto :gen_assets
if not exist "assets\models\deagle.glb" goto :gen_assets
if not exist "assets\models\knife.glb" goto :gen_assets
if not exist "assets\models\enemy.glb" goto :gen_assets
if not exist "assets\models\crate.glb" goto :gen_assets
if not exist "assets\textures\wall_sandstone.png" goto :gen_assets
if not exist "assets\sounds\ak47_shoot.wav" goto :gen_assets

echo   [ПРОПУСК] Все 3D-модели (.glb), текстуры (.png) и звуки (.wav) уже на месте.
goto :launch_game

:gen_assets
if not exist "generate_assets.py" goto :launch_game
echo   [СОЗДАНИЕ] Генерация недостающих стартовых ассетов...
%PY_CMD% generate_assets.py
echo   [OK] Стартовые ассеты созданы!

:: --------------------------------------------------------------
:: ШАГ 4. Запуск игры
:: --------------------------------------------------------------
:launch_game
if /i "%~1"=="--setup-only" exit /b 0

echo.
echo ==============================================================
echo   ЗАПУСК COUNTER-STRIKE 2 (PYTHON + URSINA)...
echo ==============================================================
%PY_CMD% main.py %*
set "GAME_EXIT=%ERRORLEVEL%"

if not "%GAME_EXIT%"=="0" goto :game_crashed
exit /b 0

:game_crashed
echo.
echo [ВНИМАНИЕ] Игра завершилась с кодом ошибки %GAME_EXIT%.
pause
exit /b %GAME_EXIT%


:: ==============================================================
:: ПОДПРОЦЕДУРА ПРОВЕРКИ И ДОКАЧКИ ПАКЕТА ЧЕРЕЗ python -m pip
:: ==============================================================
:ensure_pkg
%PY_CMD% -c "import %~1" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :pkg_skip

echo   [СКАЧИВАНИЕ] %~3  --^>  %PY_CMD% -m pip install "%~2"
%PY_CMD% -m pip install "%~2" --disable-pip-version-check
if "%ERRORLEVEL%"=="0" exit /b 0

echo   [ПОВТОР --user] Пробуем установку в профиль пользователя...
%PY_CMD% -m pip install --user "%~2" --disable-pip-version-check
if "%ERRORLEVEL%"=="0" exit /b 0

exit /b 1

:pkg_skip
echo   [ПРОПУСК] %~3 уже установлен.
exit /b 0


:: ==============================================================
:: ПОДПРОЦЕДУРА ПОИСКА РАБОЧЕГО PYTHON (БЕЗ БАГА ОТРИЦАТЕЛЬНОГО ERRORLEVEL)
:: ==============================================================
:find_working_python
:: 1. Приоритет №1: команда python напрямую (чтобы работало python -m ...)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :use_plain_python

:: 2. Если есть локальный .venv от прошлых запусков
if not exist "%~dp0.venv\Scripts\python.exe" goto :try_py_launcher
"%~dp0.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :use_local_venv

:try_py_launcher
:: 3. Лаунчер py -3 (без жёсткой привязки к 3.11, чтобы pymanager не падал!)
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto :use_py3

:: 4. Стандартные пути установки Python 3.10 - 3.14 в Windows
for %%D in (Python314 Python313 Python312 Python311 Python310) do call :check_py_dir "%%D"
if defined PY_CMD exit /b 0
exit /b 1

:check_py_dir
if defined PY_CMD exit /b 0
if exist "%LocalAppData%\Programs\Python\%~1\python.exe" set PY_CMD="%LocalAppData%\Programs\Python\%~1\python.exe"
if defined PY_CMD exit /b 0
if exist "%ProgramFiles%\%~1\python.exe" set PY_CMD="%ProgramFiles%\%~1\python.exe"
exit /b 0

:use_plain_python
set "PY_CMD=python"
exit /b 0

:use_local_venv
set PY_CMD="%~dp0.venv\Scripts\python.exe"
exit /b 0

:use_py3
set "PY_CMD=py -3"
exit /b 0


:: ==============================================================
:: АВТОУСТАНОВКА PYTHON (ЕСЛИ В СИСТЕМЕ ВООБЩЕ НЕТ PYTHON)
:: ==============================================================
:install_python_auto
where winget >nul 2>&1
if not "%ERRORLEVEL%"=="0" goto :download_python_curl

echo Установка Python через winget...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if "%ERRORLEVEL%"=="0" exit /b 0

:download_python_curl
set "PY_INSTALLER=%TEMP%\python-3.12.8-amd64.exe"
if exist "%PY_INSTALLER%" goto :run_py_installer

echo Скачивание официального установщика Python с python.org...
curl.exe -L --fail -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
if not "%ERRORLEVEL%"=="0" exit /b 1

:run_py_installer
echo Тихая установка Python (подождите 20-40 секунд)...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
exit /b 0


:: ==============================================================
:: ОБРАБОТКА ОШИБОК
:: ==============================================================
:pip_boot_error
echo.
echo [ОШИБКА] Модуль pip недоступен для %PY_CMD%.
pause
exit /b 1

:install_failed
echo.
echo [ОШИБКА] Не удалось скачать один из компонентов через %PY_CMD% -m pip.
echo Проверьте подключение к интернету и попробуйте запустить run_game.bat ещё раз.
pause
exit /b 1
