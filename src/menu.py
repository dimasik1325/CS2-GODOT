"""
Киберспортивная система меню CS2 Panorama UI + Исправленные плавные ползунки PanoramaSlider:
- Собственный безотказный виджет PanoramaSlider (перетаскивание мышью, клик в любую точку шкалы,
  колесо мыши и кнопки [-] / [+]) — работает на 100% в полном экране и в окне на Ursina 7.x и 8.x!
- 3 вкладки настроек:
    1) ГРАФИКА (15 реальных настроек 3D-движка + пресеты LOW / MEDIUM / HIGH / ULTRA)
    2) ГЕЙМПЛЕЙ И ЗВУК (мышь, зум, громкость, боты, время раунда, сложность, режим игры)
    3) ПРИЦЕЛ, HUD И УПРАВЛЕНИЕ (размер/зазор/цвет/точка прицела, зум радара, телеметрия F3)
- Главное меню с карточкой ранга XP, выбором режима, витриной 3D-оперативника и кнопкой Заставки!
"""

from __future__ import annotations

from typing import Any, Callable

from ursina import Button, Entity, Text, application, camera, clamp, color, held_keys, mouse

from src.settings import (
    CROSSHAIR_PALETTE,
    WEAPON_SKINS,
    GameSettings,
    SoundManager,
    apply_fps_limit,
    apply_fullscreen_mode,
    load_safe_texture,
    resolve_font_path,
    rgb32,
    rgba32,
)


class PanoramaSlider:
    """
    Надёжный интерактивный ползунок CS2 Panorama UI без багов встроенного Ursina Draggable:
    поддерживает плавное перетаскивание мышью, мгновенный клик по шкале, прокрутку колесом и кнопки [-]/[+].
    """

    def __init__(
        self,
        parent_panel: Entity,
        label_text: str,
        pos_xy: tuple[float, float],
        min_val: float,
        max_val: float,
        default_val: float,
        step: float = 1.0,
        width: float = 0.28,
        fmt_pct: bool = False,
        suffix: str = "",
        font_path: str | None = None,
        on_change: Callable[[float], None] | None = None,
    ) -> None:
        self.parent_panel = parent_panel
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.step = float(step)
        self.fmt_pct = fmt_pct
        self.suffix = suffix
        self.on_change = on_change
        self.dragging: bool = False

        cx, cy = pos_xy
        self.track_cx = cx + 0.015
        self.track_cy = cy - 0.016
        self.track_width = width

        self.root = Entity(parent=parent_panel, z=-0.015, add_to_scene_entities=False)

        # Заголовок слева и живое числовое значение справа
        self.title_lbl = self._mk_text(label_text, (self.track_cx - width * 0.5, cy + 0.012, -0.01), 0.52, rgb32(214, 226, 244), origin=(-0.5, 0.0), font_path=font_path)
        self.val_lbl = self._mk_text("", (self.track_cx + width * 0.5, cy + 0.012, -0.01), 0.54, rgb32(255, 196, 62), origin=(0.5, 0.0), font_path=font_path)

        # Подложка дорожки ползунка
        self.track_bg = Entity(
            parent=self.root,
            model="quad",
            position=(self.track_cx, self.track_cy, 0.0),
            scale=(width, 0.014),
            color=rgba32(26, 36, 52, 245),
            add_to_scene_entities=False,
        )
        # Активная заполненная шкала
        self.fill_bar = Entity(
            parent=self.root,
            model="quad",
            origin=(-0.5, 0.0),
            position=(self.track_cx - width * 0.5, self.track_cy, -0.004),
            scale=(0.01, 0.014),
            color=rgb32(245, 174, 38),
            add_to_scene_entities=False,
        )
        # Светящийся бегунок
        self.knob = Entity(
            parent=self.root,
            model="quad",
            position=(self.track_cx, self.track_cy, -0.008),
            scale=(0.014, 0.026),
            color=rgb32(255, 232, 165),
            add_to_scene_entities=False,
        )

        # Кнопки точной подстройки [-] и [+]
        btn_step = self.step if self.step > 0 else (self.max_val - self.min_val) * 0.05
        self.minus_btn = Button(
            parent=self.root,
            text="-",
            position=(self.track_cx - width * 0.5 - 0.024, self.track_cy, -0.006),
            scale=(0.028, 0.026),
            color=rgb32(34, 48, 68),
            highlight_color=rgb32(62, 92, 132),
            on_click=lambda: self.set_value(self.value - btn_step, notify=True),
        )
        self.plus_btn = Button(
            parent=self.root,
            text="+",
            position=(self.track_cx + width * 0.5 + 0.024, self.track_cy, -0.006),
            scale=(0.028, 0.026),
            color=rgb32(34, 48, 68),
            highlight_color=rgb32(62, 92, 132),
            on_click=lambda: self.set_value(self.value + btn_step, notify=True),
        )

        self.value: float = float(default_val)
        self.set_value(default_val, notify=False)

    def _mk_text(self, s: str, pos: tuple[float, float, float], sc: float, col: Any, origin: tuple[float, float], font_path: str | None) -> Text:
        kw: dict[str, Any] = {"parent": self.root, "text": s, "position": pos, "scale": sc, "color": col, "origin": origin}
        if font_path is not None:
            try:
                return Text(**kw, font=font_path)
            except Exception:
                return Text(**kw)
        return Text(**kw)

    def _is_Visible_in_hierarchy(self) -> bool:
        cur: Any = self.root
        while cur is not None and cur != camera.ui:
            if not getattr(cur, "enabled", True):
                return False
            cur = getattr(cur, "parent", None)
        return True

    def is_mouse_over_track(self) -> bool:
        mx, my = float(mouse.x), float(mouse.y)
        return (
            abs(mx - self.track_cx) <= (self.track_width * 0.5 + 0.012)
            and abs(my - self.track_cy) <= 0.020
        )

    def set_value(self, raw_val: float, notify: bool = True) -> None:
        v = clamp(float(raw_val), self.min_val, self.max_val)
        if self.step > 0:
            steps = round((v - self.min_val) / self.step)
            v = clamp(self.min_val + steps * self.step, self.min_val, self.max_val)
        self.value = v

        ratio = (v - self.min_val) / max(1e-6, self.max_val - self.min_val)
        left_x = self.track_cx - self.track_width * 0.5
        self.fill_bar.scale_x = max(0.002, self.track_width * ratio)
        self.knob.x = left_x + self.track_width * ratio

        if self.fmt_pct:
            self.val_lbl.text = f"{int(round(v * 100))}%"
        elif self.step >= 1.0:
            self.val_lbl.text = f"{int(round(v))}{self.suffix}"
        else:
            self.val_lbl.text = f"{v:.2f}{self.suffix}"

        if notify and self.on_change is not None:
            self.on_change(self.value)

    def _set_from_mouse_x(self) -> None:
        left_x = self.track_cx - self.track_width * 0.5
        ratio = clamp((float(mouse.x) - left_x) / max(1e-5, self.track_width), 0.0, 1.0)
        new_v = self.min_val + ratio * (self.max_val - self.min_val)
        if abs(new_v - self.value) > 1e-5:
            self.set_value(new_v, notify=True)

    def handle_input(self, key: str) -> bool:
        if not self._is_Visible_in_hierarchy():
            self.dragging = False
            return False

        if key == "left mouse down" and self.is_mouse_over_track():
            self.dragging = True
            self.knob.color = rgb32(95, 232, 255)
            self._set_from_mouse_x()
            return True

        if key == "left mouse up" and self.dragging:
            self.dragging = False
            self.knob.color = rgb32(255, 232, 165)
            return True

        if key in ("scroll up", "scroll down") and self.is_mouse_over_track():
            delta = self.step if self.step > 0 else (self.max_val - self.min_val) * 0.05
            self.set_value(self.value + (delta if key == "scroll up" else -delta), notify=True)
            return True

        return False

    def update(self) -> None:
        if not self._is_Visible_in_hierarchy():
            self.dragging = False
            return
        if self.dragging:
            if not held_keys["left mouse"] and not getattr(mouse, "left", False):
                self.dragging = False
                self.knob.color = rgb32(255, 232, 165)
            else:
                self._set_from_mouse_x()
        else:
            hovered = self.is_mouse_over_track()
            self.track_bg.color = rgba32(42, 62, 88, 250) if hovered else rgba32(26, 36, 52, 245)


class MenuManager:
    """Управляет Panorama Главным меню, Меню паузы и 3-вкладочным окном Настроек (включая 15 настроек графики)."""

    SHOWCASE_WEAPONS = ("ak47", "m4a1", "awp", "p90", "deagle")

    def __init__(
        self,
        settings: GameSettings,
        sound_mgr: SoundManager,
        on_start_play: Callable[[], None],
        on_resume_play: Callable[[], None],
        on_restart_match: Callable[[], None],
        on_return_main_menu: Callable[[], None],
        on_settings_applied: Callable[[], None],
        on_replay_splash: Callable[[], None] | None = None,
        on_showcase_changed: Callable[[str, int], None] | None = None,
    ) -> None:
        self.settings = settings
        self.sound_mgr = sound_mgr
        self.on_start_play = on_start_play
        self.on_resume_play = on_resume_play
        self.on_restart_match = on_restart_match
        self.on_return_main_menu = on_return_main_menu
        self.on_settings_applied = on_settings_applied
        self.on_replay_splash = on_replay_splash
        self.on_showcase_changed = on_showcase_changed

        self._font = resolve_font_path("assets/fonts/hud_font.ttf")
        self._settings_return_target: str = "main"
        self._showcase_weapon_idx: int = 0
        self._sliders: list[PanoramaSlider] = []

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. PANORAMA ГЛАВНОЕ МЕНЮ (С 3D-ОПЕРАТИВНИКОМ НА ПОДИУМЕ!)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.main_panel = Entity(parent=camera.ui, enabled=False, add_to_scene_entities=False)
        bg_tex = load_safe_texture("assets/textures/menu_bg.png", repeat=False)
        Entity(
            parent=self.main_panel,
            model="quad",
            texture=bg_tex,
            scale=(2.0, 1.15),
            z=0.08,
            color=rgba32(255, 255, 255, 118) if bg_tex is not None else rgba32(10, 16, 26, 125),
            add_to_scene_entities=False,
        )

        # Верхняя киберспортивная шапка Panorama UI
        Entity(parent=self.main_panel, model="quad", position=(0.0, 0.455, 0.04), scale=(1.92, 0.085), color=rgba32(8, 13, 22, 236), add_to_scene_entities=False)
        Entity(parent=self.main_panel, model="quad", position=(0.0, 0.412, 0.035), scale=(1.92, 0.0035), color=rgb32(255, 184, 42), add_to_scene_entities=False)
        self._create_label(
            self.main_panel,
            "COUNTER-STRIKE 2   •   АЛКОДИМАС × УСАТЫЙ ЭЛЬДАР EDITION",
            pos=(-0.26, 0.455, 0.01),
            scale=0.88,
            col=rgb32(255, 194, 56),
        )
        self.profile_header_lbl = self._create_label(
            self.main_panel,
            "",
            pos=(0.52, 0.455, 0.01),
            scale=0.60,
            col=rgb32(98, 228, 255),
        )

        # Левая стеклянная панель навигации
        Entity(parent=self.main_panel, model="quad", position=(-0.50, -0.04, 0.05), scale=(0.62, 0.84), color=rgba32(9, 14, 24, 234), add_to_scene_entities=False)
        Entity(parent=self.main_panel, model="quad", position=(-0.19, -0.04, 0.045), scale=(0.004, 0.84), color=rgba32(65, 205, 255, 185), add_to_scene_entities=False)

        self._create_label(self.main_panel, "ТАКТИЧЕСКИЙ ЦЕНТР CS2", pos=(-0.50, 0.32, 0.01), scale=0.86, col=rgb32(235, 242, 255))
        self._create_label(self.main_panel, "3D REALISM  •  15 GRAPHICS  •  GPU BATCHED", pos=(-0.50, 0.275, 0.01), scale=0.48, col=rgb32(158, 182, 212))

        self._create_button(self.main_panel, "▶  НАЧАТЬ БОЙ (PLAY)", pos=(-0.50, 0.185, 0.01), scale_wh=(0.52, 0.072), accent=rgb32(235, 142, 26), on_click=self._handle_play_clicked)
        self._main_mode_btn = self._create_button(self.main_panel, "", pos=(-0.50, 0.095, 0.01), scale_wh=(0.52, 0.062), accent=rgb32(36, 68, 108), on_click=self._cycle_game_mode)
        self._create_button(self.main_panel, "⚙  НАСТРОЙКИ И ГРАФИКА (15)", pos=(-0.50, 0.010, 0.01), scale_wh=(0.52, 0.062), accent=rgb32(32, 48, 72), on_click=lambda: self.open_settings("main"))
        self._main_skin_btn = self._create_button(self.main_panel, "", pos=(-0.50, -0.075, 0.01), scale_wh=(0.52, 0.062), accent=rgb32(74, 52, 102), on_click=self._cycle_skin_clicked)
        self._main_wpn_btn = self._create_button(self.main_panel, "", pos=(-0.50, -0.160, 0.01), scale_wh=(0.52, 0.062), accent=rgb32(36, 72, 68), on_click=self._cycle_showcase_weapon)
        self._create_button(self.main_panel, "▶  ЗАСТАВКА (АЛКОДИМАС & ЭЛЬДАР)", pos=(-0.50, -0.245, 0.01), scale_wh=(0.52, 0.062), accent=rgb32(98, 68, 28), on_click=self._handle_replay_splash)
        self._create_button(self.main_panel, "✕  ВЫХОД НА РАБОЧИЙ СТОЛ", pos=(-0.50, -0.330, 0.01), scale_wh=(0.52, 0.062), accent=rgb32(138, 36, 40), on_click=self._handle_quit)

        # Нижняя правая полупрозрачная карточка витрины 3D-Оперативника и новых фич
        Entity(parent=self.main_panel, model="quad", position=(0.34, -0.33, 0.05), scale=(0.86, 0.22), color=rgba32(9, 14, 24, 214), add_to_scene_entities=False)
        Entity(parent=self.main_panel, model="quad", position=(0.34, -0.22, 0.045), scale=(0.86, 0.003), color=rgb32(255, 182, 42), add_to_scene_entities=False)
        self._create_label(
            self.main_panel,
            "НОВЫЕ КЛАВИШИ:  [F5] Вид от 3-го лица (модель игрока!)  |  [F8] Скин оружия  |  [C] Рация  |  [F3] Профайлер FPS\n"
            "[3 повторно] Электрошокер Zeus x27  |  [7] FN P90 (50 патр.)  |  [B] Закупка  |  [Shift+Ctrl] Подкат  |  [Q/E] Наклон",
            pos=(0.34, -0.33, 0.01),
            scale=0.50,
            col=rgb32(216, 228, 244),
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. МЕНЮ ПАУЗЫ (ESC)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.pause_panel = Entity(parent=camera.ui, enabled=False, add_to_scene_entities=False)
        Entity(parent=self.pause_panel, model="quad", scale=(2.2, 1.3), z=0.06, color=rgba32(6, 10, 16, 205), add_to_scene_entities=False)
        Entity(parent=self.pause_panel, model="quad", position=(0.0, 0.0, 0.04), scale=(0.60, 0.76), color=rgba32(12, 18, 28, 244), add_to_scene_entities=False)
        Entity(parent=self.pause_panel, model="quad", position=(0.0, 0.378, 0.035), scale=(0.60, 0.004), color=rgb32(255, 182, 42), add_to_scene_entities=False)
        self._create_label(self.pause_panel, "ПАУЗА  /  TACTICAL MENU", pos=(0.0, 0.29, 0.01), scale=1.25, col=rgb32(255, 192, 56))
        self._create_button(self.pause_panel, "▶  ПРОДОЛЖИТЬ БОЙ (ESC)", pos=(0.0, 0.16, 0.01), scale_wh=(0.48, 0.072), accent=rgb32(42, 118, 198), on_click=self._handle_resume_clicked)
        self._create_button(self.pause_panel, "⚙  НАСТРОЙКИ И ГРАФИКА (15)", pos=(0.0, 0.05, 0.01), scale_wh=(0.48, 0.070), accent=rgb32(34, 50, 74), on_click=lambda: self.open_settings("pause"))
        self._create_button(self.pause_panel, "↻  ПЕРЕЗАПУСТИТЬ МАТЧ", pos=(0.0, -0.06, 0.01), scale_wh=(0.48, 0.070), accent=rgb32(34, 50, 74), on_click=self._handle_restart_clicked)
        self._create_button(self.pause_panel, "⌂  В ГЛАВНОЕ МЕНЮ", pos=(0.0, -0.17, 0.01), scale_wh=(0.48, 0.070), accent=rgb32(94, 68, 30), on_click=self._handle_main_menu_clicked)
        self._create_button(self.pause_panel, "✕  ВЫЙТИ ИЗ ИГРЫ", pos=(0.0, -0.28, 0.01), scale_wh=(0.48, 0.070), accent=rgb32(138, 36, 40), on_click=self._handle_quit)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. 3-ВКЛАДОЧНОЕ ОКНО НАСТРОЕК PANORAMA (15 НАСТРОЕК ГРАФИКИ!)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.settings_panel = Entity(parent=camera.ui, enabled=False, add_to_scene_entities=False)
        Entity(parent=self.settings_panel, model="quad", scale=(2.2, 1.3), z=0.07, color=rgba32(6, 10, 18, 236), add_to_scene_entities=False)
        Entity(parent=self.settings_panel, model="quad", position=(0.0, 0.0, 0.05), scale=(1.46, 0.90), color=rgba32(11, 17, 28, 246), add_to_scene_entities=False)
        Entity(parent=self.settings_panel, model="quad", position=(0.0, 0.448, 0.045), scale=(1.46, 0.005), color=rgb32(255, 182, 42), add_to_scene_entities=False)

        # Кнопки переключения 3 вкладок настроек
        self.tab_btn_gfx = self._create_button(self.settings_panel, "1. ГРАФИКА (15 НАСТРОЕК)", pos=(-0.44, 0.39, 0.01), scale_wh=(0.42, 0.058), accent=rgb32(228, 138, 28), on_click=lambda: self.switch_settings_tab(0))
        self.tab_btn_game = self._create_button(self.settings_panel, "2. ГЕЙМПЛЕЙ И АУДИО", pos=(0.0, 0.39, 0.01), scale_wh=(0.42, 0.058), accent=rgb32(32, 48, 72), on_click=lambda: self.switch_settings_tab(1))
        self.tab_btn_hud = self._create_button(self.settings_panel, "3. ПРИЦЕЛ И ИНТЕРФЕЙС", pos=(0.44, 0.39, 0.01), scale_wh=(0.42, 0.058), accent=rgb32(32, 48, 72), on_click=lambda: self.switch_settings_tab(2))

        self.tab_gfx = Entity(parent=self.settings_panel, enabled=True, add_to_scene_entities=False)
        self.tab_game = Entity(parent=self.settings_panel, enabled=False, add_to_scene_entities=False)
        self.tab_hud = Entity(parent=self.settings_panel, enabled=False, add_to_scene_entities=False)

        # ── ВКЛАДКА 1: ВСЕ 15 НАСТРОЕК 3D-ГРАФИКИ ──
        # Левая колонка: 8 плавных ползунков PanoramaSlider (#1..#8)
        self.sl_fps = self._add_slider(self.tab_gfx, "1. Лимит кадров (FPS Limit)", (-0.38, 0.30), 30, 240, self.settings.fps_limit, step=5, suffix=" FPS", cb=self._on_gfx_slider)
        self.sl_fov = self._add_slider(self.tab_gfx, "2. Угол обзора 3D (FOV)", (-0.38, 0.21), 75, 115, self.settings.fov, step=1, suffix="°", cb=self._on_gfx_slider)
        self.sl_dist = self._add_slider(self.tab_gfx, "3. Дальность прорисовки 3D", (-0.38, 0.12), 65, 220, self.settings.render_distance, step=5, suffix=" м", cb=self._on_gfx_slider)
        self.sl_fog = self._add_slider(self.tab_gfx, "4. Плотность тумана (Fog)", (-0.38, 0.03), 0.0, 2.0, self.settings.fog_density, step=0.05, fmt_pct=True, cb=self._on_gfx_slider)
        self.sl_bright = self._add_slider(self.tab_gfx, "5. Яркость и экспозиция", (-0.38, -0.06), 0.60, 1.50, self.settings.brightness, step=0.05, fmt_pct=True, cb=self._on_gfx_slider)
        self.sl_part = self._add_slider(self.tab_gfx, "6. Плотность 3D-частиц", (-0.38, -0.15), 0.0, 1.50, self.settings.particles_quality, step=0.05, fmt_pct=True, cb=self._on_gfx_slider)
        self.sl_decal = self._add_slider(self.tab_gfx, "7. Пул декалей и 3D-гильз", (-0.38, -0.24), 0, 80, self.settings.decal_shell_limit, step=4, suffix=" шт", cb=self._on_gfx_slider)
        self.sl_aniso = self._add_slider(self.tab_gfx, "8. Анизотропная фильтрация", (-0.38, -0.33), 1, 16, self.settings.anisotropic_level, step=1, suffix="x", cb=self._on_gfx_slider)

        # Правая колонка: 7 переключателей 3D-рендера (#9..#15)
        self.btn_preset = self._create_button(self.tab_gfx, "", pos=(0.35, 0.29, -0.01), scale_wh=(0.56, 0.058), accent=rgb32(182, 108, 24), on_click=self._cycle_preset)
        self.btn_fs = self._create_button(self.tab_gfx, "", pos=(0.35, 0.21, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(36, 78, 72), on_click=self._toggle_fullscreen_clicked)
        self.btn_vsync = self._create_button(self.tab_gfx, "", pos=(0.35, 0.13, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(38, 56, 86), on_click=self._toggle_vsync)
        self.btn_shadows = self._create_button(self.tab_gfx, "", pos=(0.35, 0.05, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(44, 62, 92), on_click=self._cycle_shadow_quality)
        self.btn_shader = self._create_button(self.tab_gfx, "", pos=(0.35, -0.03, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(68, 52, 98), on_click=self._cycle_shader_quality)
        self.btn_dynlight = self._create_button(self.tab_gfx, "", pos=(0.35, -0.11, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(44, 68, 86), on_click=self._toggle_dyn_lights)
        self.btn_tod = self._create_button(self.tab_gfx, "", pos=(0.35, -0.19, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(78, 58, 96), on_click=self._toggle_sky_clicked)
        self.btn_sky_det = self._create_button(self.tab_gfx, "", pos=(0.35, -0.27, -0.01), scale_wh=(0.56, 0.056), accent=rgb32(38, 68, 64), on_click=self._toggle_sky_details)

        # ── ВКЛАДКА 2: ГЕЙМПЛЕЙ И АУДИО ──
        self.sl_sens = self._add_slider(self.tab_game, "Чувствительность мыши", (-0.38, 0.25), 8, 140, self.settings.mouse_sensitivity, step=1.0, cb=self._on_game_slider)
        self.sl_zoom_sens = self._add_slider(self.tab_game, "Множитель зума в прицеле AWP", (-0.38, 0.14), 0.25, 1.20, self.settings.zoom_sensitivity, step=0.05, fmt_pct=True, cb=self._on_game_slider)
        self.sl_vol = self._add_slider(self.tab_game, "Общая громкость звуков", (-0.38, 0.03), 0.0, 1.0, self.settings.master_volume, step=0.05, fmt_pct=True, cb=self._on_game_slider)
        self.sl_music = self._add_slider(self.tab_game, "Громкость музыки в меню", (-0.38, -0.08), 0.0, 1.0, self.settings.music_volume, step=0.05, fmt_pct=True, cb=self._on_game_slider)
        self.sl_bots = self._add_slider(self.tab_game, "Количество ботов в раунде", (-0.38, -0.19), 1, 10, self.settings.bot_count, step=1, suffix=" бот.", cb=self._on_game_slider)
        self.sl_rtime = self._add_slider(self.tab_game, "Время раунда (секунд)", (-0.38, -0.30), 45, 240, self.settings.round_time_seconds, step=5, suffix=" с", cb=self._on_game_slider)

        self.btn_diff = self._create_button(self.tab_game, "", pos=(0.35, 0.20, -0.01), scale_wh=(0.56, 0.068), accent=rgb32(104, 54, 42), on_click=self._toggle_difficulty_clicked)
        self.btn_mode_s = self._create_button(self.tab_game, "", pos=(0.35, 0.09, -0.01), scale_wh=(0.56, 0.068), accent=rgb32(38, 72, 112), on_click=self._cycle_game_mode)
        self.btn_skin_s = self._create_button(self.tab_game, "", pos=(0.35, -0.02, -0.01), scale_wh=(0.56, 0.068), accent=rgb32(82, 54, 110), on_click=self._cycle_skin_clicked)

        # ── ВКЛАДКА 3: ПРИЦЕЛ, РАДАР И ИНТЕРФЕЙС ──
        self.sl_ch_size = self._add_slider(self.tab_hud, "Размер рисок прицела", (-0.38, 0.24), 0.50, 2.00, self.settings.crosshair_size, step=0.05, fmt_pct=True, cb=self._on_hud_slider)
        self.sl_ch_gap = self._add_slider(self.tab_hud, "Центральный зазор прицела", (-0.38, 0.12), 0.50, 2.00, self.settings.crosshair_gap, step=0.05, fmt_pct=True, cb=self._on_hud_slider)
        self.sl_radar = self._add_slider(self.tab_hud, "Масштаб 2D тактического радара", (-0.38, 0.00), 0.60, 1.60, self.settings.radar_zoom, step=0.05, fmt_pct=True, cb=self._on_hud_slider)

        self.btn_ch_col = self._create_button(self.tab_hud, "", pos=(0.35, 0.23, -0.01), scale_wh=(0.56, 0.064), accent=rgb32(38, 86, 68), on_click=self._cycle_crosshair_col)
        self.btn_ch_dot = self._create_button(self.tab_hud, "", pos=(0.35, 0.13, -0.01), scale_wh=(0.56, 0.064), accent=rgb32(42, 62, 88), on_click=self._toggle_ch_dot)
        self.btn_dmg_num = self._create_button(self.tab_hud, "", pos=(0.35, 0.03, -0.01), scale_wh=(0.56, 0.064), accent=rgb32(72, 58, 92), on_click=self._toggle_dmg_num)
        self.btn_fps_tel = self._create_button(self.tab_hud, "", pos=(0.35, -0.07, -0.01), scale_wh=(0.56, 0.064), accent=rgb32(36, 76, 86), on_click=self._toggle_fps_tel)

        self._create_label(
            self.tab_hud,
            "СОВЕТ: Ползунки можно плавно тянуть зажатой ЛКМ, кликать в любое место шкалы, крутить колесом мыши или жать [-] / [+]!",
            pos=(0.0, -0.26, -0.01),
            scale=0.52,
            col=rgb32(255, 204, 88),
        )

        # Нижняя кнопка сохранения настроек
        self._create_button(
            self.settings_panel,
            "✓  СОХРАНИТЬ И ПРИМЕНИТЬ  (ESC)",
            pos=(0.0, -0.395, 0.01),
            scale_wh=(0.52, 0.066),
            accent=rgb32(232, 142, 28),
            on_click=self.close_settings,
        )

        self.refresh_toggle_labels()

    def _add_slider(
        self,
        tab_parent: Entity,
        label: str,
        pos_xy: tuple[float, float],
        min_v: float,
        max_v: float,
        default_v: float,
        step: float = 1.0,
        fmt_pct: bool = False,
        suffix: str = "",
        cb: Callable[[float], None] | None = None,
    ) -> PanoramaSlider:
        sl = PanoramaSlider(
            parent_panel=tab_parent,
            label_text=label,
            pos_xy=pos_xy,
            min_val=min_v,
            max_val=max_v,
            default_val=default_v,
            step=step,
            width=0.40,
            fmt_pct=fmt_pct,
            suffix=suffix,
            font_path=self._font,
            on_change=cb,
        )
        self._sliders.append(sl)
        return sl

    def switch_settings_tab(self, tab_idx: int) -> None:
        self.tab_gfx.enabled = tab_idx == 0
        self.tab_game.enabled = tab_idx == 1
        self.tab_hud.enabled = tab_idx == 2
        active_c = rgb32(232, 142, 28)
        idle_c = rgb32(32, 48, 72)
        self.tab_btn_gfx.color = active_c if tab_idx == 0 else idle_c
        self.tab_btn_game.color = active_c if tab_idx == 1 else idle_c
        self.tab_btn_hud.color = active_c if tab_idx == 2 else idle_c
        self.sound_mgr.play_sfx("empty_click", volume=0.45, pitch=1.18)

    def _sync_sliders_from_settings(self) -> None:
        self.sl_fps.set_value(self.settings.fps_limit, notify=False)
        self.sl_fov.set_value(self.settings.fov, notify=False)
        self.sl_dist.set_value(self.settings.render_distance, notify=False)
        self.sl_fog.set_value(self.settings.fog_density, notify=False)
        self.sl_bright.set_value(self.settings.brightness, notify=False)
        self.sl_part.set_value(self.settings.particles_quality, notify=False)
        self.sl_decal.set_value(self.settings.decal_shell_limit, notify=False)
        self.sl_aniso.set_value(self.settings.anisotropic_level, notify=False)

        self.sl_sens.set_value(self.settings.mouse_sensitivity, notify=False)
        self.sl_zoom_sens.set_value(self.settings.zoom_sensitivity, notify=False)
        self.sl_vol.set_value(self.settings.master_volume, notify=False)
        self.sl_music.set_value(self.settings.music_volume, notify=False)
        self.sl_bots.set_value(self.settings.bot_count, notify=False)
        self.sl_rtime.set_value(self.settings.round_time_seconds, notify=False)

        self.sl_ch_size.set_value(self.settings.crosshair_size, notify=False)
        self.sl_ch_gap.set_value(self.settings.crosshair_gap, notify=False)
        self.sl_radar.set_value(self.settings.radar_zoom, notify=False)

    def refresh_toggle_labels(self) -> None:
        s = self.settings
        self.profile_header_lbl.text = (
            f"ЗВАНИЕ: {s.get_rank_title()}  •  XP: {s.player_xp}  •  ПОБЕД: {s.matches_won}  •  КИЛЛОВ: {s.total_career_kills}"
        )

        mode_names = {
            "CLASSIC": "КЛАССИКА БОМБА C4",
            "DEATHMATCH": "МЯСОРУБКА DEATHMATCH",
            "HEADSHOT_ONLY": "ТОЛЬКО ХЕДШОТЫ",
            "BOSS_ELDAR": "ОХОТА НА УСАТОГО ЭЛЬДАРА",
        }
        m_lbl = f"РЕЖИМ: {mode_names.get(s.game_mode, s.game_mode)}"
        self._main_mode_btn.text = m_lbl
        self.btn_mode_s.text = m_lbl

        skin_name = WEAPON_SKINS[s.weapon_skin_idx % len(WEAPON_SKINS)]["name"]
        self._main_skin_btn.text = f"СКИН: {skin_name} (F8)"
        self.btn_skin_s.text = f"3D СКИН ОРУЖИЯ: {skin_name}"

        wpn_id = self.SHOWCASE_WEAPONS[self._showcase_weapon_idx % len(self.SHOWCASE_WEAPONS)].upper()
        self._main_wpn_btn.text = f"ОРУЖИЕ АГЕНТА: {wpn_id}"

        # 7 кнопок правой колонки вкладки ГРАФИКА (#9..#15)
        self.btn_preset.text = f"9. ПРЕСЕТ КАЧЕСТВА: {s.graphics_preset}"
        self.btn_fs.text = f"10. ПОЛНЫЙ ЭКРАН: {'ВКЛ' if s.fullscreen else 'ВЫКЛ'} (F11)"
        self.btn_vsync.text = f"11. ВЕРТИК. СИНХР. VSYNC: {'ВКЛ' if s.vsync_enabled else 'ВЫКЛ'}"
        sh_str = "ВЫКЛ (FPS+)" if s.shadow_quality <= 0 else f"{s.shadow_quality}×{s.shadow_quality} px"
        self.btn_shadows.text = f"12. ТЕНИ 3D: {sh_str}"
        self.btn_shader.text = f"13. ШЕЙДЕРЫ И PBR: {s.shader_quality}"
        self.btn_dynlight.text = f"14. ДИНАМИЧ. СВЕТ ВЫСТРЕЛОВ: {'ВКЛ' if s.dynamic_lights else 'ВЫКЛ'}"
        self.btn_tod.text = f"15. ВРЕМЯ СУТОК: {s.time_of_day} (F6)"
        self.btn_sky_det.text = f"ОБЛАКА И ВЕТЕР ПАЛЬМ: {'ВКЛ' if s.sky_details else 'ВЫКЛ'}"

        self.btn_diff.text = f"СЛОЖНОСТЬ ИИ БОТОВ: {s.bot_difficulty}"
        ch_name = CROSSHAIR_PALETTE[s.crosshair_color_idx % len(CROSSHAIR_PALETTE)][0]
        self.btn_ch_col.text = f"ЦВЕТ ПРИЦЕЛА: {ch_name} (F7)"
        self.btn_ch_dot.text = f"ТОЧКА ПРИЦЕЛА: {'ВКЛ' if s.crosshair_dot else 'ВЫКЛ'}"
        self.btn_dmg_num.text = f"3D ЦИФРЫ УРОНА: {'ВКЛ' if s.show_damage_numbers else 'ВЫКЛ'}"
        self.btn_fps_tel.text = f"ПРОФАЙЛЕР FPS И ПУЛОВ (F3): {'ВКЛ' if s.show_fps_telemetry else 'ВЫКЛ'}"

    # ── ОБРАБОТЧИКИ ИЗМЕНЕНИЯ ПОЛЗУНКОВ И ПЕРЕКЛЮЧАТЕЛЕЙ ──
    def _on_gfx_slider(self, _: float) -> None:
        s = self.settings
        s.graphics_preset = "CUSTOM"
        s.fps_limit = int(round(self.sl_fps.value))
        s.fov = float(self.sl_fov.value)
        s.render_distance = float(self.sl_dist.value)
        s.fog_density = float(self.sl_fog.value)
        s.brightness = float(self.sl_bright.value)
        s.particles_quality = float(self.sl_part.value)
        s.decal_shell_limit = int(round(self.sl_decal.value))
        s.anisotropic_level = int(round(self.sl_aniso.value))
        apply_fps_limit(s.fps_limit, s.vsync_enabled)
        self.refresh_toggle_labels()
        self.on_settings_applied()

    def _on_game_slider(self, _: float) -> None:
        s = self.settings
        s.mouse_sensitivity = float(self.sl_sens.value)
        s.zoom_sensitivity = float(self.sl_zoom_sens.value)
        s.master_volume = float(self.sl_vol.value)
        s.music_volume = float(self.sl_music.value)
        s.bot_count = int(round(self.sl_bots.value))
        s.round_time_seconds = int(round(self.sl_rtime.value))
        self.sound_mgr.set_volumes(s.master_volume, s.music_volume)
        self.on_settings_applied()

    def _on_hud_slider(self, _: float) -> None:
        s = self.settings
        s.crosshair_size = float(self.sl_ch_size.value)
        s.crosshair_gap = float(self.sl_ch_gap.value)
        s.radar_zoom = float(self.sl_radar.value)
        self.on_settings_applied()

    def _cycle_preset(self) -> None:
        order = ("LOW", "MEDIUM", "HIGH", "ULTRA")
        cur = self.settings.graphics_preset if self.settings.graphics_preset in order else "HIGH"
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.settings.apply_preset_values(nxt)
        self._sync_sliders_from_settings()
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("buy_item", volume=0.55)

    def _toggle_fullscreen_clicked(self) -> None:
        self.settings.fullscreen = not self.settings.fullscreen
        apply_fullscreen_mode(self.settings.fullscreen, self.settings.vsync_enabled)
        self.refresh_toggle_labels()
        self.settings.save()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_vsync(self) -> None:
        self.settings.vsync_enabled = not self.settings.vsync_enabled
        apply_fullscreen_mode(self.settings.fullscreen, self.settings.vsync_enabled)
        apply_fps_limit(self.settings.fps_limit, self.settings.vsync_enabled)
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _cycle_shadow_quality(self) -> None:
        order = (0, 512, 1024, 2048, 4096)
        cur = self.settings.shadow_quality if self.settings.shadow_quality in order else 2048
        self.settings.shadow_quality = order[(order.index(cur) + 1) % len(order)]
        self.settings.shadows_enabled = self.settings.shadow_quality > 0
        self.settings.graphics_preset = "CUSTOM"
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _cycle_shader_quality(self) -> None:
        order = ("FLAT", "LIT", "PBR")
        cur = self.settings.shader_quality if self.settings.shader_quality in order else "PBR"
        self.settings.shader_quality = order[(order.index(cur) + 1) % len(order)]
        self.settings.graphics_preset = "CUSTOM"
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_dyn_lights(self) -> None:
        self.settings.dynamic_lights = not self.settings.dynamic_lights
        self.settings.graphics_preset = "CUSTOM"
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_sky_clicked(self) -> None:
        order = ("DAY", "SUNSET", "NIGHT", "OVERCAST")
        cur = self.settings.time_of_day if self.settings.time_of_day in order else "DAY"
        self.settings.time_of_day = order[(order.index(cur) + 1) % len(order)]
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_sky_details(self) -> None:
        self.settings.sky_details = not self.settings.sky_details
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_difficulty_clicked(self) -> None:
        order = ("EASY", "NORMAL", "HARD")
        self.settings.bot_difficulty = order[(order.index(self.settings.bot_difficulty) + 1) % len(order)]
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _cycle_game_mode(self) -> None:
        order = ("CLASSIC", "DEATHMATCH", "HEADSHOT_ONLY", "BOSS_ELDAR")
        cur = self.settings.game_mode if self.settings.game_mode in order else "CLASSIC"
        self.settings.game_mode = order[(order.index(cur) + 1) % len(order)]
        self.refresh_toggle_labels()
        self.settings.save()
        self.sound_mgr.play_sfx("buy_item", volume=0.55)

    def _cycle_skin_clicked(self) -> None:
        self.settings.weapon_skin_idx = (self.settings.weapon_skin_idx + 1) % len(WEAPON_SKINS)
        self.refresh_toggle_labels()
        self.on_settings_applied()
        if self.on_showcase_changed is not None:
            wid = self.SHOWCASE_WEAPONS[self._showcase_weapon_idx % len(self.SHOWCASE_WEAPONS)]
            self.on_showcase_changed(wid, self.settings.weapon_skin_idx)
        self.sound_mgr.play_sfx("buy_item", volume=0.55)

    def _cycle_showcase_weapon(self) -> None:
        self._showcase_weapon_idx = (self._showcase_weapon_idx + 1) % len(self.SHOWCASE_WEAPONS)
        self.refresh_toggle_labels()
        if self.on_showcase_changed is not None:
            wid = self.SHOWCASE_WEAPONS[self._showcase_weapon_idx % len(self.SHOWCASE_WEAPONS)]
            self.on_showcase_changed(wid, self.settings.weapon_skin_idx)
        self.sound_mgr.play_sfx("empty_click", volume=0.55, pitch=1.18)

    def _cycle_crosshair_col(self) -> None:
        self.settings.crosshair_color_idx = (self.settings.crosshair_color_idx + 1) % len(CROSSHAIR_PALETTE)
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_ch_dot(self) -> None:
        self.settings.crosshair_dot = not self.settings.crosshair_dot
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_dmg_num(self) -> None:
        self.settings.show_damage_numbers = not self.settings.show_damage_numbers
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_fps_tel(self) -> None:
        self.settings.show_fps_telemetry = not self.settings.show_fps_telemetry
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _handle_replay_splash(self) -> None:
        if self.on_replay_splash is not None:
            self.hide_all()
            self.on_replay_splash()

    def _create_label(self, parent_ent: Entity, content: str, pos: tuple[float, float, float], scale: float = 1.0, col: Any = color.white) -> Text:
        kwargs: dict[str, Any] = {"parent": parent_ent, "text": content, "origin": (0.0, 0.0), "position": pos, "scale": scale, "color": col}
        if self._font is not None:
            try:
                return Text(**kwargs, font=self._font)
            except Exception:
                return Text(**kwargs)
        return Text(**kwargs)

    def _create_button(self, parent_ent: Entity, title: str, pos: tuple[float, float, float], scale_wh: tuple[float, float], accent: Any, on_click: Callable[[], None]) -> Button:
        btn = Button(
            parent=parent_ent,
            text=title,
            position=pos,
            scale=scale_wh,
            color=accent,
            highlight_color=accent.tint(0.18),
            pressed_color=accent.tint(-0.15),
            on_click=on_click,
        )
        if self._font is not None and btn.text_entity is not None:
            try:
                btn.text_entity.font = self._font
            except Exception:
                pass
            btn.text_entity.scale *= 0.76
        return btn

    def show_main_menu(self) -> None:
        self.pause_panel.enabled = False
        self.settings_panel.enabled = False
        self.refresh_toggle_labels()
        self.main_panel.enabled = True
        mouse.locked = False
        mouse.visible = True
        self.sound_mgr.play_menu_music("menu_music")

    def hide_all(self) -> None:
        self.main_panel.enabled = False
        self.pause_panel.enabled = False
        self.settings_panel.enabled = False

    def show_pause_menu(self) -> None:
        self.main_panel.enabled = False
        self.settings_panel.enabled = False
        self.pause_panel.enabled = True
        mouse.locked = False
        mouse.visible = True

    def open_settings(self, return_to: str = "main") -> None:
        self._settings_return_target = return_to
        self.sound_mgr.play_sfx("empty_click", volume=0.5)
        self.main_panel.enabled = False
        self.pause_panel.enabled = False
        self._sync_sliders_from_settings()
        self.refresh_toggle_labels()
        self.settings_panel.enabled = True

    def close_settings(self) -> None:
        self.settings.save()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)
        self.settings_panel.enabled = False
        if self._settings_return_target == "pause":
            self.pause_panel.enabled = True
        else:
            self.main_panel.enabled = True

    def handle_input(self, key: str) -> bool:
        if not self.settings_panel.enabled:
            return False
        for sl in self._sliders:
            if sl.handle_input(key):
                return True
        return False

    def update(self) -> None:
        if not self.settings_panel.enabled:
            return
        for sl in self._sliders:
            sl.update()

    def _handle_play_clicked(self) -> None:
        self.sound_mgr.play_sfx("reload", volume=0.65)
        self.sound_mgr.stop_menu_music()
        self.hide_all()
        self.on_start_play()

    def _handle_resume_clicked(self) -> None:
        self.sound_mgr.play_sfx("empty_click", volume=0.5)
        self.hide_all()
        self.on_resume_play()

    def _handle_restart_clicked(self) -> None:
        self.sound_mgr.play_sfx("reload", volume=0.65)
        self.hide_all()
        self.on_restart_match()

    def _handle_main_menu_clicked(self) -> None:
        self.sound_mgr.play_sfx("empty_click", volume=0.5)
        self.on_return_main_menu()

    def _handle_quit(self) -> None:
        self.settings.save()
        application.quit()
