@echo off
setlocal EnableExtensions
chcp 65001 >nul
title CS2 Clone - Auto Installer ^& Launcher

:: Переходим в папку скрипта (корректно работает с пробелами и кириллицей)
cd /d "%~dp0"

echo ==============================================================
echo   COUNTER-STRIKE 2 CLONE  ^|  ПРОВЕРКА КОМПОНЕНТОВ И ЗАПУСК
echo ==============================================================
echo.

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "STAMP_FILE=%VENV_DIR%\.deps_ok.stamp"
set "SYS_PY_EXE="
set "SYS_PY_ARGS="

:: --------------------------------------------------------------
:: ШАГ 1. Проверка виртуального окружения .venv и Python 3.10+
:: --------------------------------------------------------------
if exist "%VENV_PY%" goto :venv_ready

echo [1/4] Поиск установленного Python 3.10+ в системе...
call :find_system_python
if defined SYS_PY_EXE goto :create_venv

echo [1/4] Python не найден. Скачивание и установка Python 3.11.9 (x64)...
call :install_python_auto
call :find_system_python
if defined SYS_PY_EXE goto :create_venv

echo.
echo [ОШИБКА] Не удалось автоматически установить Python 3.11.
echo Установите Python 3.11+ с https://www.python.org/downloads/
echo (отметьте галочку "Add python.exe to PATH") и запустите run_game.bat снова.
pause
exit /b 1

:create_venv
echo [OK] Найден Python: "%SYS_PY_EXE%" %SYS_PY_ARGS%
echo [2/4] Создание виртуального окружения .venv...
"%SYS_PY_EXE%" %SYS_PY_ARGS% -m venv "%VENV_DIR%"
if errorlevel 1 goto :venv_error
goto :check_deps

:venv_ready
echo [1/4] [ПРОПУСК] Python уже настроен.
echo [2/4] [ПРОПУСК] Виртуальное окружение .venv уже существует.

:: --------------------------------------------------------------
:: ШАГ 2. Проверка пакетов (Ursina, Panda3D, glTF, Pygame, Pillow, NumPy)
:: --------------------------------------------------------------
:check_deps
echo [3/4] Проверка библиотек из requirements.txt...

"%VENV_PY%" -c "import hashlib, pathlib, sys; import ursina, panda3d, gltf, simplepbr, pygame, numpy, PIL; req = pathlib.Path('requirements.txt').read_bytes(); st = pathlib.Path(sys.argv[1]); sys.exit(0 if (st.is_file() and st.read_text().strip() == hashlib.sha256(req).hexdigest()) else 1)" "%STAMP_FILE%" >nul 2>&1
if not errorlevel 1 goto :deps_ready

echo [СКАЧИВАНИЕ] Установка недостающих компонентов (pip install -r requirements.txt)...
"%VENV_PY%" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 goto :pip_error

"%VENV_PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :pip_error

"%VENV_PY%" -c "import hashlib, pathlib, sys; h = hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); pathlib.Path(sys.argv[1]).write_text(h)" "%STAMP_FILE%"
echo [OK] Все библиотеки успешно скачаны и установлены!
goto :check_assets

:deps_ready
echo [3/4] [ПРОПУСК] Все библиотеки (Ursina, Panda3D, glTF, Pygame, NumPy, Pillow) уже установлены.

:: --------------------------------------------------------------
:: ШАГ 3. Проверка ассетов (.glb, .png, .wav, .ttf)
:: --------------------------------------------------------------
:check_assets
echo [4/4] Проверка игровых ассетов (assets/)...
if not exist "assets\models\ak47.glb" goto :gen_assets
if not exist "assets\models\m4a1.glb" goto :gen_assets
if not exist "assets\models\deagle.glb" goto :gen_assets
if not exist "assets\models\knife.glb" goto :gen_assets
if not exist "assets\models\enemy.glb" goto :gen_assets
if not exist "assets\models\crate.glb" goto :gen_assets
if not exist "assets\textures\wall_sandstone.png" goto :gen_assets
if not exist "assets\sounds\ak47_shoot.wav" goto :gen_assets

echo [4/4] [ПРОПУСК] Все 3D-модели, текстуры и звуки на месте.
goto :launch_game

:gen_assets
if not exist "generate_assets.py" goto :launch_game
echo [СОЗДАНИЕ] Генерация недостающих стартовых ассетов в assets/...
"%VENV_PY%" generate_assets.py
echo [OK] Игровые ассеты готовы!

:: --------------------------------------------------------------
:: ШАГ 4. Запуск игры
:: --------------------------------------------------------------
:launch_game
if /i "%~1"=="--setup-only" exit /b 0

echo.
echo ==============================================================
echo   ЗАПУСК COUNTER-STRIKE 2 (PYTHON + URSINA)...
echo ==============================================================
"%VENV_PY%" main.py %*
set "GAME_EXIT=%ERRORLEVEL%"

if not "%GAME_EXIT%"=="0" goto :game_crashed
exit /b 0

:game_crashed
echo.
echo [ВНИМАНИЕ] Игра завершилась с кодом ошибки %GAME_EXIT%.
pause
exit /b %GAME_EXIT%

:: ==============================================================
:: ПОДПРОЦЕДУРЫ ПОИСКА И АВТОУСТАНОВКИ PYTHON
:: ==============================================================
:find_system_python
where py >nul 2>&1
if errorlevel 1 goto :try_python_path

py -3.11 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY_EXE=py"
    set "SYS_PY_ARGS=-3.11"
    exit /b 0
)

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY_EXE=py"
    set "SYS_PY_ARGS=-3"
    exit /b 0
)

:try_python_path
where python >nul 2>&1
if errorlevel 1 goto :try_standard_dirs

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY_EXE=python"
    set "SYS_PY_ARGS="
    exit /b 0
)

:try_standard_dirs
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    set "SYS_PY_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
    set "SYS_PY_ARGS="
    exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "SYS_PY_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    set "SYS_PY_ARGS="
    exit /b 0
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set "SYS_PY_EXE=%ProgramFiles%\Python311\python.exe"
    set "SYS_PY_ARGS="
    exit /b 0
)
exit /b 1

:install_python_auto
where winget >nul 2>&1
if errorlevel 1 goto :download_python_curl

echo Пробуем установить Python 3.11 через winget...
winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements
if not errorlevel 1 exit /b 0

:download_python_curl
set "PY_INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
if exist "%PY_INSTALLER%" goto :run_py_installer

echo Скачивание официального установщика Python 3.11.9 (x64) с python.org...
curl.exe -L --fail -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if errorlevel 1 exit /b 1

:run_py_installer
echo Выполняется тихая установка Python 3.11.9 (подождите 20-40 секунд)...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
exit /b 0

:venv_error
echo.
echo [ОШИБКА] Не удалось создать виртуальное окружение .venv.
pause
exit /b 1

:pip_error
echo.
echo [ОШИБКА] Ошибка скачивания пакетов через pip. Проверьте интернет-соединение.
pause
exit /b 1
