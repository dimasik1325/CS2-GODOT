"""
Система экранов меню игры (CS2 Tactical Realism Edition):
1) Главное меню с живой панорамой 3D-арены на фоне, музыкой и карточкой всех новых клавиш
2) Меню паузы по клавише Esc
3) Расширенное окно настроек: Полноэкранный режим (Fullscreen F11), Время суток (Day/Sunset/Night F6),
   Сложность ИИ (Easy/Normal/Hard), Тени 3D, FOV, Чувствительность мыши, Громкость и Количество ботов
"""

from __future__ import annotations

from typing import Any, Callable

from ursina import Button, Entity, Slider, Text, application, camera, color, mouse

from src.settings import (
    GameSettings,
    SoundManager,
    apply_fullscreen_mode,
    load_safe_texture,
    resolve_font_path,
    rgb32,
    rgba32,
)


class MenuManager:
    """Управляет Главным меню, Меню паузы и Расширенным окном настроек."""

    def __init__(
        self,
        settings: GameSettings,
        sound_mgr: SoundManager,
        on_start_play: Callable[[], None],
        on_resume_play: Callable[[], None],
        on_restart_match: Callable[[], None],
        on_return_main_menu: Callable[[], None],
        on_settings_applied: Callable[[], None],
    ) -> None:
        self.settings = settings
        self.sound_mgr = sound_mgr
        self.on_start_play = on_start_play
        self.on_resume_play = on_resume_play
        self.on_restart_match = on_restart_match
        self.on_return_main_menu = on_return_main_menu
        self.on_settings_applied = on_settings_applied

        self._font = resolve_font_path("assets/fonts/hud_font.ttf")
        self._settings_return_target: str = "main"

        # ── 1. ГЛАВНОЕ МЕНЮ (С ЖИВЫМ 3D-ОБЛЁТОМ КАРТЫ НА ФОНЕ!) ──
        self.main_panel = Entity(parent=camera.ui, enabled=False)
        bg_tex = load_safe_texture("assets/textures/menu_bg.png")
        Entity(
            parent=self.main_panel,
            model="quad",
            texture=bg_tex,
            scale=(2.0, 1.15),
            z=0.08,
            color=rgba32(255, 255, 255, 135) if bg_tex is not None else rgba32(14, 20, 30, 150),
        )
        Entity(
            parent=self.main_panel,
            model="quad",
            position=(-0.47, 0.0, 0.05),
            scale=(0.66, 1.15),
            color=rgba32(10, 14, 22, 232),
        )

        self._create_label(
            self.main_panel,
            "COUNTER-STRIKE 2",
            pos=(-0.47, 0.36, 0.02),
            scale=1.78,
            col=rgb32(245, 166, 35),
        )
        self._create_label(
            self.main_panel,
            "3D REALISM  •  100+ TACTICAL FEATURES EDITION",
            pos=(-0.47, 0.295, 0.02),
            scale=0.64,
            col=rgb32(185, 205, 230),
        )

        self._create_button(
            self.main_panel,
            "PLAY  /  НАЧАТЬ БОЙ",
            pos=(-0.47, 0.14, 0.01),
            accent=rgb32(228, 138, 28),
            on_click=self._handle_play_clicked,
        )
        self._create_button(
            self.main_panel,
            "SETTINGS  /  НАСТРОЙКИ",
            pos=(-0.47, 0.03, 0.01),
            accent=rgb32(36, 48, 66),
            on_click=lambda: self.open_settings("main"),
        )
        self._main_sky_btn = self._create_button(
            self.main_panel,
            f"SKY: {self.settings.time_of_day}  (F6)",
            pos=(-0.47, -0.08, 0.01),
            accent=rgb32(44, 68, 96),
            on_click=self._toggle_sky_clicked,
        )
        self._main_fs_btn = self._create_button(
            self.main_panel,
            self._fs_label(),
            pos=(-0.47, -0.19, 0.01),
            accent=rgb32(42, 78, 68),
            on_click=self._toggle_fullscreen_clicked,
        )
        self._create_button(
            self.main_panel,
            "QUIT  /  ВЫХОД",
            pos=(-0.47, -0.30, 0.01),
            accent=rgb32(138, 38, 38),
            on_click=self._handle_quit,
        )

        # Карточка полного тактического управления справа
        Entity(
            parent=self.main_panel,
            model="quad",
            position=(0.28, -0.01, 0.05),
            scale=(0.74, 0.78),
            color=rgba32(10, 15, 24, 212),
        )
        self._create_label(
            self.main_panel,
            "УПРАВЛЕНИЕ И НОВЫЕ ВОЗМОЖНОСТИ",
            pos=(0.28, 0.31, 0.02),
            scale=0.95,
            col=rgb32(245, 185, 65),
        )
        controls_lines = (
            "WASD — Движение  |  Shift — Спринт  |  Shift+Ctrl — ПОДКАТ!\n"
            "Q / E — Выглянуть из-за угла (Lean)  |  E у бомбы — Разминировать C4\n"
            "ЛКМ — Огонь  |  ПКМ — Прицел AWP / Режим Burst / Удар ножом в спину\n"
            "1 / 2 / 3 — Винтовка / Пистолет / Керамбит  |  6,7,8,9,0 — AWP, MP9, Дробовик, FAMAS, USP\n"
            "B — Меню закупки CS2 ($)  |  Tab — Таблица счёта и точности\n"
            "G — Бросить гранату (HE / Flash / Smoke / Molotov)  |  V — Сменить гранату\n"
            "F — Осмотр оружия в 3D  |  T — 3D Фонарь  |  X — Стимулятор +35 HP  |  Z — 3D Пинг\n"
            "F6 — День/Закат/Ночь  |  F7 — Цвет прицела  |  F11 — Полный экран  |  Esc — Пауза"
        )
        self._create_label(
            self.main_panel,
            controls_lines,
            pos=(0.28, -0.04, 0.02),
            scale=0.58,
            col=rgb32(220, 230, 244),
        )

        # ── 2. МЕНЮ ПАУЗЫ (ESC) ──
        self.pause_panel = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.pause_panel, model="quad", scale=(2.2, 1.3), z=0.06, color=rgba32(8, 12, 18, 198))
        Entity(parent=self.pause_panel, model="quad", position=(0.0, 0.0, 0.04), scale=(0.58, 0.76), color=rgba32(16, 22, 32, 240))
        self._create_label(self.pause_panel, "PAUSED  /  ПАУЗА", pos=(0.0, 0.29, 0.01), scale=1.42, col=rgb32(245, 175, 50))
        self._create_button(self.pause_panel, "RESUME  (ESC)", pos=(0.0, 0.16, 0.01), accent=rgb32(46, 122, 195), on_click=self._handle_resume_clicked)
        self._create_button(self.pause_panel, "SETTINGS  /  НАСТРОЙКИ", pos=(0.0, 0.05, 0.01), accent=rgb32(38, 48, 64), on_click=lambda: self.open_settings("pause"))
        self._create_button(self.pause_panel, "RESTART MATCH  /  ЗАНОВО", pos=(0.0, -0.06, 0.01), accent=rgb32(38, 48, 64), on_click=self._handle_restart_clicked)
        self._create_button(self.pause_panel, "MAIN MENU  /  В МЕНЮ", pos=(0.0, -0.17, 0.01), accent=rgb32(92, 68, 32), on_click=self._handle_main_menu_clicked)
        self._create_button(self.pause_panel, "QUIT  /  ВЫХОД", pos=(0.0, -0.28, 0.01), accent=rgb32(138, 38, 38), on_click=self._handle_quit)

        # ── 3. РАСШИРЕННАЯ ПАНЕЛЬ НАСТРОЕК ──
        self.settings_panel = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.settings_panel, model="quad", scale=(2.2, 1.3), z=0.07, color=rgba32(8, 12, 18, 228))
        Entity(parent=self.settings_panel, model="quad", position=(0.0, 0.0, 0.05), scale=(1.04, 0.84), color=rgba32(16, 22, 34, 244))
        self._create_label(self.settings_panel, "SETTINGS  /  НАСТРОЙКИ 3D И ИГРЫ", pos=(0.0, 0.34, 0.01), scale=1.28, col=rgb32(245, 175, 50))

        # Левая колонка ползунков
        self._create_label(self.settings_panel, "Mouse Sensitivity (Чувствительность):", pos=(-0.24, 0.23, 0.01), scale=0.68, col=rgb32(210, 220, 235))
        self.sens_slider = Slider(min=10, max=120, default=round(self.settings.mouse_sensitivity, 1), dynamic=True, parent=self.settings_panel, position=(-0.46, 0.185, 0.01), scale=0.85)
        self.sens_slider.on_value_changed = self._on_slider_changed

        self._create_label(self.settings_panel, "Master Volume (Общая громкость):", pos=(-0.24, 0.11, 0.01), scale=0.68, col=rgb32(210, 220, 235))
        self.vol_slider = Slider(min=0.0, max=1.0, default=round(self.settings.master_volume, 2), dynamic=True, parent=self.settings_panel, position=(-0.46, 0.065, 0.01), scale=0.85)
        self.vol_slider.on_value_changed = self._on_slider_changed

        self._create_label(self.settings_panel, "Bots per Round (Ботов в раунде):", pos=(-0.24, -0.01, 0.01), scale=0.68, col=rgb32(210, 220, 235))
        self.bots_slider = Slider(min=2, max=10, default=int(self.settings.bot_count), step=1, dynamic=True, parent=self.settings_panel, position=(-0.46, -0.055, 0.01), scale=0.85)
        self.bots_slider.on_value_changed = self._on_slider_changed

        self._create_label(self.settings_panel, "Field of View / Угол обзора (FOV):", pos=(-0.24, -0.13, 0.01), scale=0.68, col=rgb32(210, 220, 235))
        self.fov_slider = Slider(min=78, max=110, default=int(self.settings.fov), step=1, dynamic=True, parent=self.settings_panel, position=(-0.46, -0.175, 0.01), scale=0.85)
        self.fov_slider.on_value_changed = self._on_slider_changed

        # Правая колонка переключателей 3D-графики, полного экрана и сложности
        self.fs_btn = self._create_button(self.settings_panel, self._fs_label(), pos=(0.25, 0.19, 0.01), accent=rgb32(42, 82, 72), on_click=self._toggle_fullscreen_clicked)
        self.shadows_btn = self._create_button(self.settings_panel, self._shadows_label(), pos=(0.25, 0.08, 0.01), accent=rgb32(46, 66, 95), on_click=self._toggle_shadows_clicked)
        self.tod_btn = self._create_button(self.settings_panel, f"TIME OF DAY: {self.settings.time_of_day}", pos=(0.25, -0.03, 0.01), accent=rgb32(82, 64, 104), on_click=self._toggle_sky_clicked)
        self.diff_btn = self._create_button(self.settings_panel, f"BOT AI: {self.settings.bot_difficulty}", pos=(0.25, -0.14, 0.01), accent=rgb32(96, 58, 44), on_click=self._toggle_difficulty_clicked)

        self._create_button(
            self.settings_panel,
            "SAVE & BACK  /  СОХРАНИТЬ",
            pos=(0.0, -0.31, 0.01),
            accent=rgb32(228, 138, 28),
            on_click=self.close_settings,
        )

    def _fs_label(self) -> str:
        return "FULLSCREEN: ON (F11)" if self.settings.fullscreen else "FULLSCREEN: OFF (F11)"

    def _shadows_label(self) -> str:
        return "3D SHADOWS: ON" if self.settings.shadows_enabled else "3D SHADOWS: OFF"

    def refresh_toggle_labels(self) -> None:
        for b in (self.fs_btn, self._main_fs_btn):
            b.text = self._fs_label()
        self.shadows_btn.text = self._shadows_label()
        self.tod_btn.text = f"TIME OF DAY: {self.settings.time_of_day}"
        self._main_sky_btn.text = f"SKY: {self.settings.time_of_day}  (F6)"
        self.diff_btn.text = f"BOT AI: {self.settings.bot_difficulty}"

    def _toggle_fullscreen_clicked(self) -> None:
        self.settings.fullscreen = not self.settings.fullscreen
        apply_fullscreen_mode(self.settings.fullscreen)
        self.refresh_toggle_labels()
        self.settings.save()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_shadows_clicked(self) -> None:
        self.settings.shadows_enabled = not self.settings.shadows_enabled
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_sky_clicked(self) -> None:
        order = ("DAY", "SUNSET", "NIGHT")
        self.settings.time_of_day = order[(order.index(self.settings.time_of_day) + 1) % len(order)]
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _toggle_difficulty_clicked(self) -> None:
        order = ("EASY", "NORMAL", "HARD")
        self.settings.bot_difficulty = order[(order.index(self.settings.bot_difficulty) + 1) % len(order)]
        self.refresh_toggle_labels()
        self.on_settings_applied()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)

    def _create_label(
        self,
        parent_ent: Entity,
        content: str,
        pos: tuple[float, float, float],
        scale: float = 1.0,
        col: Any = color.white,
    ) -> Text:
        kwargs: dict[str, Any] = {
            "parent": parent_ent,
            "text": content,
            "origin": (0.0, 0.0),
            "position": pos,
            "scale": scale,
            "color": col,
        }
        if self._font is not None:
            try:
                return Text(**kwargs, font=self._font)
            except Exception:
                return Text(**kwargs)
        return Text(**kwargs)

    def _create_button(
        self,
        parent_ent: Entity,
        title: str,
        pos: tuple[float, float, float],
        accent: Any,
        on_click: Callable[[], None],
    ) -> Button:
        btn = Button(
            parent=parent_ent,
            text=title,
            position=pos,
            scale=(0.43, 0.075),
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
            btn.text_entity.scale *= 0.80
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
        self.sens_slider.value = float(self.settings.mouse_sensitivity)
        self.vol_slider.value = float(self.settings.master_volume)
        self.bots_slider.value = int(self.settings.bot_count)
        self.fov_slider.value = int(self.settings.fov)
        self.refresh_toggle_labels()
        self.settings_panel.enabled = True

    def _on_slider_changed(self) -> None:
        self.settings.mouse_sensitivity = float(self.sens_slider.value)
        self.settings.master_volume = float(self.vol_slider.value)
        self.settings.bot_count = int(round(self.bots_slider.value))
        self.settings.fov = float(self.fov_slider.value)
        self.sound_mgr.set_master_volume(self.settings.master_volume)
        self.on_settings_applied()

    def close_settings(self) -> None:
        self._on_slider_changed()
        self.settings.save()
        self.sound_mgr.play_sfx("empty_click", volume=0.55)
        self.settings_panel.enabled = False
        if self._settings_return_target == "pause":
            self.pause_panel.enabled = True
        else:
            self.main_panel.enabled = True

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
