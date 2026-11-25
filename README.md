# Counter-Strike 2 Clone — Python 3.11 + Ursina Engine (3D Tactical Shooter)

Полноценный 3D-шутер от первого лица в стиле **Counter-Strike 2**, написанный на **Python 3.11+** и движке **Ursina (Panda3D + glTF 2.0)** с поддержкой `.glb`/`.gltf` моделей, скелетных и процедурных анимаций, системы раундов, ИИ ботов, динамического разброса и отдачи, а также сборки в единый исполняемый файл **`.exe`** через **PyInstaller**.

---

## Скачать проект (ZIP-архив)

- **Прямая ссылка на скачивание ZIP с GitHub:**  
  👉 **[Скачать CS2-Clone ZIP (`arena/c43fb65b-cs2-godot.zip`)](https://github.com/dimasik1325/CS2-GODOT/archive/refs/heads/arena/c43fb65b-cs2-godot.zip)**

---

## 1. Быстрый запуск (Windows — в один клик через `.bat`)

Просто дважды кликните по файлу **`run_game.bat`** в корне проекта! Скрипт сам пошагово:
1. Проверит наличие **Python 3.10+** (если его нет — автоматически скачает и тихо установит Python 3.11.9 x64 через `winget` или `python.org`; если уже есть — **пропустит**).
2. Проверит виртуальное окружение **`.venv`** (если уже создано — **пропустит**).
3. Проверит все библиотеки из `requirements.txt` (`Ursina`, `Panda3D`, `glTF`, `Pygame`, `NumPy`, `Pillow`) по контрольной сумме и импорту (если уже стоят — **мгновенно пропустит** без обращения к сети; если чего-то нет — докачает).
4. Проверит наличие 3D-моделей `.glb`, текстур `.png` и звуков `.wav` в `assets/` (при необходимости сгенерирует недостающие).
5. **Запустит игру** (`main.py`).

### Ручной запуск через терминал (Windows / Linux / macOS)

Требуется **Python 3.11+** (Windows 10/11, Linux или macOS).

```bash
# 1. Создайте и активируйте виртуальное окружение
python -m venv .venv

# Windows (PowerShell / CMD):
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 2. Установите точные версии зависимостей
pip install -r requirements.txt

# 3. Запустите игру (стартовые .glb/.png/.wav/.ttf уже лежат в assets/!)
python main.py
```

> Если вы удалили папку `assets/` и хотите пересоздать стартовые 3D-модели, текстуры и звуки с нуля — выполните:
> ```bash
> python generate_assets.py
> ```
> Даже при полном отсутствии файлов в `assets/` игра автоматически переключится на детализированный fallback из примитивов Ursina без падений.

---

## 2. Сборка в один `.exe` (Windows)

В проекте уже настроен `sys._MEIPASS` (в `src/settings.py`), подготовлен файл `build.spec` и одно-кликовый сборщик **`build_exe.bat`**.

### Способ А — В один клик через `build_exe.bat`
Дважды кликните по **`build_exe.bat`** — он проверит/докачает окружение и PyInstaller (пропустив уже установленное) и соберёт `dist\cs2_clone.exe`.

### Способ Б — Через `build.spec` из терминала
```powershell
pyinstaller --clean -y build.spec
```

### Способ В — Одной командой PyInstaller из терминала (Windows)
```powershell
pyinstaller --onefile --windowed --name cs2_clone --add-data "assets;assets" --collect-all ursina --collect-all panda3d --collect-all gltf --collect-all simplepbr main.py
```

Готовый автономный файл появится по пути **`dist\cs2_clone.exe`** — он не требует установленного Python на целевом ПК и сохраняет пользовательские настройки в `user_settings.json` рядом с `.exe`.

---

## 3. Управление в игре

| Клавиша | Действие |
|---|---|
| `W / A / S / D` | Передвижение |
| `Мышь` | Обзор и прицеливание |
| `Left Shift` | Быстрый бег (повышает разброс и громкость шагов) |
| `Left Ctrl` (или `C`) | Плавный тактический присед (повышает кучность стрельбы и прячет за низкими ящиками) |
| `Space` | Прыжок |
| `ЛКМ` | Огонь (автоочередь на AK-47 / M4A1-S, одиночный на Desert Eagle, удар ножом) |
| `R` | Перезарядка оружия |
| `1` | Основная винтовка (`AK-47`; повторное нажатие `1` переключает `AK-47 ↔ M4A1-S`) |
| `2` | Пистолет (`Desert Eagle`) |
| `3` | Нож (`Tactical Knife`, ускоряет бег как в CS2) |
| `4` | Прямой выбор винтовки с глушителем (`M4A1-S`) |
| `Колесо мыши` | Быстрая прокрутка слотов оружия |
| `Esc` | Пауза / Настройки чувствительности мыши, громкости и количества ботов |

---

## 4. Структура папки `assets/` и замена на реальные CS2-ассеты

Загрузчик `load_safe_model` автоматически нормализует масштаб сторонних `.glb`/`.gltf` моделей (даже если модель с Sketchfab экспортирована в сантиметрах или миллиметрах) и сохраняет их PBR-текстуры. Просто положите скачанный файл под нужным именем:

### 3D-модели (`assets/models/`)
| Имя файла | Назначение в игре | Поддерживаемые анимации внутри `.glb` |
|---|---|---|
| `assets/models/ak47.glb` | Основной автомат **AK-47** в руках игрока | `idle`, `shoot`, `reload`, `walk` (опционально) |
| `assets/models/m4a1.glb` | Автомат спецназа **M4A1-S** с глушителем | `idle`, `shoot`, `reload`, `walk` (опционально) |
| `assets/models/deagle.glb` | Пистолет **Desert Eagle** | `idle`, `shoot`, `reload` (опционально) |
| `assets/models/knife.glb` | Тактический нож | `idle`, `shoot` (опционально) |
| `assets/models/enemy.glb` | 3D-модель бота-противника | `idle`, `walk`, `shoot`, `death` (опционально) |
| `assets/models/crate.glb` | Деревянный тактический ящик на карте | Статический меш |
| `assets/models/arena_map.glb` | *(Опционально)* Полная 3D-карта уровня (например `de_dust2`) | Подхватывается автоматически с `collider='mesh'`! |

> **Подгонка положения оружия в руках:** если у скачанной модели с Sketchfab нестандартный разворот ствола, откройте `src/settings.py` → словарь `WEAPON_SPECS` и измените кортеж `"view_rot": (0.0, 180.0, 0.0)` (например на `(0.0, 90.0, 0.0)` или `(0.0, 0.0, 0.0)`) и `"view_pos"`.

### Текстуры (`assets/textures/`)
- `wall_sandstone.png` — текстура песчаных стен арены
- `floor_dust.png` — текстура пыльного пола арены
- `crate_wood.png` — текстура деревянных ящиков (если используется куб)
- `muzzle_flash.png` — PNG со свечением вспышки выстрела (с прозрачностью RGBA)
- `menu_bg.png` — фоновая иллюстрация Главного меню
- `icon_hp.png`, `icon_armor.png` — иконки здоровья и брони в левом нижнем углу HUD

### Звуки (`assets/sounds/` — поддерживаются `.wav`, `.ogg`, `.mp3`)
- `ak47_shoot.wav`, `m4a1_shoot.wav`, `deagle_shoot.wav`, `knife_slash.wav` — выстрелы и удар ножом
- `reload.wav`, `empty_click.wav` — перезарядка и сухой щелчок пустого магазина
- `footstep.wav` — шаги по песку/камню
- `hitmarker.wav`, `headshot.wav`, `player_hurt.wav` — попадание, звон шлема при хедшоте, урон игроку
- `round_win.wav`, `round_lose.wav` — фанфары победы/поражения в раунде
- `menu_music.wav` — фоновая музыка Главного меню

### Шрифт (`assets/fonts/`)
- `hud_font.ttf` — любой кириллический/латинский шрифт `.ttf` (например *Stratum2*, *Bahnschrift*, *Rajdhani*, *Montserrat Bold*, *DejaVuSans-Bold*).

---

## 5. Где бесплатно скачать крутые готовые ассеты под CS2 (CC0 / Royalty-Free)

1. **Quaternius — Ultimate Gun Pack / Modular Characters (CC0, формат `.gltf`/`.glb`)**  
   - Сайт: `https://quaternius.com` (разделы *Ultimate Gun Pack* и *Animated Soldiers / SWAT Pack*).  
   - Скачайте архив `.glb`, переименуйте автомат Калашникова в `ak47.glb`, карабин M4 в `m4a1.glb`, крупный пистолет в `deagle.glb`, солдата в `enemy.glb` и скопируйте в `assets/models/`.
2. **Kenney.nl — Blaster Kit / Weapon Pack & Prototype Textures (CC0)**  
   - Сайт: `https://kenney.nl/assets` → *Weapon Pack* (`.glb` модели оружия) и *FPS Audio / Impact Sounds* (`.ogg` звуки выстрелов и шагов).
3. **Sketchfab — Карта `de_dust2` и высокополигональные скины оружия (фильтр Downloadable + `.glb`)**  
   - Сайт: `https://sketchfab.com` — в поиске введите:
     - `"Dust2 low poly"` → нажмите **Download 3D Model → Autoconverted format (glTF `.glb`)** → сохраните как `assets/models/arena_map.glb`. При следующем запуске `ArenaMap` автоматически загрузит вашу 3D-карту вместо процедурной арены!
     - `"AK-47 PBR"` / `"M4A1-S"` / `"Desert Eagle"` → скачайте `.glb` и положите в `assets/models/`.
4. **AmbientCG / Poly Haven (CC0 PBR-текстуры песчаника и дерева)**  
   - Сайт: `https://ambientcg.com` — скачайте `Color.jpg` / `.png` из наборов *SandstoneBricks* и *WoodPlanks*, переименуйте в `wall_sandstone.png` и `floor_dust.png` и положите в `assets/textures/`.
5. **Freesound.org / Kenney Audio (звуки выстрелов и интерфейса)**  
   - Любые `.wav` или `.ogg` сэмплы выстрелов сохраните в `assets/sounds/` под именами `ak47_shoot.wav`, `deagle_shoot.wav`, `m4a1_shoot.wav`, `reload.wav`.
