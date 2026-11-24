"""
Система экранов меню игры:
1) Главное меню (Play / Settings / Quit, фоновый арт menu_bg.png, фоновая музыка, подсказка управления)
2) Меню паузы по клавише Esc (Resume / Settings / Restart Match / Main Menu / Quit)
3) Окно настроек (ползунки чувствительности мыши, громкости звука и количества ботов)
"""

from __future__ import annotations

from typing import Any, Callable

from ursina import Button, Entity, Slider, Text, application, camera, color, mouse

from src.settings import (
    GameSettings,
    SoundManager,
    load_safe_texture,
    resolve_font_path,
)


class MenuManager:
    """Управляет Главным меню, Меню паузы и Окном настроек."""

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
        self._settings_return_target: str = "main"  # 'main' | 'pause'

        # ── 1. ГЛАВНОЕ МЕНЮ ──
        self.main_panel = Entity(parent=camera.ui, enabled=False)
        bg_tex = load_safe_texture("assets/textures/menu_bg.png")
        Entity(
            parent=self.main_panel,
            model="quad",
            texture=bg_tex,
            scale=(1.95, 1.12),
            z=0.08,
            color=color.white if bg_tex is not None else color.rgb(22, 28, 38),
        )
        # Левая затемнённая колонка в стиле главного экрана CS2
        Entity(
            parent=self.main_panel,
            model="quad",
            position=(-0.44, 0.0, 0.05),
            scale=(0.68, 1.12),
            color=color.rgba(10, 14, 22, 222),
        )

        self._create_label(
            self.main_panel,
            "COUNTER-STRIKE 2",
            pos=(-0.44, 0.34, 0.02),
            scale=1.85,
            col=color.rgb(245, 166, 35),
        )
        self._create_label(
            self.main_panel,
            "PYTHON 3.11  •  URSINA 3D TACTICAL OPS",
            pos=(-0.44, 0.275, 0.02),
            scale=0.72,
            col=color.rgb(185, 198, 218),
        )

        self._create_button(
            self.main_panel,
            "PLAY  /  ИГРАТЬ",
            pos=(-0.44, 0.11, 0.01),
            accent=color.rgb(228, 138, 28),
            on_click=self._handle_play_clicked,
        )
        self._create_button(
            self.main_panel,
            "SETTINGS  /  НАСТРОЙКИ",
            pos=(-0.44, -0.01, 0.01),
            accent=color.rgb(36, 46, 62),
            on_click=lambda: self.open_settings("main"),
        )
        self._create_button(
            self.main_panel,
            "QUIT  /  ВЫХОД",
            pos=(-0.44, -0.13, 0.01),
            accent=color.rgb(138, 38, 38),
            on_click=self._handle_quit,
        )

        # Информационная карточка управления справа
        Entity(
            parent=self.main_panel,
            model="quad",
            position=(0.30, -0.02, 0.05),
            scale=(0.62, 0.62),
            color=color.rgba(12, 16, 24, 205),
        )
        self._create_label(
            self.main_panel,
            "УПРАВЛЕНИЕ  /  CONTROLS",
            pos=(0.30, 0.22, 0.02),
            scale=1.02,
            col=color.rgb(245, 185, 65),
        )
        controls_lines = (
            "WASD — Передвижение\n"
            "Left Shift — Быстрый бег\n"
            "Left Ctrl — Тактический присед (+точность)\n"
            "Space — Прыжок\n"
            "ЛКМ — Стрельба / Очередь / Удар ножом\n"
            "R — Перезарядка магазина\n"
            "1 / 2 / 3 / 4 (или колесо) — AK-47 / Deagle / Нож / M4A1-S\n"
            "Esc — Пауза и настройки в бою"
        )
        self._create_label(
            self.main_panel,
            controls_lines,
            pos=(0.30, -0.04, 0.02),
            scale=0.72,
            col=color.rgb(218, 226, 238),
        )

        # ── 2. МЕНЮ ПАУЗЫ (ESC) ──
        self.pause_panel = Entity(parent=camera.ui, enabled=False)
        Entity(
            parent=self.pause_panel,
            model="quad",
            scale=(2.1, 1.2),
            z=0.06,
            color=color.rgba(8, 12, 18, 195),
        )
        Entity(
            parent=self.pause_panel,
            model="quad",
            position=(0.0, 0.0, 0.04),
            scale=(0.56, 0.72),
            color=color.rgba(16, 22, 32, 238),
        )
        self._create_label(
            self.pause_panel,
            "PAUSED  /  ПАУЗА",
            pos=(0.0, 0.27, 0.01),
            scale=1.45,
            col=color.rgb(245, 175, 50),
        )
        self._create_button(
            self.pause_panel,
            "RESUME  (ESC)",
            pos=(0.0, 0.14, 0.01),
            accent=color.rgb(46, 122, 195),
            on_click=self._handle_resume_clicked,
        )
        self._create_button(
            self.pause_panel,
            "SETTINGS  /  НАСТРОЙКИ",
            pos=(0.0, 0.03, 0.01),
            accent=color.rgb(38, 48, 64),
            on_click=lambda: self.open_settings("pause"),
        )
        self._create_button(
            self.pause_panel,
            "RESTART MATCH  /  ЗАНОВО",
            pos=(0.0, -0.08, 0.01),
            accent=color.rgb(38, 48, 64),
            on_click=self._handle_restart_clicked,
        )
        self._create_button(
            self.pause_panel,
            "MAIN MENU  /  В МЕНЮ",
            pos=(0.0, -0.19, 0.01),
            accent=color.rgb(92, 68, 32),
            on_click=self._handle_main_menu_clicked,
        )
        self._create_button(
            self.pause_panel,
            "QUIT  /  ВЫХОД",
            pos=(0.0, -0.30, 0.01),
            accent=color.rgb(138, 38, 38),
            on_click=self._handle_quit,
        )

        # ── 3. ПАНЕЛЬ НАСТРОЕК (МЫШЬ, ГРОМКОСТЬ, ЧИСЛО БОТОВ) ──
        self.settings_panel = Entity(parent=camera.ui, enabled=False)
        Entity(
            parent=self.settings_panel,
            model="quad",
            scale=(2.1, 1.2),
            z=0.07,
            color=color.rgba(8, 12, 18, 225),
        )
        Entity(
            parent=self.settings_panel,
            model="quad",
            position=(0.0, 0.0, 0.05),
            scale=(0.86, 0.72),
            color=color.rgba(16, 22, 34, 242),
        )
        self._create_label(
            self.settings_panel,
            "SETTINGS  /  НАСТРОЙКИ",
            pos=(0.0, 0.27, 0.01),
            scale=1.40,
            col=color.rgb(245, 175, 50),
        )

        # Ползунок чувствительности мыши
        self._create_label(
            self.settings_panel,
            "Mouse Sensitivity (Чувствительность мыши):",
            pos=(0.0, 0.165, 0.01),
            scale=0.78,
            col=color.rgb(210, 220, 235),
        )
        self.sens_slider = Slider(
            min=10,
            max=120,
            default=round(self.settings.mouse_sensitivity, 1),
            dynamic=True,
            parent=self.settings_panel,
            position=(-0.26, 0.115, 0.01),
        )
        self.sens_slider.on_value_changed = self._on_slider_changed

        # Ползунок общей громкости
        self._create_label(
            self.settings_panel,
            "Master Volume (Громкость звука и музыки):",
            pos=(0.0, 0.035, 0.01),
            scale=0.78,
            col=color.rgb(210, 220, 235),
        )
        self.vol_slider = Slider(
            min=0.0,
            max=1.0,
            default=round(self.settings.master_volume, 2),
            dynamic=True,
            parent=self.settings_panel,
            position=(-0.26, -0.015, 0.01),
        )
        self.vol_slider.on_value_changed = self._on_slider_changed

        # Ползунок количества врагов в раунде
        self._create_label(
            self.settings_panel,
            "Bots per Round (Количество врагов в раунде):",
            pos=(0.0, -0.095, 0.01),
            scale=0.78,
            col=color.rgb(210, 220, 235),
        )
        self.bots_slider = Slider(
            min=2,
            max=8,
            default=int(self.settings.bot_count),
            step=1,
            dynamic=True,
            parent=self.settings_panel,
            position=(-0.26, -0.145, 0.01),
        )
        self.bots_slider.on_value_changed = self._on_slider_changed

        self._create_button(
            self.settings_panel,
            "SAVE & BACK  /  СОХРАНИТЬ",
            pos=(0.0, -0.265, 0.01),
            accent=color.rgb(228, 138, 28),
            on_click=self.close_settings,
        )

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
            kwargs["font"] = self._font
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
            scale=(0.44, 0.078),
            color=accent,
            highlight_color=accent.tint(0.18),
            pressed_color=accent.tint(-0.15),
            on_click=on_click,
        )
        if self._font is not None and btn.text_entity is not None:
            btn.text_entity.font = self._font
            btn.text_entity.scale *= 0.88
        return btn

    def show_main_menu(self) -> None:
        self.pause_panel.enabled = False
        self.settings_panel.enabled = False
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
        self.settings_panel.enabled = True

    def _on_slider_changed(self) -> None:
        self.settings.mouse_sensitivity = float(self.sens_slider.value)
        self.settings.master_volume = float(self.vol_slider.value)
        self.settings.bot_count = int(round(self.bots_slider.value))
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
