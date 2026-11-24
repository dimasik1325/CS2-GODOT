"""
Конфигурация игры, характеристики оружия, менеджер настроек,
безопасные загрузчики ассетов (.glb/.gltf/.obj, .png/.jpg, .wav/.ogg/.mp3, .ttf)
и поддержка упаковки в единый .exe через PyInstaller (sys._MEIPASS).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from panda3d.core import Filename, LPoint3f, NodePath
from ursina import Audio, Texture, application

try:
    import gltf
except ImportError:  # pragma: no cover
    gltf = None

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None


def get_resource_root() -> Path:
    """
    Возвращает корневую папку ресурсов.
    При запуске собранного PyInstaller --onefile берёт временную директорию sys._MEIPASS.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent.parent


def get_writable_dir() -> Path:
    """Папка рядом с .exe (или корнем проекта) для сохранения user_settings.json."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


RESOURCE_ROOT: Path = get_resource_root()
ASSETS_DIR: Path = RESOURCE_ROOT / "assets"
SETTINGS_FILE: Path = get_writable_dir() / "user_settings.json"

# Кэш загруженных GLB NodePath, чтобы не парсить диск повторно и не терять PBR-текстуры
_GLB_CACHE: dict[str, NodePath] = {}
_TEX_CACHE: dict[str, Texture | None] = {}


def configure_ursina_asset_folder() -> None:
    """Настраивает application.asset_folder и защищает mouse/camera при работе без окна."""
    application.asset_folder = RESOURCE_ROOT
    from ursina import camera, mouse, window

    if not hasattr(camera, "_clip_plane_far"):
        camera._clip_plane_far = 10000
    if not hasattr(camera, "_clip_plane_near"):
        camera._clip_plane_near = 0.05

    mouse_cls = type(mouse)
    if not getattr(mouse_cls, "_cs2_safe_patched", False):

        def _safe_locked_setter(self: Any, value: bool) -> None:
            self._locked = bool(value)
            window.set_mouse_mode(window.M_confined if value else window.M_absolute)
            if not application.base or getattr(application.base, "win", None) is None:
                return
            window.set_cursor_hidden(bool(value))
            application.base.win.requestProperties(window)
            self._locked_mouse_last_frame = True

        def _safe_visible_setter(self: Any, value: bool) -> None:
            self._visible = bool(value)
            window.set_cursor_hidden(not bool(value))
            if application.base and getattr(application.base, "win", None) is not None:
                application.base.win.requestProperties(window)

        mouse_cls.locked = property(lambda self: getattr(self, "_locked", False), _safe_locked_setter)
        mouse_cls.visible = property(lambda self: getattr(self, "_visible", True), _safe_visible_setter)
        mouse_cls._cs2_safe_patched = True


def resource_path(relative_path: str | Path) -> Path:
    """Преобразует относительный путь ('assets/models/ak47.glb') в абсолютный Path."""
    return RESOURCE_ROOT / Path(relative_path)


def resolve_font_path(relative_path: str = "assets/fonts/hud_font.ttf") -> str | None:
    """
    Проверяет наличие .ttf шрифта и возвращает путь в формате Panda3D (forward-slashes).
    Если шрифт не найден — возвращает None (Ursina использует встроенный шрифт).
    """
    full_path = resource_path(relative_path)
    if full_path.is_file():
        return str(Filename.fromOsSpecific(str(full_path)).getFullpath())
    # Поиск любого .ttf в assets/fonts/
    fonts_dir = ASSETS_DIR / "fonts"
    if fonts_dir.is_dir():
        for candidate in sorted(fonts_dir.glob("*.ttf")):
            return str(Filename.fromOsSpecific(str(candidate)).getFullpath())
    return None


def load_safe_texture(relative_path: str) -> Texture | None:
    """
    Безопасно загружает текстуру (.png, .jpg, .dds).
    Если точный файл не найден, пробует альтернативные расширения; иначе возвращает None.
    """
    if relative_path in _TEX_CACHE:
        return _TEX_CACHE[relative_path]

    base_candidate = resource_path(relative_path)
    candidates = [base_candidate]
    if base_candidate.suffix:
        for ext in (".png", ".jpg", ".jpeg", ".dds"):
            candidates.append(base_candidate.with_suffix(ext))

    for file_path in candidates:
        if file_path.is_file():
            try:
                tex = Texture(file_path.resolve())
                _TEX_CACHE[relative_path] = tex
                return tex
            except Exception as exc:
                print(f"[Assets] Ошибка чтения текстуры {file_path.name}: {exc}")

    _TEX_CACHE[relative_path] = None
    return None


def load_safe_model(
    relative_path: str,
    target_max_extent: float | None = None,
    align_bottom_zero: bool = False,
) -> NodePath | None:
    """
    Безопасно загружает 3D-модель (.glb, .gltf, .obj, .fbx).
    - Сохраняет встроенные материалы и вертексные цвета (обходит баг clearTexture в Ursina).
    - При необходимости автоматически нормализует масштаб сторонних моделей с Sketchfab
      (например, экспортированных в сантиметрах вместо метров).
    - При отсутствии файла возвращает None, чтобы вызывающий код включил fallback на примитивы.
    """
    cache_key = f"{relative_path}|{target_max_extent}|{align_bottom_zero}"
    if cache_key in _GLB_CACHE:
        cached_template = _GLB_CACHE[cache_key]
        instance = NodePath(f"instance_{Path(relative_path).stem}")
        cached_template.copyTo(instance)
        return instance

    base_path = resource_path(relative_path)
    candidates = [base_path]
    if base_path.suffix.lower() in (".glb", ".gltf", ".obj", ".fbx"):
        for ext in (".glb", ".gltf", ".obj", ".fbx"):
            alt = base_path.with_suffix(ext)
            if alt not in candidates:
                candidates.append(alt)

    found_file: Path | None = next((p for p in candidates if p.is_file()), None)
    if found_file is None:
        return None

    try:
        suffix = found_file.suffix.lower()
        if suffix in (".glb", ".gltf") and gltf is not None:
            gltf_settings = gltf.GltfSettings()
            model_root = gltf.load_model(str(found_file), gltf_settings=gltf_settings)
            loaded_np = NodePath(model_root)
        else:
            from ursina.mesh_importer import load_model

            loaded_raw = load_model(found_file.name, path=found_file.parent, use_deepcopy=True)
            if loaded_raw is None:
                return None
            loaded_np = loaded_raw if isinstance(loaded_raw, NodePath) else NodePath(loaded_raw)

        # Создаём корневой контейнер для нормализации масштаба/пивота сторонних ассетов
        wrapper = NodePath(f"template_{found_file.stem}")
        loaded_np.reparentTo(wrapper)

        bounds = loaded_np.getTightBounds()
        if bounds is not None:
            min_pt, max_pt = bounds
            dims = max_pt - min_pt
            max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1e-5)

            if target_max_extent is not None:
                # Если модель сильно отличается по масштабу (например FBX/Sketchfab в см или мм)
                if max_dim > target_max_extent * 2.2 or max_dim < target_max_extent * 0.35:
                    scale_factor = target_max_extent / max_dim
                    loaded_np.setScale(scale_factor)
                    bounds = loaded_np.getTightBounds()
                    if bounds is not None:
                        min_pt, max_pt = bounds

            if align_bottom_zero and bounds is not None:
                center_x = (min_pt.x + max_pt.x) * 0.5
                center_z = (min_pt.z + max_pt.z) * 0.5
                loaded_np.setPos(LPoint3f(-center_x, -min_pt.y, -center_z))

        _GLB_CACHE[cache_key] = wrapper
        instance = NodePath(f"instance_{found_file.stem}")
        wrapper.copyTo(instance)
        return instance
    except Exception as exc:
        print(f"[Assets] Не удалось загрузить 3D-модель {found_file.name} ({exc}). Включён fallback на примитивы.")
        return None


@dataclass
class GameSettings:
    """Пользовательские настройки игры с сохранением на диск."""

    mouse_sensitivity: float = 45.0
    master_volume: float = 0.65
    fov: float = 90.0
    bot_count: int = 5
    round_time_seconds: int = 105
    rounds_to_win: int = 5

    @classmethod
    def load(cls) -> "GameSettings":
        if SETTINGS_FILE.is_file():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                instance = cls(**filtered)
                instance.mouse_sensitivity = float(max(5.0, min(140.0, instance.mouse_sensitivity)))
                instance.master_volume = float(max(0.0, min(1.0, instance.master_volume)))
                instance.bot_count = int(max(1, min(10, int(instance.bot_count))))
                return instance
            except Exception as exc:
                print(f"[Settings] Не удалось прочитать {SETTINGS_FILE.name}: {exc}")
        return cls()

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[Settings] Ошибка сохранения настроек: {exc}")


class SoundManager:
    """
    Единый менеджер звука для выстрелов, шагов, интерфейса и музыки меню.
    Использует Ursina Audio с автоматическим fallback на pygame.mixer (для .mp3)
    и защитой от сбоев при отсутствии звукового устройства.
    """

    def __init__(self, master_volume: float = 0.65) -> None:
        self.master_volume: float = max(0.0, min(1.0, master_volume))
        Audio.volume_multiplier = self.master_volume
        self._music_audio: Audio | None = None
        self._pygame_ready: bool = False

        if pygame is not None:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                self._pygame_ready = True
            except Exception:
                self._pygame_ready = False

    def _find_sound_file(self, stem_or_filename: str) -> Path | None:
        sounds_dir = ASSETS_DIR / "sounds"
        if not sounds_dir.is_dir():
            return None
        direct = sounds_dir / stem_or_filename
        if direct.is_file():
            return direct
        stem = Path(stem_or_filename).stem
        for ext in (".wav", ".ogg", ".mp3"):
            candidate = sounds_dir / f"{stem}{ext}"
            if candidate.is_file():
                return candidate
        return None

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.0, float(volume)))
        Audio.volume_multiplier = self.master_volume
        if self._music_audio is not None and getattr(self._music_audio, "_clip", None) is not None:
            try:
                self._music_audio.volume = 0.45
            except Exception:
                pass
        if self._pygame_ready and pygame is not None:
            try:
                pygame.mixer.music.set_volume(self.master_volume * 0.45)
            except Exception:
                pass

    def play_sfx(self, sound_name: str, volume: float = 0.85, pitch: float = 1.0) -> None:
        """Проигрывает короткий звуковой эффект (.wav / .ogg / .mp3)."""
        if self.master_volume <= 0.001:
            return

        sound_path = self._find_sound_file(sound_name)
        if sound_path is None:
            return

        # Для .mp3 используем pygame.mixer, так как Panda3D лучше работает с .wav/.ogg
        if sound_path.suffix.lower() == ".mp3" and self._pygame_ready and pygame is not None:
            try:
                sfx = pygame.mixer.Sound(str(sound_path))
                sfx.set_volume(min(1.0, volume * self.master_volume))
                sfx.play()
                return
            except Exception:
                pass

        try:
            rel_key = f"assets/sounds/{sound_path.name}"
            sfx_entity = Audio(
                rel_key,
                volume=volume,
                pitch=pitch,
                loop=False,
                autoplay=False,
                auto_destroy=False,
            )
            if getattr(sfx_entity, "_clip", None) is not None:
                sfx_entity.play()
                length = max(float(sfx_entity.length or 0.5), 0.15)
                from ursina import destroy

                destroy(sfx_entity, delay=length + 0.1)
            else:
                from ursina import destroy

                destroy(sfx_entity)
        except Exception:
            pass

    def play_menu_music(self, track_name: str = "menu_music") -> None:
        """Запускает зацикленную фоновую тему главного меню."""
        self.stop_menu_music()
        sound_path = self._find_sound_file(track_name)
        if sound_path is None:
            return

        if sound_path.suffix.lower() == ".mp3" and self._pygame_ready and pygame is not None:
            try:
                pygame.mixer.music.load(str(sound_path))
                pygame.mixer.music.set_volume(self.master_volume * 0.45)
                pygame.mixer.music.play(-1)
                return
            except Exception:
                pass

        try:
            rel_key = f"assets/sounds/{sound_path.name}"
            music = Audio(
                rel_key,
                volume=0.45,
                loop=True,
                autoplay=False,
                auto_destroy=False,
            )
            if getattr(music, "_clip", None) is not None:
                music.play()
                self._music_audio = music
            else:
                from ursina import destroy

                destroy(music)
        except Exception:
            self._music_audio = None

    def stop_menu_music(self) -> None:
        """Останавливает фоновую музыку меню при входе в матч."""
        if self._music_audio is not None:
            try:
                self._music_audio.stop(destroy=True)
            except Exception:
                pass
            self._music_audio = None

        if self._pygame_ready and pygame is not None:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ТАКТИКО-ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ ОРУЖИЯ В СТИЛЕ CS2
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "ak47": {
        "slot": 1,
        "display_name": "AK-47",
        "model_path": "assets/models/ak47.glb",
        "shoot_sound": "ak47_shoot",
        "automatic": True,
        "fire_rate": 0.10,           # 600 выстр./мин (классика AK-47 в CS2)
        "damage": 36,                # Урон в корпус
        "headshot_mult": 3.5,        # Ваншот в голову (126 ед.)
        "range": 130.0,
        "falloff": 0.98,
        "mag_size": 30,
        "reserve_max": 90,
        "reload_time": 2.15,
        "base_spread": 0.008,        # Точный первый выстрел
        "max_spread": 0.068,
        "spread_per_shot": 0.011,
        "recoil_pitch": 1.65,
        "recoil_yaw": 0.55,
        "mobility": 0.94,
        "is_melee": False,
        "view_pos": (0.28, -0.24, 0.48),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.72,
        "muzzle_local": (0.0, 0.03, -0.68),
    },
    "deagle": {
        "slot": 2,
        "display_name": "DESERT EAGLE",
        "model_path": "assets/models/deagle.glb",
        "shoot_sound": "deagle_shoot",
        "automatic": False,
        "fire_rate": 0.27,           # Мощный полуавтоматический пистолет
        "damage": 53,
        "headshot_mult": 3.7,        # Знаменитый One-Deag (196 ед.)
        "range": 100.0,
        "falloff": 0.94,
        "mag_size": 7,
        "reserve_max": 35,
        "reload_time": 1.85,
        "base_spread": 0.006,
        "max_spread": 0.075,
        "spread_per_shot": 0.028,
        "recoil_pitch": 3.10,
        "recoil_yaw": 0.75,
        "mobility": 1.00,
        "is_melee": False,
        "view_pos": (0.26, -0.23, 0.44),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.82,
        "muzzle_local": (0.0, 0.03, -0.28),
    },
    "knife": {
        "slot": 3,
        "display_name": "TACTICAL KNIFE",
        "model_path": "assets/models/knife.glb",
        "shoot_sound": "knife_slash",
        "automatic": False,
        "fire_rate": 0.42,
        "damage": 55,
        "headshot_mult": 1.85,
        "range": 3.1,
        "falloff": 1.0,
        "mag_size": -1,              # Бесконечный боезапас
        "reserve_max": -1,
        "reload_time": 0.0,
        "base_spread": 0.0,
        "max_spread": 0.0,
        "spread_per_shot": 0.0,
        "recoil_pitch": 0.6,
        "recoil_yaw": 0.4,
        "mobility": 1.14,            # Бег с ножом быстрее, как в CS2!
        "is_melee": True,
        "view_pos": (0.27, -0.24, 0.40),
        "view_rot": (8.0, 165.0, -12.0),
        "view_scale": 0.85,
        "muzzle_local": (0.0, 0.0, -0.25),
    },
    "m4a1": {
        "slot": 4,
        "display_name": "M4A1-S",
        "model_path": "assets/models/m4a1.glb",
        "shoot_sound": "m4a1_shoot",
        "automatic": True,
        "fire_rate": 0.095,          # Быстрая бесшумная стрельба с мягкой отдачей
        "damage": 33,
        "headshot_mult": 3.1,
        "range": 135.0,
        "falloff": 0.99,
        "mag_size": 20,
        "reserve_max": 80,
        "reload_time": 2.00,
        "base_spread": 0.005,
        "max_spread": 0.046,
        "spread_per_shot": 0.008,
        "recoil_pitch": 1.15,
        "recoil_yaw": 0.35,
        "mobility": 0.96,
        "is_melee": False,
        "view_pos": (0.27, -0.24, 0.47),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.70,
        "muzzle_local": (0.0, 0.02, -0.78),
    },
}
