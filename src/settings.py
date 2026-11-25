"""
Конфигурация игры, полноэкранный режим Windows/Linux (DPI-aware),
PBR-материалы Panda3D, характеристики 10 видов оружия и 4 видов гранат CS2,
менеджер настроек, звуковой движок и безопасные загрузчики ассетов (.glb/.png/.wav/.ttf).
"""

from __future__ import annotations

import ctypes
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from panda3d.core import (
    Filename,
    FontPool,
    LPoint3f,
    Material,
    NodePath,
    SamplerState,
    WindowProperties,
    getModelPath,
)
from ursina import Audio, Entity, Texture, Vec2, application, color

try:
    import gltf
except ImportError:  # pragma: no cover
    gltf = None

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None


def enable_windows_dpi_awareness() -> None:
    """Отключает размытие и сдвиг полноэкранного окна при масштабировании 125%/150% в Windows."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def get_native_screen_size() -> tuple[int, int]:
    """Определяет реальное разрешение основного монитора (Windows API / screeninfo / Panda3D)."""
    if sys.platform == "win32":
        try:
            w = int(ctypes.windll.user32.GetSystemMetrics(0))
            h = int(ctypes.windll.user32.GetSystemMetrics(1))
            if w >= 640 and h >= 480:
                return w, h
        except Exception:
            pass

    try:
        from ursina import window

        mon = getattr(window, "main_monitor", None)
        if mon is not None and getattr(mon, "width", 0) >= 640:
            return int(mon.width), int(mon.height)
    except Exception:
        pass

    try:
        if application.base and getattr(application.base, "pipe", None) is not None:
            w = int(application.base.pipe.getDisplayWidth())
            h = int(application.base.pipe.getDisplayHeight())
            if w >= 640 and h >= 480:
                return w, h
    except Exception:
        pass

    return 1920, 1080


def apply_fullscreen_mode(enable: bool) -> None:
    """
    Переключает игру между настоящим полноэкранным режимом на весь монитор
    и оконным режимом 1280x720 без падений в Ursina 7.x и Ursina 8.x.
    """
    from ursina import window

    window._fullscreen = bool(enable)
    if getattr(application, "window_type", None) == "none":
        return
    if not application.base or getattr(application.base, "win", None) is None:
        return

    mon_w, mon_h = get_native_screen_size()
    wp = WindowProperties()
    if enable:
        mon = getattr(window, "main_monitor", None)
        origin_x = int(getattr(mon, "x", 0)) if mon is not None else 0
        origin_y = int(getattr(mon, "y", 0)) if mon is not None else 0
        wp.setUndecorated(True)
        wp.setOrigin(origin_x, origin_y)
        wp.setSize(mon_w, mon_h)
    else:
        win_w = min(1280, max(960, int(mon_w * 0.80)))
        win_h = min(720, max(540, int(mon_h * 0.80)))
        pos_x = max(20, (mon_w - win_w) // 2)
        pos_y = max(20, (mon_h - win_h) // 2)
        wp.setUndecorated(False)
        wp.setFullscreen(False)
        wp.setSize(win_w, win_h)
        wp.setOrigin(pos_x, pos_y)

    try:
        application.base.win.requestProperties(wp)
    except Exception:
        pass


def get_resource_root() -> Path:
    """Возвращает корневую папку ресурсов (включая sys._MEIPASS для PyInstaller .exe)."""
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

_GLB_CACHE: dict[str, NodePath] = {}
_TEX_CACHE: dict[str, Texture | None] = {}
_MAT_CACHE: dict[str, Material] = {}


def rgb32(r: float, g: float, b: float) -> Any:
    """Создаёт цвет из диапазона 0..255 (совместимо и с Ursina 7.x, и с Ursina 8.x)."""
    return color.Color(r / 255.0, g / 255.0, b / 255.0, 1.0)


def rgba32(r: float, g: float, b: float, a: float = 255.0) -> Any:
    """Создаёт цвет с альфа-каналом из диапазона 0..255 (совместимо с Ursina 7.x и 8.x)."""
    return color.Color(r / 255.0, g / 255.0, b / 255.0, a / 255.0)


CROSSHAIR_PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("GREEN", (65, 255, 130)),
    ("CYAN", (65, 235, 255)),
    ("YELLOW", (255, 235, 65)),
    ("WHITE", (250, 250, 250)),
    ("ORANGE", (255, 155, 45)),
    ("PINK", (255, 95, 215)),
)


def get_pbr_material(preset: str = "stone") -> Material:
    """Возвращает кэшированный Panda3D Material с бликами Specular/Shininess для 3D-реализма."""
    if preset in _MAT_CACHE:
        return _MAT_CACHE[preset]

    mat = Material(f"cs2_mat_{preset}")
    presets: dict[str, tuple[float, tuple[float, float, float, float]]] = {
        "stone": (14.0, (0.12, 0.11, 0.09, 1.0)),
        "sand": (8.0, (0.07, 0.06, 0.05, 1.0)),
        "wood": (18.0, (0.16, 0.13, 0.09, 1.0)),
        "asphalt": (16.0, (0.14, 0.14, 0.15, 1.0)),
        "metal": (58.0, (0.58, 0.62, 0.68, 1.0)),
        "steel": (72.0, (0.72, 0.76, 0.82, 1.0)),
        "chrome": (96.0, (0.92, 0.95, 0.98, 1.0)),
        "gold": (88.0, (0.95, 0.78, 0.32, 1.0)),
        "polymer": (32.0, (0.28, 0.30, 0.32, 1.0)),
        "fabric": (9.0, (0.08, 0.08, 0.08, 1.0)),
        "foliage": (12.0, (0.10, 0.14, 0.08, 1.0)),
        "glass": (110.0, (0.95, 0.98, 1.0, 1.0)),
    }
    shininess, spec = presets.get(preset, presets["stone"])
    mat.setShininess(shininess)
    mat.setSpecular(spec)
    _MAT_CACHE[preset] = mat
    return mat


def apply_pbr_material(entity: Entity | NodePath, preset: str = "stone") -> None:
    """Применяет бликовый 3D-материал к объекту Ursina/Panda3D."""
    try:
        entity.setMaterial(get_pbr_material(preset), 1)
    except Exception:
        pass


def configure_ursina_asset_folder() -> None:
    """
    Настраивает пути ресурсов Ursina/Panda3D, защищает Text.font от бага Ursina 8.x
    на Windows и защищает mouse/camera при работе без окна.
    """
    application.asset_folder = RESOURCE_ROOT
    fonts_dir = ASSETS_DIR / "fonts"
    if fonts_dir.is_dir():
        application.fonts_folder = fonts_dir
        p3d_fonts_dir = Filename.fromOsSpecific(str(fonts_dir.resolve()))
        getModelPath().append_path(p3d_fonts_dir)

    from ursina import Text, camera, mouse, window

    if not hasattr(camera, "_clip_plane_far"):
        camera._clip_plane_far = 10000
    if not hasattr(camera, "_clip_plane_near"):
        camera._clip_plane_near = 0.05

    if not getattr(Text, "_cs2_font_patched", False):

        def _safe_font_getter(self: Any) -> Any:
            return getattr(self, "_font", None)

        def _safe_font_setter(self: Any, value: Any) -> None:
            if not value:
                return
            candidate_paths: list[Path] = []
            val_str = str(value)
            direct_p = Path(val_str)
            if direct_p.is_file():
                candidate_paths.append(direct_p)
            rel_p = RESOURCE_ROOT / val_str
            if rel_p.is_file():
                candidate_paths.append(rel_p)
            in_fonts = ASSETS_DIR / "fonts" / Path(val_str).name
            if in_fonts.is_file():
                candidate_paths.append(in_fonts)

            for folder_attr in ("fonts_folder", "asset_folder", "internal_fonts_folder"):
                folder = getattr(application, folder_attr, None)
                if isinstance(folder, Path) and folder.is_dir():
                    for found in folder.glob(f"**/{Path(val_str).name}"):
                        if found.is_file():
                            candidate_paths.append(found)
                            break
                    if candidate_paths:
                        break

            loaded_font = None
            if candidate_paths:
                target = candidate_paths[0].resolve()
                try:
                    p3d_dir = Filename.fromOsSpecific(str(target.parent))
                    getModelPath().append_path(p3d_dir)
                    p3d_full = Filename.fromOsSpecific(str(target)).getFullpath()
                    loaded_font = FontPool.load_font(p3d_full) or FontPool.load_font(target.name)
                except Exception:
                    loaded_font = None
            else:
                try:
                    loaded_font = FontPool.load_font(val_str)
                except Exception:
                    loaded_font = None

            if loaded_font:
                self._font = loaded_font
                self._font.clear()
                self._font.setPixelsPerUnit(getattr(self, "resolution", Text.default_resolution))
                self._font.setLineHeight(getattr(self, "line_height", 1))
                if getattr(self, "raw_text", None):
                    self.text = self.raw_text

        Text.font_getter = _safe_font_getter
        Text.font_setter = _safe_font_setter
        Text.font = property(_safe_font_getter, _safe_font_setter)
        Text._cs2_font_patched = True

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
    return RESOURCE_ROOT / Path(relative_path)


def resolve_font_path(relative_path: str = "assets/fonts/hud_font.ttf") -> str | None:
    full_path = resource_path(relative_path)
    if full_path.is_file():
        getModelPath().append_path(Filename.fromOsSpecific(str(full_path.parent.resolve())))
        return full_path.name
    fonts_dir = ASSETS_DIR / "fonts"
    if fonts_dir.is_dir():
        for candidate in sorted(fonts_dir.glob("*.ttf")):
            getModelPath().append_path(Filename.fromOsSpecific(str(candidate.parent.resolve())))
            return candidate.name
    return None


def load_safe_texture(relative_path: str) -> Texture | None:
    """Безопасно загружает текстуру с анизотропной фильтрацией 8x для чётких стен под углом."""
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
                raw_tex = getattr(tex, "_texture", None)
                if raw_tex is not None:
                    raw_tex.setAnisotropicDegree(8)
                    raw_tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                    raw_tex.setMagfilter(SamplerState.FT_linear)
                    raw_tex.generateRamMipmapImages()
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
    """Безопасно загружает 3D-модель (.glb/.gltf/.obj/.fbx) с кэшированием и нормализацией масштаба."""
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

        wrapper = NodePath(f"template_{found_file.stem}")
        loaded_np.reparentTo(wrapper)

        bounds = loaded_np.getTightBounds()
        if bounds is not None:
            min_pt, max_pt = bounds
            dims = max_pt - min_pt
            max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1e-5)

            if target_max_extent is not None:
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
    """Расширенные пользовательские настройки игры с сохранением на диск."""

    fullscreen: bool = True
    shadows_enabled: bool = True
    time_of_day: str = "DAY"           # DAY | SUNSET | NIGHT
    bot_difficulty: str = "NORMAL"     # EASY | NORMAL | HARD
    crosshair_color_idx: int = 0
    show_damage_numbers: bool = True
    mouse_sensitivity: float = 45.0
    master_volume: float = 0.68
    fov: float = 92.0
    bot_count: int = 5
    round_time_seconds: int = 115
    rounds_to_win: int = 7

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
                instance.fov = float(max(75.0, min(115.0, instance.fov)))
                instance.bot_count = int(max(1, min(10, int(instance.bot_count))))
                if instance.time_of_day not in ("DAY", "SUNSET", "NIGHT"):
                    instance.time_of_day = "DAY"
                if instance.bot_difficulty not in ("EASY", "NORMAL", "HARD"):
                    instance.bot_difficulty = "NORMAL"
                instance.crosshair_color_idx = int(instance.crosshair_color_idx) % len(CROSSHAIR_PALETTE)
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
    """Единый менеджер звука для оружия, гранат, C4, шагов, анонсеров и музыки меню."""

    def __init__(self, master_volume: float = 0.68) -> None:
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
                self._music_audio.volume = 0.42
            except Exception:
                pass
        if self._pygame_ready and pygame is not None:
            try:
                pygame.mixer.music.set_volume(self.master_volume * 0.42)
            except Exception:
                pass

    def play_sfx(self, sound_name: str, volume: float = 0.85, pitch: float = 1.0) -> None:
        if self.master_volume <= 0.001:
            return

        sound_path = self._find_sound_file(sound_name)
        if sound_path is None:
            return

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
        self.stop_menu_music()
        sound_path = self._find_sound_file(track_name)
        if sound_path is None:
            return

        if sound_path.suffix.lower() == ".mp3" and self._pygame_ready and pygame is not None:
            try:
                pygame.mixer.music.load(str(sound_path))
                pygame.mixer.music.set_volume(self.master_volume * 0.42)
                pygame.mixer.music.play(-1)
                return
            except Exception:
                pass

        try:
            rel_key = f"assets/sounds/{sound_path.name}"
            music = Audio(
                rel_key,
                volume=0.42,
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
# ПОЛНЫЙ АРСЕНАЛ ОРУЖИЯ CS2 (10 ОБРАЗЦОВ + ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ ОГНЯ)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "ak47": {
        "slot": 1,
        "category": "primary",
        "price": 2700,
        "kill_reward": 300,
        "display_name": "AK-47",
        "model_path": "assets/models/ak47.glb",
        "shoot_sound": "ak47_shoot",
        "automatic": True,
        "burst_capable": False,
        "silenced": False,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.10,
        "damage": 36,
        "headshot_mult": 3.5,
        "armor_pen": 0.78,
        "wallbang_mult": 0.55,
        "range": 145.0,
        "falloff": 0.98,
        "mag_size": 30,
        "reserve_max": 90,
        "reload_time": 2.15,
        "base_spread": 0.007,
        "max_spread": 0.066,
        "spread_per_shot": 0.011,
        "recoil_pitch": 1.62,
        "recoil_yaw": 0.55,
        "mobility": 0.93,
        "is_melee": False,
        "view_pos": (0.27, -0.24, 0.47),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.72,
    },
    "m4a1": {
        "slot": 1,
        "category": "primary",
        "price": 2900,
        "kill_reward": 300,
        "display_name": "M4A1-S",
        "model_path": "assets/models/m4a1.glb",
        "shoot_sound": "m4a1_shoot",
        "automatic": True,
        "burst_capable": False,
        "silenced": True,
        "pellets": 1,
        "scope_levels": (68.0,),
        "fire_rate": 0.095,
        "damage": 34,
        "headshot_mult": 3.15,
        "armor_pen": 0.72,
        "wallbang_mult": 0.50,
        "range": 150.0,
        "falloff": 0.99,
        "mag_size": 20,
        "reserve_max": 80,
        "reload_time": 1.98,
        "base_spread": 0.0045,
        "max_spread": 0.044,
        "spread_per_shot": 0.0075,
        "recoil_pitch": 1.12,
        "recoil_yaw": 0.34,
        "mobility": 0.96,
        "is_melee": False,
        "view_pos": (0.26, -0.24, 0.46),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.70,
    },
    "awp": {
        "slot": 1,
        "category": "primary",
        "price": 4750,
        "kill_reward": 100,
        "display_name": "AWP SNIPER",
        "model_path": "assets/models/awp.glb",
        "shoot_sound": "awp_shoot",
        "automatic": False,
        "burst_capable": False,
        "silenced": False,
        "pellets": 1,
        "scope_levels": (38.0, 14.0),
        "fire_rate": 1.18,
        "damage": 118,
        "headshot_mult": 4.0,
        "armor_pen": 0.97,
        "wallbang_mult": 0.80,
        "range": 220.0,
        "falloff": 0.995,
        "mag_size": 5,
        "reserve_max": 30,
        "reload_time": 2.85,
        "base_spread": 0.042,        # Без прицела разброс выше, в прицеле почти 0.0!
        "max_spread": 0.090,
        "spread_per_shot": 0.045,
        "recoil_pitch": 4.80,
        "recoil_yaw": 0.65,
        "mobility": 0.82,
        "is_melee": False,
        "view_pos": (0.27, -0.25, 0.45),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.68,
    },
    "mp9": {
        "slot": 1,
        "category": "primary",
        "price": 1250,
        "kill_reward": 600,
        "display_name": "MP9 SMG",
        "model_path": "assets/models/mp9.glb",
        "shoot_sound": "mp9_shoot",
        "automatic": True,
        "burst_capable": False,
        "silenced": False,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.070,          # 857 выстр./мин!
        "damage": 26,
        "headshot_mult": 3.2,
        "armor_pen": 0.60,
        "wallbang_mult": 0.25,
        "range": 95.0,
        "falloff": 0.91,
        "mag_size": 30,
        "reserve_max": 120,
        "reload_time": 1.75,
        "base_spread": 0.010,
        "max_spread": 0.056,
        "spread_per_shot": 0.007,
        "recoil_pitch": 0.92,
        "recoil_yaw": 0.42,
        "mobility": 1.04,
        "is_melee": False,
        "view_pos": (0.25, -0.23, 0.42),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.78,
    },
    "shotgun": {
        "slot": 1,
        "category": "primary",
        "price": 2000,
        "kill_reward": 900,
        "display_name": "XM1014 SHOTGUN",
        "model_path": "assets/models/shotgun.glb",
        "shoot_sound": "shotgun_shoot",
        "automatic": True,
        "burst_capable": False,
        "silenced": False,
        "pellets": 8,
        "scope_levels": (),
        "fire_rate": 0.34,
        "damage": 20,                # 8 картечин x 20 = до 160 урона вблизи!
        "headshot_mult": 2.4,
        "armor_pen": 0.75,
        "wallbang_mult": 0.20,
        "range": 55.0,
        "falloff": 0.78,
        "mag_size": 7,
        "reserve_max": 32,
        "reload_time": 2.25,
        "base_spread": 0.044,
        "max_spread": 0.075,
        "spread_per_shot": 0.016,
        "recoil_pitch": 3.40,
        "recoil_yaw": 0.85,
        "mobility": 0.95,
        "is_melee": False,
        "view_pos": (0.27, -0.24, 0.45),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.72,
    },
    "famas": {
        "slot": 1,
        "category": "primary",
        "price": 2050,
        "kill_reward": 300,
        "display_name": "FAMAS",
        "model_path": "assets/models/famas.glb",
        "shoot_sound": "famas_shoot",
        "automatic": True,
        "burst_capable": True,       # ПКМ переключает AUTO <-> 3-ROUND BURST
        "silenced": False,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.090,
        "damage": 31,
        "headshot_mult": 3.3,
        "armor_pen": 0.70,
        "wallbang_mult": 0.45,
        "range": 135.0,
        "falloff": 0.96,
        "mag_size": 25,
        "reserve_max": 90,
        "reload_time": 2.10,
        "base_spread": 0.0065,
        "max_spread": 0.055,
        "spread_per_shot": 0.009,
        "recoil_pitch": 1.25,
        "recoil_yaw": 0.45,
        "mobility": 0.96,
        "is_melee": False,
        "view_pos": (0.26, -0.24, 0.44),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.72,
    },
    "usp": {
        "slot": 2,
        "category": "secondary",
        "price": 200,
        "kill_reward": 300,
        "display_name": "USP-S",
        "model_path": "assets/models/usp.glb",
        "shoot_sound": "usp_shoot",
        "automatic": False,
        "burst_capable": False,
        "silenced": True,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.17,
        "damage": 35,
        "headshot_mult": 3.5,
        "armor_pen": 0.55,
        "wallbang_mult": 0.25,
        "range": 105.0,
        "falloff": 0.93,
        "mag_size": 12,
        "reserve_max": 36,
        "reload_time": 1.70,
        "base_spread": 0.005,
        "max_spread": 0.048,
        "spread_per_shot": 0.014,
        "recoil_pitch": 1.35,
        "recoil_yaw": 0.35,
        "mobility": 1.02,
        "is_melee": False,
        "view_pos": (0.25, -0.22, 0.42),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.80,
    },
    "deagle": {
        "slot": 2,
        "category": "secondary",
        "price": 700,
        "kill_reward": 300,
        "display_name": "DESERT EAGLE",
        "model_path": "assets/models/deagle.glb",
        "shoot_sound": "deagle_shoot",
        "automatic": False,
        "burst_capable": False,
        "silenced": False,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.27,
        "damage": 54,
        "headshot_mult": 3.7,
        "armor_pen": 0.93,
        "wallbang_mult": 0.65,
        "range": 115.0,
        "falloff": 0.95,
        "mag_size": 7,
        "reserve_max": 35,
        "reload_time": 1.85,
        "base_spread": 0.0055,
        "max_spread": 0.075,
        "spread_per_shot": 0.028,
        "recoil_pitch": 3.10,
        "recoil_yaw": 0.75,
        "mobility": 1.00,
        "is_melee": False,
        "view_pos": (0.26, -0.23, 0.44),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.82,
    },
    "glock": {
        "slot": 2,
        "category": "secondary",
        "price": 200,
        "kill_reward": 300,
        "display_name": "GLOCK-18",
        "model_path": "assets/models/glock.glb",
        "shoot_sound": "glock_shoot",
        "automatic": False,
        "burst_capable": True,       # ПКМ переключает SEMI <-> 3-ROUND BURST
        "silenced": False,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.14,
        "damage": 29,
        "headshot_mult": 3.4,
        "armor_pen": 0.50,
        "wallbang_mult": 0.20,
        "range": 95.0,
        "falloff": 0.90,
        "mag_size": 20,
        "reserve_max": 120,
        "reload_time": 1.65,
        "base_spread": 0.007,
        "max_spread": 0.055,
        "spread_per_shot": 0.012,
        "recoil_pitch": 1.15,
        "recoil_yaw": 0.40,
        "mobility": 1.04,
        "is_melee": False,
        "view_pos": (0.25, -0.22, 0.41),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.82,
    },
    "knife": {
        "slot": 3,
        "category": "melee",
        "price": 0,
        "kill_reward": 1500,
        "display_name": "KARAMBIT KNIFE",
        "model_path": "assets/models/knife.glb",
        "shoot_sound": "knife_slash",
        "automatic": False,
        "burst_capable": False,
        "silenced": True,
        "pellets": 1,
        "scope_levels": (),
        "fire_rate": 0.40,
        "heavy_rate": 0.78,
        "damage": 55,
        "heavy_damage": 90,
        "backstab_damage": 180,
        "headshot_mult": 1.65,
        "armor_pen": 0.88,
        "wallbang_mult": 0.0,
        "range": 3.25,
        "falloff": 1.0,
        "mag_size": -1,
        "reserve_max": -1,
        "reload_time": 0.0,
        "base_spread": 0.0,
        "max_spread": 0.0,
        "spread_per_shot": 0.0,
        "recoil_pitch": 0.5,
        "recoil_yaw": 0.3,
        "mobility": 1.15,
        "is_melee": True,
        "view_pos": (0.27, -0.24, 0.40),
        "view_rot": (8.0, 165.0, -12.0),
        "view_scale": 0.85,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ТАКТИЧЕСКИЕ ГРАНАТЫ И СНАРЯЖЕНИЕ CS2
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRENADE_ORDER: tuple[str, ...] = ("he", "flash", "smoke", "molotov")

GRENADE_SPECS: dict[str, dict[str, Any]] = {
    "he": {
        "display_name": "HE GRENADE",
        "short": "HE",
        "price": 300,
        "max_carry": 1,
        "fuse": 1.75,
        "color_rgb": (92, 118, 72),
    },
    "flash": {
        "display_name": "FLASHBANG",
        "short": "FLASH",
        "price": 200,
        "max_carry": 2,
        "fuse": 1.45,
        "color_rgb": (215, 222, 232),
    },
    "smoke": {
        "display_name": "SMOKE GRENADE",
        "short": "SMOKE",
        "price": 300,
        "max_carry": 1,
        "fuse": 1.80,
        "color_rgb": (118, 132, 146),
    },
    "molotov": {
        "display_name": "MOLOTOV FIRE",
        "short": "MOLO",
        "price": 400,
        "max_carry": 1,
        "fuse": 2.40,
        "color_rgb": (225, 112, 34),
    },
}

BUY_ITEMS: tuple[dict[str, Any], ...] = (
    {"id": "ak47", "kind": "weapon", "label": "AK-47 Rifle", "price": 2700},
    {"id": "m4a1", "kind": "weapon", "label": "M4A1-S Silenced", "price": 2900},
    {"id": "awp", "kind": "weapon", "label": "AWP Sniper", "price": 4750},
    {"id": "mp9", "kind": "weapon", "label": "MP9 Submachine", "price": 1250},
    {"id": "shotgun", "kind": "weapon", "label": "XM1014 Shotgun", "price": 2000},
    {"id": "famas", "kind": "weapon", "label": "FAMAS Burst/Auto", "price": 2050},
    {"id": "deagle", "kind": "weapon", "label": "Desert Eagle", "price": 700},
    {"id": "kevlar_helmet", "kind": "gear", "label": "Kevlar + Helmet", "price": 1000},
    {"id": "defuse_stim", "kind": "gear", "label": "Defuse Kit + Stimshot", "price": 400},
    {"id": "he", "kind": "grenade", "label": "HE Grenade", "price": 300},
    {"id": "flash", "kind": "grenade", "label": "Flashbang", "price": 200},
    {"id": "smoke", "kind": "grenade", "label": "Smoke + Molotov Pack", "price": 650},
)
