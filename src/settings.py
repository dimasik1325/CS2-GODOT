"""
Ядро настроек, 15 параметров 3D-графики, оптимизации, PBR-материалов, скинов и арсенала (12 пушек).
Поддерживает Python 3.10–3.14, Ursina 7.x и 8.x, PyInstaller (.exe), кириллические пути и живое
обновление графического конвейера Panda3D без перезапуска игры.
"""

from __future__ import annotations

import ctypes
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from panda3d.core import (
    ClockObject,
    Filename,
    LVecBase4f,
    Material,
    SamplerState,
    WindowProperties,
    loadPrcFileData,
)
from panda3d.core import Filename, Loader
from ursina import Audio, Entity, Text, Texture, application, clamp, color, load_model, window


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ПОЛНЫЙ ЭКРАН, FPS LIMIT, VSYNC И СОВМЕСТИМОСТЬ С URSINA 7.x / 8.x
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _detect_screen_resolution() -> tuple[int, int]:
    mon = getattr(window, "main_monitor", None)
    if mon is not None and getattr(mon, "width", 0) and getattr(mon, "height", 0):
        return int(mon.width), int(mon.height)
    if sys.platform == "win32":
        try:
            u32 = ctypes.windll.user32
            w_px, h_px = int(u32.GetSystemMetrics(0)), int(u32.GetSystemMetrics(1))
            if w_px >= 640 and h_px >= 480:
                return w_px, h_px
        except Exception:
            pass
    try:
        pipe = getattr(application.base, "pipe", None)
        if pipe is not None:
            w_px, h_px = int(pipe.getDisplayWidth()), int(pipe.getDisplayHeight())
            if w_px >= 640 and h_px >= 480:
                return w_px, h_px
    except Exception:
        pass
    return 1920, 1080


def apply_fullscreen_mode(enable_fullscreen: bool, vsync_enabled: bool = True) -> None:
    base = getattr(application, "base", None)
    p3d_win = getattr(base, "win", None) if base is not None else None
    if p3d_win is None:
        return
    try:
        loadPrcFileData("", f"sync-video {'#t' if vsync_enabled else '#f'}")
    except Exception:
        pass
    scr_w, scr_h = _detect_screen_resolution()
    wp = WindowProperties()
    if enable_fullscreen:
        wp.setUndecorated(True)
        wp.setOrigin(0, 0)
        wp.setSize(scr_w, scr_h)
    else:
        win_w = min(1280, max(960, int(scr_w * 0.80)))
        win_h = min(720, max(540, int(scr_h * 0.80)))
        wp.setUndecorated(False)
        wp.setFullscreen(False)
        wp.setSize(win_w, win_h)
        wp.setOrigin(max(20, (scr_w - win_w) // 2), max(20, (scr_h - win_h) // 2))
    try:
        p3d_win.requestProperties(wp)
    except Exception:
        pass


def apply_fps_limit(fps_limit: int, vsync_enabled: bool = True) -> None:
    """Настраивает глобальный ограничитель кадров Panda3D ClockObject."""
    try:
        clk = ClockObject.getGlobalClock()
        if vsync_enabled or fps_limit >= 240:
            clk.setMode(ClockObject.MNonLimited)
        else:
            clk.setMode(ClockObject.MLimited)
            clk.setFrameRate(float(max(30, fps_limit)))
    except Exception:
        pass


def rgb32(r: float, g: float, b: float):
    return color.rgb(r / 255.0, g / 255.0, b / 255.0)


def rgba32(r: float, g: float, b: float, a: float = 255.0):
    return color.rgba(r / 255.0, g / 255.0, b / 255.0, a / 255.0)


def _patch_ursina_text_font_safety() -> None:
    if getattr(Text, "_cs2_font_patched", False):
        return
    orig_setter = getattr(Text, "font_setter", None)
    if orig_setter is None and isinstance(getattr(Text, "font", None), property):
        orig_setter = Text.font.fset
    if orig_setter is None:
        return

    def _safe_font_setter(self: Any, value: Any) -> None:
        # Быстрый путь: абсолютный/существующий .ttf путь (glob Ursina 8.3 ломается на abs-путях!)
        try:
            val_str = str(value) if value else ""
            if val_str.lower().endswith((".ttf", ".otf")) and Path(val_str).is_file():
                from panda3d.core import FontPool, getModelPath

                getModelPath().append_path(str(Path(val_str).parent.resolve()))
                fnt = FontPool.load_font(Path(val_str).name)
                if fnt is not None and hasattr(fnt, "isValid") and fnt.isValid():
                    self._font = fnt
                    self._font.clear()
                    self._font.setPixelsPerUnit(getattr(self, "resolution", 100))
                    self._font.setLineHeight(getattr(self, "line_height", 1))
                    if getattr(self, "text", None):
                        self.text = self.text
                    return
        except Exception:
            pass
        try:
            orig_setter(self, value)
            if getattr(self, "_font", None) is not None:
                return
        except Exception:
            pass
        try:
            p3d_loader = getattr(getattr(application, "base", None), "loader", None)
            if p3d_loader is None:
                return
            for candidate in (str(value) if value else "", "cmss12"):
                if not candidate:
                    continue
                try:
                    fnt = p3d_loader.loadFont(candidate)
                except Exception:
                    fnt = None
                if fnt:
                    self._font = fnt
                    self._font.clear()
                    self._font.setPixelsPerUnit(getattr(self, "resolution", 100))
                    self._font.setLineHeight(getattr(self, "line_height", 1))
                    if getattr(self, "text", None):
                        self.text = self.text
                    return
        except Exception:
            pass

    Text.font_setter = _safe_font_setter
    Text.font = property(getattr(Text, "font_getter", lambda self: getattr(self, "_font", None)), _safe_font_setter)
    Text._cs2_font_patched = True


def _patch_ursina_scene_fog_safety() -> None:
    """Ursina Scene.fog_* сеттеры вызывают has_ancestor() на пустых NodePath (например, автоудалённые Audio),
    что обрывает процесс C++-ассертом. Пропатчиваем сеттеры безопасной фильтрацией пустых сущностей."""
    from ursina.scene import Scene as _SceneCls
    from ursina.scene import instance as _scene_instance

    if getattr(_SceneCls, "_cs2_fog_patched", False):
        return

    def _safe_entities() -> list:
        out: list = []
        for e in list(getattr(_scene_instance, "entities", []) or []):
            try:
                if not e.isEmpty():
                    out.append(e)
            except Exception:
                continue
        return out

    def _fog_color_setter(self: Any, value: Any) -> None:
        self._fog_color = value
        try:
            self.fog.setColor(value)
        except Exception:
            pass
        for e in _safe_entities():
            try:
                if e in self._entities_marked_for_removal:
                    continue
                if e.shader and "fog_color" in e.shader.default_input:
                    e.set_shader_input("fog_color", value)
            except Exception:
                continue

    def _fog_density_setter(self: Any, value: Any) -> None:
        self._fog_density = value
        if isinstance(value, tuple):
            try:
                self.fog.setLinearRange(value[0], value[1])
            except Exception:
                pass
            for e in _safe_entities():
                try:
                    if e in self._entities_marked_for_removal:
                        continue
                    if e.shader and "fog_start" in e.shader.default_input and "fog_end" in e.shader.default_input:
                        e.set_shader_input("fog_start", value[0])
                        e.set_shader_input("fog_end", value[1])
                except Exception:
                    continue

    _SceneCls.fog_color = property(_SceneCls.fog_color.fget, _fog_color_setter)
    _SceneCls.fog_density = property(_SceneCls.fog_density.fget, _fog_density_setter)
    _SceneCls._cs2_fog_patched = True


_patch_ursina_text_font_safety()
_patch_ursina_scene_fog_safety()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ПУТИ К РЕСУРСАМ И НАСТРАИВАЕМАЯ АНИЗОТРОПИЯ ТЕКСТУР
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent.parent


def get_writable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


RESOURCE_ROOT: Path = get_resource_root()
WRITABLE_ROOT: Path = get_writable_root()
ASSETS_DIR: Path = RESOURCE_ROOT / "assets"
SETTINGS_FILE: Path = WRITABLE_ROOT / "user_settings.json"

_LOADED_P3D_TEXTURES: list[Any] = []
_CURRENT_ANISO: int = 8


def set_global_anisotropy(level: int) -> None:
    """В реальном времени обновляет анизотропную фильтрацию на всех загруженных 3D-текстурах."""
    global _CURRENT_ANISO
    _CURRENT_ANISO = max(1, min(16, int(level)))
    for p3d_tex in _LOADED_P3D_TEXTURES:
        try:
            p3d_tex.setAnisotropicDegree(_CURRENT_ANISO)
            if _CURRENT_ANISO > 1:
                p3d_tex.setMinfilter(SamplerState.FTLinearMipmapLinear)
                p3d_tex.setMagfilter(SamplerState.FTLinear)
            else:
                p3d_tex.setMinfilter(SamplerState.FTLinear)
        except Exception:
            pass


def configure_ursina_asset_folder() -> None:
    application.asset_folder = RESOURCE_ROOT


def asset_path(relative_path: str) -> Path:
    return RESOURCE_ROOT / relative_path


def apply_pbr_material(
    entity: Entity,
    shininess: float = 28.0,
    specular_strength: float = 0.35,
    metallic: float = 0.0,
    ambient_boost: float = 1.0,
) -> None:
    try:
        mat = Material()
        mat.setShininess(max(1.0, min(128.0, shininess)))
        mat.setSpecular(LVecBase4f(specular_strength, specular_strength, specular_strength, 1.0))
        mat.setAmbient(LVecBase4f(ambient_boost, ambient_boost, ambient_boost, 1.0))
        if hasattr(mat, "setMetallic"):
            mat.setMetallic(max(0.0, min(1.0, metallic)))
        entity.setMaterial(mat, 1)
    except Exception:
        pass


def load_safe_texture(relative_path: str, repeat: bool = True) -> Texture | None:
    full = asset_path(relative_path)
    if not full.is_file():
        return None
    try:
        tex = Texture(str(full))
        p3d_tex = getattr(tex, "_texture", None)
        if p3d_tex is not None:
            p3d_tex.setMinfilter(SamplerState.FTLinearMipmapLinear)
            p3d_tex.setMagfilter(SamplerState.FTLinear)
            p3d_tex.setAnisotropicDegree(_CURRENT_ANISO)
            if repeat:
                p3d_tex.setWrapU(SamplerState.WMRepeat)
                p3d_tex.setWrapV(SamplerState.WMRepeat)
            if p3d_tex not in _LOADED_P3D_TEXTURES:
                _LOADED_P3D_TEXTURES.append(p3d_tex)
        return tex
    except Exception:
        return None


def resolve_font_path(relative_path: str = "assets/fonts/hud_font.ttf") -> str | None:
    full = asset_path(relative_path)
    if not full.is_file() or full.stat().st_size < 256:
        return None
    try:
        p3d_fn = Filename.fromOsSpecific(str(full)).getFullpath()
        p3d_loader = getattr(getattr(application, "base", None), "loader", None)
        if p3d_loader is not None and not p3d_loader.loadFont(p3d_fn):
            return None
        return p3d_fn
    except Exception:
        return None


def normalize_nodepath_scale(node_path: Any, target_span: float = 1.0) -> None:
    try:
        bounds = node_path.getTightBounds()
        if not bounds or len(bounds) != 2:
            return
        min_pt, max_pt = bounds
        dims = max_pt - min_pt
        max_dim = max(abs(dims.x), abs(dims.y), abs(dims.z))
        if max_dim > 1e-4:
            factor = target_span / max_dim
            node_path.setScale(factor)
    except Exception:
        pass


def load_safe_model(relative_path: str, normalize_to: float | None = None) -> Any | None:
    full = asset_path(relative_path)
    if not full.is_file():
        return None
    model_np = None
    try:
        p3d_fn = Filename.fromOsSpecific(str(full))
        raw_loader = getattr(getattr(application, "base", None), "loader", None)
        if raw_loader is not None:
            loaded = raw_loader.loadModel(p3d_fn, noCache=False)
            if loaded is not None and not loaded.isEmpty():
                model_np = loaded.copyTo(Entity()) if False else loaded
    except Exception:
        model_np = None
    if model_np is None:
        try:
            model_np = load_model(relative_path)
        except Exception:
            model_np = None
    if model_np is None:
        try:
            p3d_loader = Loader.getGlobalPtr()
            panda_node = p3d_loader.loadSync(Filename.fromOsSpecific(str(full)))
            if panda_node is not None:
                from panda3d.core import NodePath

                model_np = NodePath(panda_node)
        except Exception:
            model_np = None
    if model_np is not None:
        try:
            model_np = model_np.copyTo(model_np.getParent()) if model_np.hasParent() else model_np.copySubgraph()
        except Exception:
            pass
        if normalize_to is not None:
            normalize_nodepath_scale(model_np, target_span=normalize_to)
    return model_np


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ХРАНЕНИЕ ПОЛЬЗОВАТЕЛЬСКИХ НАСТРОЕК + 15 НАСТРОЕК ГРАФИКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CROSSHAIR_PALETTE: list[tuple[str, tuple[int, int, int]]] = [
    ("GREEN", (75, 255, 115)),
    ("CYAN", (65, 245, 255)),
    ("YELLOW", (255, 235, 55)),
    ("MAGENTA", (255, 85, 235)),
    ("WHITE", (250, 252, 255)),
    ("ELDAR GOLD", (255, 182, 42)),
]

WEAPON_SKINS: list[dict[str, Any]] = [
    {"id": "default", "name": "SPEC-OPS BLACK", "tint": None, "metal": 0.55, "shininess": 42.0},
    {"id": "asiimov", "name": "ASIIMOV CYBER", "tint": (255, 148, 52), "metal": 0.35, "shininess": 56.0},
    {"id": "eldar_gold", "name": "УСАТЫЙ ЗОЛОТОЙ", "tint": (255, 206, 68), "metal": 0.92, "shininess": 96.0},
    {"id": "redline", "name": "REDLINE CRIMSON", "tint": (228, 48, 58), "metal": 0.62, "shininess": 68.0},
    {"id": "emerald", "name": "EMERALD GAMMA", "tint": (52, 232, 132), "metal": 0.78, "shininess": 84.0},
    {"id": "sapphire", "name": "ICE SAPPHIRE", "tint": (72, 168, 255), "metal": 0.82, "shininess": 88.0},
]

PLAYER_RANKS: list[tuple[int, str]] = [
    (0, "SILVER ELITE"),
    (300, "GOLD NOVA MASTER"),
    (800, "MASTER GUARDIAN"),
    (1600, "LEGENDARY EAGLE"),
    (3000, "GLOBAL ELITE • УВАЖАЕМЫЙ"),
]

RADIO_CALLOUTS: list[str] = [
    "РАЦИЯ [CT]: Иду на точку A — прикройте!",
    "РАЦИЯ [CT]: Чисто на Миду, продвигаюсь!",
    "РАЦИЯ [CT]: Бросаю тактическую гранату!",
    "РАЦИЯ [CT]: За уважаемого Алкодимаса и усатого Эльдара — В АТАКУ!",
]


@dataclass
class GameSettings:
    # ── 15 НАСТРОЕК 3D-ГРАФИКИ ──
    fullscreen: bool = True                 # 1. Полный экран
    graphics_preset: str = "HIGH"           # 2. Пресет (LOW / MEDIUM / HIGH / ULTRA / CUSTOM)
    fps_limit: int = 144                    # 3. Лимит FPS (30..240)
    vsync_enabled: bool = True              # 4. VSync (ON/OFF)
    fov: float = 92.0                       # 5. Поле зрения 3D FOV (75..115)
    shadow_quality: int = 2048              # 6. Качество теней (0, 512, 1024, 2048, 4096)
    shader_quality: str = "PBR"             # 7. Шейдеры и блики (FLAT / LIT / PBR)
    anisotropic_level: int = 8              # 8. Анизотропная фильтрация (1, 2, 4, 8, 16)
    render_distance: float = 165.0          # 9. Дальность прорисовки 3D (65..220)
    fog_density: float = 1.0                # 10. Плотность атмосферного тумана (0.0..2.0)
    brightness: float = 1.05                # 11. Яркость и экспозиция (0.60..1.50)
    particles_quality: float = 1.0          # 12. Количество 3D-частиц и дыма (0.0..1.50)
    decal_shell_limit: int = 48             # 13. Лимит декалей и 3D-гильз (0..80)
    dynamic_lights: bool = True             # 14. Динамический свет выстрелов/взрывов (ON/OFF)
    time_of_day: str = "DAY"                # 15. Время суток и небо (DAY / SUNSET / NIGHT / OVERCAST)
    sky_details: bool = True                # Детали неба, пылинок и ветра пальм

    # Обратная совместимость
    shadows_enabled: bool = True

    # ── НАСТРОЙКИ ГЕЙМПЛЕЯ, АУДИО, ПРИЦЕЛА И ПРОГРЕССА ──
    mouse_sensitivity: float = 42.0
    zoom_sensitivity: float = 0.65
    master_volume: float = 0.75
    music_volume: float = 0.45
    bot_count: int = 5
    bot_difficulty: str = "NORMAL"          # EASY / NORMAL / HARD
    game_mode: str = "CLASSIC"              # CLASSIC / DEATHMATCH / HEADSHOT_ONLY / BOSS_ELDAR
    round_time_seconds: int = 115
    rounds_to_win: int = 5

    crosshair_color_idx: int = 0
    crosshair_size: float = 1.0             # 0.5 .. 2.0
    crosshair_gap: float = 1.0              # 0.5 .. 2.0
    crosshair_dot: bool = True
    show_damage_numbers: bool = True
    show_fps_telemetry: bool = True
    radar_zoom: float = 1.0                 # 0.6 .. 1.6
    weapon_skin_idx: int = 0

    player_xp: int = 0
    matches_won: int = 0
    total_career_kills: int = 0

    def apply_preset_values(self, preset: str) -> None:
        p = preset.upper()
        self.graphics_preset = p
        if p == "LOW":
            self.shadow_quality = 0
            self.shadows_enabled = False
            self.shader_quality = "FLAT"
            self.anisotropic_level = 1
            self.render_distance = 85.0
            self.fog_density = 0.65
            self.particles_quality = 0.35
            self.decal_shell_limit = 12
            self.dynamic_lights = False
            self.sky_details = False
        elif p == "MEDIUM":
            self.shadow_quality = 1024
            self.shadows_enabled = True
            self.shader_quality = "LIT"
            self.anisotropic_level = 4
            self.render_distance = 130.0
            self.fog_density = 0.90
            self.particles_quality = 0.75
            self.decal_shell_limit = 28
            self.dynamic_lights = True
            self.sky_details = True
        elif p == "HIGH":
            self.shadow_quality = 2048
            self.shadows_enabled = True
            self.shader_quality = "PBR"
            self.anisotropic_level = 8
            self.render_distance = 165.0
            self.fog_density = 1.0
            self.particles_quality = 1.0
            self.decal_shell_limit = 48
            self.dynamic_lights = True
            self.sky_details = True
        elif p == "ULTRA":
            self.shadow_quality = 4096
            self.shadows_enabled = True
            self.shader_quality = "PBR"
            self.anisotropic_level = 16
            self.render_distance = 220.0
            self.fog_density = 1.15
            self.particles_quality = 1.40
            self.decal_shell_limit = 80
            self.dynamic_lights = True
            self.sky_details = True

    def get_rank_title(self) -> str:
        title = PLAYER_RANKS[0][1]
        for req_xp, r_name in PLAYER_RANKS:
            if self.player_xp >= req_xp:
                title = r_name
        return title

    @classmethod
    def load(cls) -> "GameSettings":
        if SETTINGS_FILE.is_file():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                s = cls(
                    fullscreen=bool(data.get("fullscreen", True)),
                    graphics_preset=str(data.get("graphics_preset", "HIGH")),
                    fps_limit=int(clamp(int(data.get("fps_limit", 144)), 30, 240)),
                    vsync_enabled=bool(data.get("vsync_enabled", True)),
                    fov=float(clamp(float(data.get("fov", 92.0)), 75.0, 115.0)),
                    shadow_quality=int(data.get("shadow_quality", 2048)),
                    shader_quality=str(data.get("shader_quality", "PBR")),
                    anisotropic_level=int(clamp(int(data.get("anisotropic_level", 8)), 1, 16)),
                    render_distance=float(clamp(float(data.get("render_distance", 165.0)), 65.0, 220.0)),
                    fog_density=float(clamp(float(data.get("fog_density", 1.0)), 0.0, 2.0)),
                    brightness=float(clamp(float(data.get("brightness", 1.05)), 0.60, 1.50)),
                    particles_quality=float(clamp(float(data.get("particles_quality", 1.0)), 0.0, 1.50)),
                    decal_shell_limit=int(clamp(int(data.get("decal_shell_limit", 48)), 0, 80)),
                    dynamic_lights=bool(data.get("dynamic_lights", True)),
                    time_of_day=str(data.get("time_of_day", "DAY")),
                    sky_details=bool(data.get("sky_details", True)),
                    shadows_enabled=bool(data.get("shadows_enabled", True)),
                    mouse_sensitivity=float(clamp(float(data.get("mouse_sensitivity", 42.0)), 8.0, 140.0)),
                    zoom_sensitivity=float(clamp(float(data.get("zoom_sensitivity", 0.65)), 0.25, 1.20)),
                    master_volume=float(clamp(float(data.get("master_volume", 0.75)), 0.0, 1.0)),
                    music_volume=float(clamp(float(data.get("music_volume", 0.45)), 0.0, 1.0)),
                    bot_count=int(clamp(int(data.get("bot_count", 5)), 1, 10)),
                    bot_difficulty=str(data.get("bot_difficulty", "NORMAL")),
                    game_mode=str(data.get("game_mode", "CLASSIC")),
                    round_time_seconds=int(clamp(int(data.get("round_time_seconds", 115)), 45, 240)),
                    rounds_to_win=int(clamp(int(data.get("rounds_to_win", 5)), 1, 16)),
                    crosshair_color_idx=int(data.get("crosshair_color_idx", 0)) % len(CROSSHAIR_PALETTE),
                    crosshair_size=float(clamp(float(data.get("crosshair_size", 1.0)), 0.5, 2.0)),
                    crosshair_gap=float(clamp(float(data.get("crosshair_gap", 1.0)), 0.5, 2.0)),
                    crosshair_dot=bool(data.get("crosshair_dot", True)),
                    show_damage_numbers=bool(data.get("show_damage_numbers", True)),
                    show_fps_telemetry=bool(data.get("show_fps_telemetry", True)),
                    radar_zoom=float(clamp(float(data.get("radar_zoom", 1.0)), 0.6, 1.6)),
                    weapon_skin_idx=int(data.get("weapon_skin_idx", 0)) % len(WEAPON_SKINS),
                    player_xp=max(0, int(data.get("player_xp", 0))),
                    matches_won=max(0, int(data.get("matches_won", 0))),
                    total_career_kills=max(0, int(data.get("total_career_kills", 0))),
                )
                if s.shadow_quality not in (0, 512, 1024, 2048, 4096):
                    s.shadow_quality = 2048
                if s.shader_quality not in ("FLAT", "LIT", "PBR"):
                    s.shader_quality = "PBR"
                if s.time_of_day not in ("DAY", "SUNSET", "NIGHT", "OVERCAST"):
                    s.time_of_day = "DAY"
                if s.bot_difficulty not in ("EASY", "NORMAL", "HARD"):
                    s.bot_difficulty = "NORMAL"
                if s.game_mode not in ("CLASSIC", "DEATHMATCH", "HEADSHOT_ONLY", "BOSS_ELDAR"):
                    s.game_mode = "CLASSIC"
                s.shadows_enabled = s.shadow_quality > 0
                return s
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        self.shadows_enabled = self.shadow_quality > 0
        try:
            SETTINGS_FILE.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. МЕНЕДЖЕР ЗВУКА И МУЗЫКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class SoundManager:
    def __init__(self, master_volume: float = 0.75, music_volume: float = 0.45) -> None:
        self.master_volume: float = master_volume
        self.music_volume: float = music_volume
        self._menu_music: Audio | None = None
        self._available_cache: dict[str, str | None] = {}

    def _find_sound_relpath(self, name: str) -> str | None:
        if name in self._available_cache:
            return self._available_cache[name]
        for ext in (".wav", ".ogg", ".mp3"):
            rel = f"assets/sounds/{name}{ext}"
            if asset_path(rel).is_file():
                self._available_cache[name] = rel
                return rel
        self._available_cache[name] = None
        return None

    def play_sfx(self, name: str, volume: float = 1.0, pitch: float = 1.0) -> None:
        if self.master_volume <= 0.001:
            return
        rel = self._find_sound_relpath(name)
        if rel is None:
            return
        try:
            Audio(
                rel,
                volume=clamp(volume * self.master_volume, 0.0, 1.0),
                pitch=pitch,
                autoplay=True,
                auto_destroy=True,
            )
        except Exception:
            pass

    def play_menu_music(self, name: str = "menu_music") -> None:
        rel = self._find_sound_relpath(name)
        if rel is None:
            return
        try:
            if self._menu_music is None:
                self._menu_music = Audio(
                    rel,
                    loop=True,
                    autoplay=True,
                    volume=clamp(self.music_volume * self.master_volume, 0.0, 1.0),
                )
            else:
                self._menu_music.volume = clamp(self.music_volume * self.master_volume, 0.0, 1.0)
                if not self._menu_music.playing:
                    self._menu_music.play()
        except Exception:
            self._menu_music = None

    def stop_menu_music(self) -> None:
        if self._menu_music is not None:
            try:
                self._menu_music.stop()
            except Exception:
                pass

    def set_volumes(self, master: float, music: float | None = None) -> None:
        self.master_volume = clamp(master, 0.0, 1.0)
        if music is not None:
            self.music_volume = clamp(music, 0.0, 1.0)
        if self._menu_music is not None:
            try:
                self._menu_music.volume = clamp(self.music_volume * self.master_volume, 0.0, 1.0)
            except Exception:
                pass

    def set_master_volume(self, value: float) -> None:
        self.set_volumes(value, None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. ТТХ ПОЛНОГО АРСЕНАЛА (12 ВИДОВ ОРУЖИЯ + ГРАНАТЫ + ЗАКУПКА)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "ak47": {
        "display_name": "AK-47",
        "slot": 1,
        "category": "primary",
        "price": 2700,
        "kill_reward": 300,
        "model_path": "assets/models/ak47.glb",
        "shoot_sound": "ak47_shoot",
        "silenced": False,
        "damage": 36,
        "headshot_mult": 3.9,
        "pellets": 1,
        "fire_interval": 0.10,
        "automatic": True,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": 30,
        "reserve_max": 90,
        "reload_time": 2.25,
        "base_spread": 0.011,
        "move_spread": 0.042,
        "jump_spread": 0.105,
        "recoil_pitch": 1.65,
        "recoil_yaw": 0.65,
        "range": 140.0,
        "falloff": 0.985,
        "penetration": 0.68,
        "is_melee": False,
        "mobility": 0.94,
        "view_pos": (0.31, -0.27, 0.62),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.80,
    },
    "m4a1": {
        "display_name": "M4A1-S",
        "slot": 1,
        "category": "primary",
        "price": 2900,
        "kill_reward": 300,
        "model_path": "assets/models/m4a1.glb",
        "shoot_sound": "m4a1_shoot",
        "silenced": True,
        "damage": 33,
        "headshot_mult": 3.4,
        "pellets": 1,
        "fire_interval": 0.09,
        "automatic": True,
        "supports_burst": False,
        "scope_fovs": [62.0],
        "mag_size": 20,
        "reserve_max": 80,
        "reload_time": 2.05,
        "base_spread": 0.006,
        "move_spread": 0.028,
        "jump_spread": 0.088,
        "recoil_pitch": 1.10,
        "recoil_yaw": 0.40,
        "range": 145.0,
        "falloff": 0.99,
        "penetration": 0.62,
        "is_melee": False,
        "mobility": 0.96,
        "view_pos": (0.30, -0.26, 0.64),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.80,
    },
    "awp": {
        "display_name": "AWP Sniper",
        "slot": 1,
        "category": "primary",
        "price": 4750,
        "kill_reward": 100,
        "model_path": "assets/models/awp.glb",
        "shoot_sound": "awp_shoot",
        "silenced": False,
        "damage": 115,
        "headshot_mult": 3.85,
        "pellets": 1,
        "fire_interval": 1.18,
        "automatic": False,
        "supports_burst": False,
        "scope_fovs": [38.0, 16.0],
        "mag_size": 5,
        "reserve_max": 30,
        "reload_time": 3.10,
        "base_spread": 0.048,
        "scoped_spread": 0.0008,
        "move_spread": 0.085,
        "jump_spread": 0.190,
        "recoil_pitch": 5.20,
        "recoil_yaw": 0.85,
        "range": 220.0,
        "falloff": 0.998,
        "penetration": 0.90,
        "is_melee": False,
        "mobility": 0.82,
        "view_pos": (0.31, -0.26, 0.66),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.86,
    },
    "p90": {
        "display_name": "FN P90",
        "slot": 1,
        "category": "primary",
        "price": 2350,
        "kill_reward": 300,
        "model_path": "assets/models/p90.glb",
        "shoot_sound": "p90_shoot",
        "silenced": False,
        "damage": 26,
        "headshot_mult": 3.2,
        "pellets": 1,
        "fire_interval": 0.070,
        "automatic": True,
        "supports_burst": False,
        "scope_fovs": [66.0],
        "mag_size": 50,
        "reserve_max": 100,
        "reload_time": 2.45,
        "base_spread": 0.015,
        "move_spread": 0.020,
        "jump_spread": 0.068,
        "recoil_pitch": 0.90,
        "recoil_yaw": 0.52,
        "range": 105.0,
        "falloff": 0.968,
        "penetration": 0.50,
        "is_melee": False,
        "mobility": 1.01,
        "view_pos": (0.29, -0.25, 0.56),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.78,
    },
    "mp9": {
        "display_name": "MP9 Tactical",
        "slot": 1,
        "category": "primary",
        "price": 1250,
        "kill_reward": 600,
        "model_path": "assets/models/mp9.glb",
        "shoot_sound": "mp9_shoot",
        "silenced": False,
        "damage": 24,
        "headshot_mult": 3.3,
        "pellets": 1,
        "fire_interval": 0.072,
        "automatic": True,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": 30,
        "reserve_max": 120,
        "reload_time": 1.85,
        "base_spread": 0.015,
        "move_spread": 0.022,
        "jump_spread": 0.065,
        "recoil_pitch": 0.92,
        "recoil_yaw": 0.48,
        "range": 95.0,
        "falloff": 0.96,
        "penetration": 0.35,
        "is_melee": False,
        "mobility": 1.02,
        "view_pos": (0.29, -0.25, 0.55),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.72,
    },
    "shotgun": {
        "display_name": "XM1014 Auto",
        "slot": 1,
        "category": "primary",
        "price": 2000,
        "kill_reward": 900,
        "model_path": "assets/models/shotgun.glb",
        "shoot_sound": "shotgun_shoot",
        "silenced": False,
        "damage": 18,
        "headshot_mult": 2.4,
        "pellets": 8,
        "fire_interval": 0.34,
        "automatic": True,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": 7,
        "reserve_max": 32,
        "reload_time": 2.35,
        "base_spread": 0.052,
        "move_spread": 0.022,
        "jump_spread": 0.055,
        "recoil_pitch": 3.20,
        "recoil_yaw": 0.80,
        "range": 48.0,
        "falloff": 0.92,
        "penetration": 0.20,
        "is_melee": False,
        "mobility": 0.93,
        "view_pos": (0.30, -0.27, 0.62),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.80,
    },
    "famas": {
        "display_name": "FAMAS F1",
        "slot": 1,
        "category": "primary",
        "price": 2050,
        "kill_reward": 300,
        "model_path": "assets/models/famas.glb",
        "shoot_sound": "famas_shoot",
        "silenced": False,
        "damage": 30,
        "headshot_mult": 3.4,
        "pellets": 1,
        "fire_interval": 0.092,
        "automatic": True,
        "supports_burst": True,
        "scope_fovs": [],
        "mag_size": 25,
        "reserve_max": 90,
        "reload_time": 2.15,
        "base_spread": 0.010,
        "move_spread": 0.034,
        "jump_spread": 0.095,
        "recoil_pitch": 1.25,
        "recoil_yaw": 0.50,
        "range": 130.0,
        "falloff": 0.98,
        "penetration": 0.58,
        "is_melee": False,
        "mobility": 0.96,
        "view_pos": (0.30, -0.26, 0.60),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.78,
    },
    "usp": {
        "display_name": "USP-S",
        "slot": 2,
        "category": "secondary",
        "price": 200,
        "kill_reward": 300,
        "model_path": "assets/models/usp.glb",
        "shoot_sound": "usp_shoot",
        "silenced": True,
        "damage": 35,
        "headshot_mult": 3.5,
        "pellets": 1,
        "fire_interval": 0.17,
        "automatic": False,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": 12,
        "reserve_max": 36,
        "reload_time": 1.70,
        "base_spread": 0.007,
        "move_spread": 0.022,
        "jump_spread": 0.070,
        "recoil_pitch": 1.25,
        "recoil_yaw": 0.35,
        "range": 105.0,
        "falloff": 0.96,
        "penetration": 0.38,
        "is_melee": False,
        "mobility": 1.00,
        "view_pos": (0.27, -0.24, 0.54),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.68,
    },
    "deagle": {
        "display_name": "Desert Eagle",
        "slot": 2,
        "category": "secondary",
        "price": 700,
        "kill_reward": 300,
        "model_path": "assets/models/deagle.glb",
        "shoot_sound": "deagle_shoot",
        "silenced": False,
        "damage": 58,
        "headshot_mult": 3.8,
        "pellets": 1,
        "fire_interval": 0.28,
        "automatic": False,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": 7,
        "reserve_max": 35,
        "reload_time": 1.90,
        "base_spread": 0.008,
        "move_spread": 0.036,
        "jump_spread": 0.095,
        "recoil_pitch": 3.60,
        "recoil_yaw": 0.70,
        "range": 120.0,
        "falloff": 0.97,
        "penetration": 0.72,
        "is_melee": False,
        "mobility": 0.98,
        "view_pos": (0.28, -0.25, 0.54),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.68,
    },
    "glock": {
        "display_name": "Glock-18",
        "slot": 2,
        "category": "secondary",
        "price": 200,
        "kill_reward": 300,
        "model_path": "assets/models/glock.glb",
        "shoot_sound": "glock_shoot",
        "silenced": False,
        "damage": 28,
        "headshot_mult": 3.4,
        "pellets": 1,
        "fire_interval": 0.14,
        "automatic": False,
        "supports_burst": True,
        "scope_fovs": [],
        "mag_size": 20,
        "reserve_max": 120,
        "reload_time": 1.65,
        "base_spread": 0.011,
        "move_spread": 0.022,
        "jump_spread": 0.068,
        "recoil_pitch": 1.05,
        "recoil_yaw": 0.42,
        "range": 95.0,
        "falloff": 0.95,
        "penetration": 0.32,
        "is_melee": False,
        "mobility": 1.02,
        "view_pos": (0.27, -0.24, 0.52),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.66,
    },
    "zeus": {
        "display_name": "Zeus x27 Taser",
        "slot": 3,
        "category": "utility",
        "price": 200,
        "kill_reward": 100,
        "model_path": "assets/models/zeus.glb",
        "shoot_sound": "zeus_zap",
        "silenced": False,
        "damage": 260,
        "headshot_mult": 1.2,
        "pellets": 1,
        "fire_interval": 0.85,
        "automatic": False,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": 2,
        "reserve_max": 4,
        "reload_time": 2.40,
        "base_spread": 0.002,
        "move_spread": 0.006,
        "jump_spread": 0.020,
        "recoil_pitch": 1.50,
        "recoil_yaw": 0.30,
        "range": 7.8,
        "falloff": 1.0,
        "penetration": 0.0,
        "is_melee": False,
        "is_zeus": True,
        "mobility": 1.05,
        "view_pos": (0.27, -0.24, 0.50),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.68,
    },
    "knife": {
        "display_name": "Karambit Doppler",
        "slot": 3,
        "category": "melee",
        "price": 0,
        "kill_reward": 1500,
        "model_path": "assets/models/knife.glb",
        "shoot_sound": "knife_slash",
        "silenced": True,
        "damage": 55,
        "heavy_damage": 90,
        "backstab_damage": 180,
        "headshot_mult": 1.5,
        "pellets": 1,
        "fire_interval": 0.42,
        "automatic": False,
        "supports_burst": False,
        "scope_fovs": [],
        "mag_size": -1,
        "reserve_max": -1,
        "reload_time": 0.0,
        "base_spread": 0.0,
        "move_spread": 0.0,
        "jump_spread": 0.0,
        "recoil_pitch": 0.0,
        "recoil_yaw": 0.0,
        "range": 2.85,
        "falloff": 1.0,
        "penetration": 0.0,
        "is_melee": True,
        "mobility": 1.12,
        "view_pos": (0.27, -0.24, 0.50),
        "view_rot": (0.0, 180.0, 0.0),
        "view_scale": 0.62,
    },
}

GRENADE_ORDER: list[str] = ["he", "flash", "smoke", "molotov"]

GRENADE_SPECS: dict[str, dict[str, Any]] = {
    "he": {"name": "HE Grenade", "short": "HE", "price": 300, "max_carry": 2, "fuse": 1.75, "color": (72, 98, 62)},
    "flash": {"name": "Flashbang", "short": "FLASH", "price": 200, "max_carry": 2, "fuse": 1.45, "color": (210, 218, 226)},
    "smoke": {"name": "Smoke Grenade", "short": "SMOKE", "price": 300, "max_carry": 1, "fuse": 1.80, "color": (118, 128, 138)},
    "molotov": {"name": "Molotov", "short": "MOLO", "price": 400, "max_carry": 1, "fuse": 2.40, "color": (215, 95, 35)},
}

BUY_ITEMS: list[dict[str, Any]] = [
    {"id": "ak47", "kind": "weapon", "label": "AK-47", "price": 2700},
    {"id": "m4a1", "kind": "weapon", "label": "M4A1-S", "price": 2900},
    {"id": "awp", "kind": "weapon", "label": "AWP Sniper", "price": 4750},
    {"id": "p90", "kind": "weapon", "label": "FN P90 (50 патр.)", "price": 2350},
    {"id": "shotgun", "kind": "weapon", "label": "XM1014 Shotgun", "price": 2000},
    {"id": "mp9", "kind": "weapon", "label": "MP9 Tactical", "price": 1250},
    {"id": "deagle", "kind": "weapon", "label": "Desert Eagle", "price": 700},
    {"id": "zeus", "kind": "weapon", "label": "Zeus x27 Шокер", "price": 200},
    {"id": "kevlar_helmet", "kind": "gear", "label": "Kevlar + Helmet", "price": 1000},
    {"id": "defuse_stim", "kind": "gear", "label": "Defuse + Stimshot", "price": 400},
    {"id": "he", "kind": "grenade", "label": "HE + Flashbang", "price": 400},
    {"id": "smoke", "kind": "grenade", "label": "Smoke + Molotov", "price": 600},
]
