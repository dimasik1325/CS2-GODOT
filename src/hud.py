"""
Киберспортивный интерфейс CS2 Panorama UI (HUD + Радар + Телеметрия F3 + Дуга урона + Закупка B + Таб):
- Стеклянные тёмно-графитовые карточки с неоновыми золотыми и ледяными акцентными полосами!
- Графический вращающийся радар с сеткой, конусом обзора, кругами дымов, масштабом (radar_zoom) и врагами!
- Направленный индикатор входящего урона (Directional Damage Arc) вокруг прицела!
- Полоска выносливости (Stamina), бейдж текущего 3D-скина оружия (F8), полоска прогресса ранга XP!
- Панель мониторинга оптимизации и FPS (F3), кастомизируемый прицел (цвет, размер, зазор, точка),
  интерактивное меню закупки (B), таблица счёта (Tab) и MVP-карточка раунда!
"""

from __future__ import annotations

import math
from typing import Any, Callable

from ursina import Button, Entity, Text, camera, clamp, color

from src.settings import (
    BUY_ITEMS,
    CROSSHAIR_PALETTE,
    GRENADE_ORDER,
    GRENADE_SPECS,
    WEAPON_SKINS,
    GameSettings,
    load_safe_texture,
    resolve_font_path,
    rgb32,
    rgba32,
)


class CS2HUD:
    """Управляет современным Panorama 2D-интерфейсом, радаром, индикатором направления урона, закупкой и счётом."""

    def __init__(
        self,
        settings: GameSettings,
        on_buy_item: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.on_buy_item = on_buy_item
        self.root = Entity(parent=camera.ui, enabled=False, add_to_scene_entities=False)
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        # ── 1. ЭКРАННЫЕ ЭФФЕКТЫ: УРОН, НАПРАВЛЕННАЯ ДУГА УРОНА, ЛЕЧЕНИЕ И FLASHBANG ──
        self._damage_alpha: float = 0.0
        self._damage_arc_alpha: float = 0.0
        self._heal_alpha: float = 0.0
        self._flashbang_alpha: float = 0.0

        self.damage_flash = Entity(parent=self.root, model="quad", scale=(2.4, 1.4), z=0.05, color=rgba32(215, 22, 22, 0), add_to_scene_entities=False)
        self.heal_flash = Entity(parent=self.root, model="quad", scale=(2.4, 1.4), z=0.048, color=rgba32(45, 225, 115, 0), add_to_scene_entities=False)
        self.flashbang_overlay = Entity(parent=self.root, model="quad", scale=(2.5, 1.5), z=-0.085, color=rgba32(255, 255, 255, 0), add_to_scene_entities=False)

        # Вращающийся индикатор направления выстрела врага вокруг прицела!
        self.damage_arc_pivot = Entity(parent=self.root, z=-0.025, add_to_scene_entities=False)
        self.damage_arc_bar = Entity(
            parent=self.damage_arc_pivot,
            model="quad",
            position=(0.0, 0.135, 0.0),
            scale=(0.085, 0.012),
            color=rgba32(255, 48, 42, 0),
            add_to_scene_entities=False,
        )

        # ── 2. СНАЙПЕРСКИЙ ПРИЦЕЛ AWP ──
        self.scope_root = Entity(parent=self.root, z=-0.06, enabled=False, add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", position=(-0.66, 0.0), scale=(0.68, 1.3), color=rgba32(5, 8, 14, 248), add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", position=(0.66, 0.0), scale=(0.68, 1.3), color=rgba32(5, 8, 14, 248), add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", position=(0.0, 0.44), scale=(0.66, 0.42), color=rgba32(5, 8, 14, 248), add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", position=(0.0, -0.44), scale=(0.66, 0.42), color=rgba32(5, 8, 14, 248), add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", scale=(0.66, 0.0018), color=rgba32(15, 18, 22, 245), z=-0.01, add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", scale=(0.0018, 0.66), color=rgba32(15, 18, 22, 245), z=-0.01, add_to_scene_entities=False)
        Entity(parent=self.scope_root, model="quad", scale=(0.0058, 0.0058), color=rgb32(255, 48, 42), z=-0.02, add_to_scene_entities=False)

        # ── 3. PANORAMA РАДАР-МИНИКАРТА С СЕТКОЙ И КОНУСОМ ОБЗОРА ──
        self.radar_center = (-0.685, 0.352)
        self.radar_half = 0.102
        # Неоновая рамка радара
        Entity(parent=self.root, model="quad", position=(self.radar_center[0], self.radar_center[1], 0.012), scale=(self.radar_half * 2.10, self.radar_half * 2.10), color=rgba32(58, 195, 255, 185), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(self.radar_center[0], self.radar_center[1], 0.008), scale=(self.radar_half * 2.02, self.radar_half * 2.02), color=rgba32(11, 18, 28, 228), add_to_scene_entities=False)
        # Перекрестие координатной сетки радара
        Entity(parent=self.root, model="quad", position=(self.radar_center[0], self.radar_center[1], 0.004), scale=(self.radar_half * 1.96, 0.0015), color=rgba32(65, 125, 165, 85), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(self.radar_center[0], self.radar_center[1], 0.004), scale=(0.0015, self.radar_half * 1.96), color=rgba32(65, 125, 165, 85), add_to_scene_entities=False)
        # Конус обзора игрока на радаре
        Entity(parent=self.root, model="quad", position=(self.radar_center[0] - 0.012, self.radar_center[1] + 0.022, -0.012), scale=(0.0022, 0.044), rotation_z=26.0, color=rgba32(85, 255, 150, 120), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(self.radar_center[0] + 0.012, self.radar_center[1] + 0.022, -0.012), scale=(0.0022, 0.044), rotation_z=-26.0, color=rgba32(85, 255, 150, 120), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(self.radar_center[0], self.radar_center[1], -0.02), scale=(0.009, 0.009), rotation_z=45.0, color=rgb32(85, 255, 145), add_to_scene_entities=False)

        self.radar_site_a = self._make_text("A", pos=(self.radar_center[0], self.radar_center[1], -0.02), scale=0.64, col=rgb32(255, 188, 68))
        self.radar_site_b = self._make_text("B", pos=(self.radar_center[0], self.radar_center[1], -0.02), scale=0.64, col=rgb32(255, 188, 68))
        self.radar_c4_dot = Entity(parent=self.root, model="quad", scale=(0.013, 0.013), color=rgb32(255, 42, 42), z=-0.025, enabled=False, add_to_scene_entities=False)
        self.radar_ping_dot = Entity(parent=self.root, model="quad", scale=(0.010, 0.010), rotation_z=45.0, color=rgb32(65, 235, 255), z=-0.024, enabled=False, add_to_scene_entities=False)
        self.radar_smoke_dots: list[Entity] = [
            Entity(parent=self.root, model="quad", scale=(0.024, 0.024), color=rgba32(195, 208, 220, 130), z=-0.018, enabled=False, add_to_scene_entities=False)
            for _ in range(4)
        ]
        self.radar_enemy_dots: list[Entity] = [
            Entity(parent=self.root, model="quad", scale=(0.0095, 0.0095), color=rgb32(255, 58, 48), z=-0.022, enabled=False, add_to_scene_entities=False)
            for _ in range(10)
        ]

        # Плашка баланса $ и звания под радаром
        Entity(parent=self.root, model="quad", position=(-0.685, 0.214, 0.01), scale=(0.215, 0.052), color=rgba32(10, 16, 26, 224), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(-0.685, 0.239, 0.005), scale=(0.215, 0.003), color=rgb32(92, 242, 136), add_to_scene_entities=False)
        self.cash_text = self._make_text("$ 1600", pos=(-0.685, 0.220), scale=1.06, col=rgb32(108, 248, 136))
        self.rank_hud_text = self._make_text("SILVER ELITE", pos=(-0.685, 0.197), scale=0.45, col=rgb32(255, 196, 68))

        # ── 4. ВЕРХНЕЕ PANORAMA ТАБЛО МАТЧА + ТЕЛЕМЕТРИЯ ОПТИМИЗАЦИИ (F3) ──
        Entity(parent=self.root, model="quad", position=(0.0, 0.446, 0.01), scale=(0.50, 0.082), color=rgba32(10, 15, 24, 232), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(0.0, 0.486, 0.005), scale=(0.50, 0.0035), color=rgb32(255, 182, 42), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(-0.165, 0.448, -0.005), scale=(0.125, 0.064), color=rgba32(38, 108, 198, 235), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(0.165, 0.448, -0.005), scale=(0.125, 0.064), color=rgba32(208, 136, 36, 235), add_to_scene_entities=False)

        self.ct_score_text = self._make_text("CT  0", pos=(-0.165, 0.448), scale=1.16, col=rgb32(232, 244, 255))
        self.timer_text = self._make_text("01:55", pos=(0.0, 0.458), scale=1.28, col=color.white)
        self.round_sub_text = self._make_text("ROUND 1  •  CLASSIC", pos=(0.0, 0.420), scale=0.56, col=rgb32(182, 198, 218))
        self.t_score_text = self._make_text("0  T", pos=(0.165, 0.448), scale=1.16, col=rgb32(255, 244, 215))

        # Телеметрия оптимизации (F3) в правом верхнем углу
        self.telemetry_bg = Entity(parent=self.root, model="quad", position=(0.61, 0.468, 0.01), scale=(0.48, 0.036), color=rgba32(8, 14, 22, 210), add_to_scene_entities=False)
        self.telemetry_text = self._make_text("FPS: 144 | 6.9ms | BATCHES: 5 | POOL: 0", pos=(0.61, 0.468), scale=0.47, col=rgb32(98, 238, 196))

        self.c4_alert_text = self._make_text("", pos=(0.0, 0.376), scale=0.88, col=rgb32(255, 68, 58))
        self.defuse_bar_bg = Entity(parent=self.root, model="quad", position=(0.0, -0.14, -0.02), scale=(0.36, 0.025), color=rgba32(12, 18, 28, 235), enabled=False, add_to_scene_entities=False)
        self.defuse_bar_fill = Entity(parent=self.defuse_bar_bg, model="quad", origin=(-0.5, 0.0), position=(-0.49, 0.0, -0.01), scale=(0.01, 0.78), color=rgb32(72, 218, 255), add_to_scene_entities=False)
        self.defuse_label = self._make_text("ОБЕЗВРЕЖИВАНИЕ C4 (УДЕРЖИВАЙТЕ E)...", pos=(0.0, -0.108), scale=0.70, col=rgb32(125, 228, 255))
        self.defuse_label.enabled = False

        # ── 5. НИЖНЯЯ ЛЕВАЯ КАРТОЧКА PANORAMA: HP, БРОНЯ, СТАМИНА И СПЕЦСРЕДСТВА ──
        Entity(parent=self.root, model="quad", position=(-0.555, -0.422, 0.01), scale=(0.46, 0.118), color=rgba32(10, 15, 24, 228), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(-0.555, -0.363, 0.005), scale=(0.46, 0.0035), color=rgb32(65, 205, 255), add_to_scene_entities=False)

        hp_tex = load_safe_texture("assets/textures/icon_hp.png")
        Entity(parent=self.root, model="quad", texture=hp_tex, position=(-0.745, -0.402, -0.01), scale=(0.034, 0.034), color=rgb32(95, 238, 152) if hp_tex is None else color.white, add_to_scene_entities=False)
        self.hp_text = self._make_text("100", pos=(-0.668, -0.402), scale=1.58, col=color.white)
        Entity(parent=self.root, model="quad", position=(-0.685, -0.438, -0.01), scale=(0.145, 0.009), color=rgba32(45, 54, 66, 225), add_to_scene_entities=False)
        self.hp_bar = Entity(parent=self.root, model="quad", origin=(-0.5, 0.0), position=(-0.7575, -0.438, -0.02), scale=(0.145, 0.009), color=rgb32(88, 238, 145), add_to_scene_entities=False)

        armor_tex = load_safe_texture("assets/textures/icon_armor.png")
        Entity(parent=self.root, model="quad", texture=armor_tex, position=(-0.54, -0.402, -0.01), scale=(0.034, 0.034), color=rgb32(85, 178, 255) if armor_tex is None else color.white, add_to_scene_entities=False)
        self.armor_text = self._make_text("100", pos=(-0.462, -0.402), scale=1.58, col=rgb32(202, 230, 255))
        Entity(parent=self.root, model="quad", position=(-0.48, -0.438, -0.01), scale=(0.145, 0.009), color=rgba32(45, 54, 66, 225), add_to_scene_entities=False)
        self.armor_bar = Entity(parent=self.root, model="quad", origin=(-0.5, 0.0), position=(-0.5525, -0.438, -0.02), scale=(0.145, 0.009), color=rgb32(78, 174, 255), add_to_scene_entities=False)

        # Полоска выносливости (Stamina)
        Entity(parent=self.root, model="quad", position=(-0.555, -0.453, -0.01), scale=(0.41, 0.005), color=rgba32(38, 46, 58, 220), add_to_scene_entities=False)
        self.stamina_bar = Entity(parent=self.root, model="quad", origin=(-0.5, 0.0), position=(-0.76, -0.453, -0.02), scale=(0.41, 0.005), color=rgb32(255, 198, 58), add_to_scene_entities=False)

        self.gear_sub_text = self._make_text(
            "[X] STIM:1  |  [T] LIGHT  |  [C] RADIO  |  [F5] 3RD-PERSON",
            pos=(-0.555, -0.470),
            scale=0.46,
            col=rgb32(174, 192, 214),
        )

        # ── 6. НИЖНЯЯ ПРАВАЯ КАРТОЧКА PANORAMA: ОРУЖИЕ, СКИН F8, ПАТРОНЫ И ГРАНАТЫ ──
        Entity(parent=self.root, model="quad", position=(0.545, -0.420, 0.01), scale=(0.48, 0.122), color=rgba32(10, 15, 24, 228), add_to_scene_entities=False)
        Entity(parent=self.root, model="quad", position=(0.545, -0.359, 0.005), scale=(0.48, 0.0035), color=rgb32(255, 182, 42), add_to_scene_entities=False)

        self.weapon_name_text = self._make_text("AK-47  •  SPEC-OPS", pos=(0.545, -0.376), scale=0.78, col=rgb32(255, 192, 62))
        self.ammo_text = self._make_text("30 / 90", pos=(0.545, -0.414), scale=1.54, col=color.white)
        self.grenade_belt_text = self._make_text("[G] THROW: HE(1) FLASH(1) SMOKE(1) MOLO(1)", pos=(0.545, -0.448), scale=0.49, col=rgb32(215, 228, 244))
        self.slots_text = self._make_text("[1-4,6-0] ОРУЖИЕ  [F8] СКИН  [F] ОСМОТР  [B] ЗАКУПКА", pos=(0.545, -0.469), scale=0.45, col=rgb32(158, 176, 198))

        # ── 7. НАСТРАИВАЕМЫЙ ПРИЦЕЛ CS2 ──
        ch_col = rgb32(*CROSSHAIR_PALETTE[0][1])
        self.ch_top = Entity(parent=self.root, model="quad", color=ch_col, z=-0.02, add_to_scene_entities=False)
        self.ch_bottom = Entity(parent=self.root, model="quad", color=ch_col, z=-0.02, add_to_scene_entities=False)
        self.ch_left = Entity(parent=self.root, model="quad", color=ch_col, z=-0.02, add_to_scene_entities=False)
        self.ch_right = Entity(parent=self.root, model="quad", color=ch_col, z=-0.02, add_to_scene_entities=False)
        self.ch_dot = Entity(parent=self.root, model="quad", scale=(0.0026, 0.0026), color=ch_col, z=-0.02, add_to_scene_entities=False)
        self.apply_crosshair_style()
        self.update_crosshair(0.01)

        # ── 8. HITMARKER ──
        self._hitmarker_timer: float = 0.0
        self._hitmarker_headshot: bool = False
        self.hitmarker_bars: list[Entity] = []
        for (hx, hy), rot_z in [((-0.011, 0.011), -45.0), ((0.011, 0.011), 45.0), ((-0.011, -0.011), 45.0), ((0.011, -0.011), -45.0)]:
            bar = Entity(parent=self.root, model="quad", position=(hx, hy, -0.03), scale=(0.0024, 0.011), rotation_z=rot_z, color=rgba32(255, 255, 255, 0), add_to_scene_entities=False)
            self.hitmarker_bars.append(bar)

        # ── 9. КИЛЛФИД, СЕРИИ УБИЙСТВ И РАЦИЯ ──
        self._killfeed_entries: list[tuple[str, float, bool]] = []
        self._killfeed_labels: list[Text] = [
            self._make_text("", pos=(0.56, 0.415 - idx * 0.034), scale=0.64, col=rgb32(245, 220, 165))
            for idx in range(5)
        ]

        self._streak_timer: float = 0.0
        self.streak_text = self._make_text("", pos=(0.0, 0.285, -0.03), scale=1.32, col=rgb32(255, 198, 56))
        self.streak_text.enabled = False

        self._notice_timer: float = 0.0
        self.notice_text = self._make_text("", pos=(0.0, -0.265, -0.03), scale=0.74, col=rgb32(138, 228, 255))
        self.notice_text.enabled = False

        # ── 10. ЦЕНТРАЛЬНЫЙ MVP-БАННЕР РАУНДА ──
        self.banner_box = Entity(parent=self.root, model="quad", position=(0.0, 0.155, -0.03), scale=(0.78, 0.15), color=rgba32(10, 15, 25, 238), enabled=False, add_to_scene_entities=False)
        Entity(parent=self.banner_box, model="quad", position=(0.0, 0.48, -0.005), scale=(1.0, 0.035), color=rgb32(255, 182, 42), add_to_scene_entities=False)
        self.banner_title = self._make_text("", pos=(0.0, 0.182, -0.04), scale=1.45, col=rgb32(95, 195, 255))
        self.banner_sub = self._make_text("", pos=(0.0, 0.122, -0.04), scale=0.74, col=rgb32(222, 232, 245))
        self.banner_title.enabled = False
        self.banner_sub.enabled = False

        # ── 11. МЕНЮ ЗАКУПКИ СНАРЯЖЕНИЯ PANORAMA BUY MENU (B) ──
        self.buy_panel = Entity(parent=self.root, z=-0.07, enabled=False, add_to_scene_entities=False)
        Entity(parent=self.buy_panel, model="quad", scale=(1.22, 0.74), color=rgba32(9, 14, 24, 242), add_to_scene_entities=False)
        Entity(parent=self.buy_panel, model="quad", position=(0.0, 0.368, -0.005), scale=(1.22, 0.005), color=rgb32(255, 182, 42), add_to_scene_entities=False)
        self._make_parent_text(self.buy_panel, "CS2 PANORAMA BUY MENU  —  НАЖМИТЕ [B] ИЛИ [ESC] ДЛЯ ЗАКРЫТИЯ", pos=(0.0, 0.31, -0.01), scale=0.92, col=rgb32(255, 192, 58))
        self.buy_buttons: list[Button] = []
        for i, item in enumerate(BUY_ITEMS):
            col_i = i % 3
            row_i = i // 3
            bx = -0.37 + col_i * 0.37
            by = 0.175 - row_i * 0.122
            item_id = str(item["id"])
            btn = Button(
                parent=self.buy_panel,
                text=f"{item['label']}\n$ {item['price']}",
                position=(bx, by, -0.015),
                scale=(0.34, 0.098),
                color=rgb32(24, 36, 54),
                highlight_color=rgb32(48, 86, 136),
                pressed_color=rgb32(235, 148, 32),
                on_click=(lambda iid=item_id: self._click_buy(iid)),
            )
            if self._font is not None and btn.text_entity is not None:
                try:
                    btn.text_entity.font = self._font
                except Exception:
                    pass
                btn.text_entity.scale *= 0.72
            self.buy_buttons.append(btn)

        # ── 12. ТАБЛИЦА СТАТИСТИКИ МАТЧА SCOREBOARD (TAB) ──
        self.scoreboard_panel = Entity(parent=self.root, z=-0.075, enabled=False, add_to_scene_entities=False)
        Entity(parent=self.scoreboard_panel, model="quad", scale=(1.18, 0.70), color=rgba32(8, 13, 22, 242), add_to_scene_entities=False)
        Entity(parent=self.scoreboard_panel, model="quad", position=(0.0, 0.348, -0.005), scale=(1.18, 0.005), color=rgb32(65, 205, 255), add_to_scene_entities=False)
        self._make_parent_text(self.scoreboard_panel, "ТАБЛИЦА МАТЧА CS2  •  АЛКОДИМАС × УСАТЫЙ ЭЛЬДАР EDITION", pos=(0.0, 0.29, -0.01), scale=0.92, col=rgb32(255, 192, 58))
        self.sb_body = self._make_parent_text(self.scoreboard_panel, "", pos=(0.0, -0.02, -0.01), scale=0.68, col=rgb32(224, 234, 248))

    def _make_text(self, content: str, pos: tuple[float, ...], scale: float = 1.0, col: Any = color.white) -> Text:
        return self._make_parent_text(self.root, content, pos, scale, col)

    def _make_parent_text(self, parent_ent: Entity, content: str, pos: tuple[float, ...], scale: float = 1.0, col: Any = color.white) -> Text:
        kwargs: dict[str, Any] = {"parent": parent_ent, "text": content, "origin": (0.0, 0.0), "scale": scale, "color": col}
        if self._font is not None:
            try:
                txt = Text(**kwargs, font=self._font)
            except Exception:
                txt = Text(**kwargs)
        else:
            txt = Text(**kwargs)
        txt.position = (pos[0], pos[1], -0.02) if len(pos) == 2 else pos
        return txt

    def _click_buy(self, item_id: str) -> None:
        if self.on_buy_item is not None:
            self.on_buy_item(item_id)

    def set_visible(self, visible: bool) -> None:
        self.root.enabled = visible
        if not visible:
            self.buy_panel.enabled = False
            self.scoreboard_panel.enabled = False
            self.scope_root.enabled = False

    def apply_crosshair_style(self) -> str:
        name, rgb = CROSSHAIR_PALETTE[self.settings.crosshair_color_idx % len(CROSSHAIR_PALETTE)]
        c = rgb32(*rgb)
        sz = clamp(self.settings.crosshair_size, 0.5, 2.2)
        bar_len = 0.012 * sz
        bar_thick = 0.0024 * clamp(sz, 0.75, 1.45)
        self.ch_top.scale = (bar_thick, bar_len)
        self.ch_bottom.scale = (bar_thick, bar_len)
        self.ch_left.scale = (bar_len, bar_thick)
        self.ch_right.scale = (bar_len, bar_thick)
        for part in (self.ch_top, self.ch_bottom, self.ch_left, self.ch_right, self.ch_dot):
            part.color = c
        self.ch_dot.enabled = bool(self.settings.crosshair_dot) and not self.scope_root.enabled
        return name

    def apply_crosshair_color(self, palette_idx: int) -> str:
        self.settings.crosshair_color_idx = palette_idx % len(CROSSHAIR_PALETTE)
        return self.apply_crosshair_style()

    def set_scope_visible(self, scoped: bool) -> None:
        self.scope_root.enabled = scoped
        for part in (self.ch_top, self.ch_bottom, self.ch_left, self.ch_right):
            part.enabled = not scoped
        self.ch_dot.enabled = (not scoped) and bool(self.settings.crosshair_dot)

    def update_crosshair(self, spread: float) -> None:
        gap_base = 0.008 * clamp(self.settings.crosshair_gap, 0.5, 2.2)
        gap = clamp(gap_base + spread * 0.34, 0.005, 0.058)
        half_len = self.ch_top.scale_y * 0.5
        self.ch_top.position = (0.0, gap + half_len, -0.02)
        self.ch_bottom.position = (0.0, -(gap + half_len), -0.02)
        self.ch_left.position = (-(gap + half_len), 0.0, -0.02)
        self.ch_right.position = (gap + half_len, 0.0, -0.02)

    def show_hitmarker(self, is_headshot: bool = False) -> None:
        self._hitmarker_timer = 0.18
        self._hitmarker_headshot = is_headshot
        col = rgba32(255, 62, 48, 255) if is_headshot else rgba32(255, 255, 255, 245)
        for bar in self.hitmarker_bars:
            bar.color = col

    def flash_damage(self, rel_angle_deg: float | None = None) -> None:
        self._damage_alpha = 118.0
        self.damage_flash.color = rgba32(215, 24, 24, int(self._damage_alpha))
        if rel_angle_deg is not None:
            self.damage_arc_pivot.rotation_z = -rel_angle_deg
            self._damage_arc_alpha = 235.0
            self.damage_arc_bar.color = rgba32(255, 48, 42, int(self._damage_arc_alpha))

    def flash_heal(self) -> None:
        self._heal_alpha = 95.0
        self.heal_flash.color = rgba32(45, 225, 115, int(self._heal_alpha))

    def trigger_flashbang(self, strength: float) -> None:
        self._flashbang_alpha = max(self._flashbang_alpha, clamp(strength, 0.0, 1.0) * 255.0)
        self.flashbang_overlay.color = rgba32(255, 255, 255, int(self._flashbang_alpha))

    def show_killstreak_banner(self, text_str: str) -> None:
        self.streak_text.text = text_str
        self.streak_text.enabled = True
        self._streak_timer = 2.4

    def show_notice(self, message: str, duration: float = 2.2) -> None:
        self.notice_text.text = message
        self.notice_text.enabled = True
        self._notice_timer = duration

    def push_killfeed(self, weapon_name: str, victim_name: str, is_headshot: bool) -> None:
        hs_tag = " [HS]" if is_headshot else ""
        line = f"YOU  [{weapon_name}{hs_tag}]  {victim_name}"
        self._killfeed_entries.insert(0, (line, 5.0, is_headshot))
        self._killfeed_entries = self._killfeed_entries[:5]
        self._refresh_killfeed_ui()

    def clear_killfeed(self) -> None:
        self._killfeed_entries.clear()
        self._refresh_killfeed_ui()

    def _refresh_killfeed_ui(self) -> None:
        for idx, lbl in enumerate(self._killfeed_labels):
            if idx < len(self._killfeed_entries):
                text_str, _, is_hs = self._killfeed_entries[idx]
                lbl.text = text_str
                lbl.color = rgb32(255, 110, 95) if is_hs else rgb32(245, 224, 175)
            else:
                lbl.text = ""

    def show_round_banner(self, title: str, subtitle: str, ct_won: bool = True) -> None:
        self.banner_box.enabled = True
        self.banner_title.enabled = True
        self.banner_sub.enabled = True
        self.banner_title.text = title
        self.banner_title.color = rgb32(95, 195, 255) if ct_won else rgb32(255, 168, 58)
        self.banner_sub.text = subtitle

    def hide_round_banner(self) -> None:
        self.banner_box.enabled = False
        self.banner_title.enabled = False
        self.banner_sub.enabled = False

    def _world_to_radar(self, wx: float, wz: float, px: float, pz: float, yaw_deg: float) -> tuple[float, float]:
        dx = wx - px
        dz = wz - pz
        rad = math.radians(yaw_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        rx = dx * cos_a - dz * sin_a
        ry = -dx * sin_a + dz * cos_a
        zoom = clamp(self.settings.radar_zoom, 0.6, 1.6)
        scale = (self.radar_half / 34.0) * zoom
        ux = clamp(rx * scale, -self.radar_half * 0.90, self.radar_half * 0.90)
        uy = clamp(ry * scale, -self.radar_half * 0.90, self.radar_half * 0.90)
        return self.radar_center[0] + ux, self.radar_center[1] + uy

    def update_radar(
        self,
        player_pos: Any,
        player_yaw: float,
        site_a: Any,
        site_b: Any,
        bots: list[Any],
        c4_planted: bool,
        c4_pos: Any,
        ping_pos: Any,
        smokes: list[Any] | None = None,
    ) -> None:
        ax, ay = self._world_to_radar(site_a.x, site_a.z, player_pos.x, player_pos.z, player_yaw)
        bx, by = self._world_to_radar(site_b.x, site_b.z, player_pos.x, player_pos.z, player_yaw)
        self.radar_site_a.position = (ax, ay, -0.02)
        self.radar_site_b.position = (bx, by, -0.02)

        if c4_planted:
            cx, cy = self._world_to_radar(c4_pos.x, c4_pos.z, player_pos.x, player_pos.z, player_yaw)
            self.radar_c4_dot.position = (cx, cy, -0.025)
            self.radar_c4_dot.enabled = True
        else:
            self.radar_c4_dot.enabled = False

        if ping_pos is not None:
            px_r, py_r = self._world_to_radar(ping_pos.x, ping_pos.z, player_pos.x, player_pos.z, player_yaw)
            self.radar_ping_dot.position = (px_r, py_r, -0.024)
            self.radar_ping_dot.enabled = True
        else:
            self.radar_ping_dot.enabled = False

        for s_idx, s_dot in enumerate(self.radar_smoke_dots):
            if smokes is not None and s_idx < len(smokes):
                sm = smokes[s_idx]
                sx, sy = self._world_to_radar(sm.center.x, sm.center.z, player_pos.x, player_pos.z, player_yaw)
                s_dot.position = (sx, sy, -0.018)
                s_dot.enabled = True
            else:
                s_dot.enabled = False

        for idx, dot in enumerate(self.radar_enemy_dots):
            if idx < len(bots):
                b = bots[idx]
                visible_on_radar = b.state != "DEAD" and (
                    b.state == "ATTACK"
                    or b.role == "BOSS"
                    or getattr(b, "recently_fired_timer", 0.0) > 0.0
                    or (b.world_position - player_pos).length() < 18.0
                )
                if visible_on_radar:
                    ex, ey = self._world_to_radar(b.x, b.z, player_pos.x, player_pos.z, player_yaw)
                    dot.position = (ex, ey, -0.022)
                    dot.color = rgb32(255, 205, 48) if b.role == "BOSS" else rgb32(255, 58, 48)
                    dot.enabled = True
                else:
                    dot.enabled = False
            else:
                dot.enabled = False

    def update_telemetry(self, dt: float, batches: int, active_fx: int) -> None:
        show = bool(self.settings.show_fps_telemetry)
        self.telemetry_bg.enabled = show
        self.telemetry_text.enabled = show
        if not show:
            return
        fps = int(round(1.0 / max(0.001, dt)))
        ms = dt * 1000.0
        self.telemetry_text.text = (
            f"FPS: {fps:>3d} ({ms:4.1f}ms)  |  GPU BATCHES: {batches}  |  FX POOL: {active_fx}  |  {self.settings.graphics_preset}"
        )

    def update_scoreboard(
        self,
        ct_score: int,
        t_score: int,
        player_kills: int,
        player_deaths: int,
        player_hs: int,
        shots_fired: int,
        shots_hit: int,
        total_dmg: int,
        cash: int,
        bots: list[Any],
    ) -> None:
        if not self.scoreboard_panel.enabled:
            return
        acc = int(round(100.0 * shots_hit / max(1, shots_fired)))
        hs_pct = int(round(100.0 * player_hs / max(1, player_kills)))
        lines = [
            f"CT  {ct_score}   :   {t_score}  TERRORISTS   |   РЕЖИМ: {self.settings.game_mode}   |   ЗВАНИЕ: {self.settings.get_rank_title()}",
            "────────────────────────────────────────────────────────────────────",
            f"[CT] ВЫ            K: {player_kills:<2d}  D: {player_deaths:<2d}  HS: {hs_pct:>3d}%   ACC: {acc:>3d}%   DMG: {total_dmg:<4d}  ${cash}",
            "────────────────────────────────────────────────────────────────────",
        ]
        for b in bots:
            status = "DEAD" if b.state == "DEAD" else f"{b.hp} HP"
            lines.append(
                f"[T ] {b.bot_name:<15s} ({b.role:<6s})   K: {b.kills:<2d}  D: {b.deaths:<2d}   STATUS: {status}"
            )
        self.sb_body.text = "\n".join(lines)

    def sync_stats(
        self,
        hp: int,
        armor: int,
        stamina: float,
        weapon_id: str,
        weapon_display_name: str,
        skin_idx: int,
        ammo_mag: int,
        ammo_reserve: int,
        is_reloading: bool,
        ct_score: int,
        t_score: int,
        round_num: int,
        time_left: float,
        alive_bots: int,
        spread: float,
        cash: int = 1600,
        grenades: dict[str, int] | None = None,
        selected_grenade: str = "he",
        stimshots: int = 1,
        flashlight_on: bool = False,
        third_person: bool = False,
        is_scoped: bool = False,
        burst_active: bool = False,
        c4_planted: bool = False,
        c4_site: str = "",
        c4_timer: float = 0.0,
        defuse_progress: float = 0.0,
    ) -> None:
        self.hp_text.text = str(max(0, hp))
        self.hp_text.color = rgb32(255, 75, 70) if hp <= 25 else color.white
        self.hp_bar.scale_x = max(0.001, 0.145 * clamp(hp / 100.0, 0.0, 1.0))
        self.hp_bar.color = rgb32(255, 75, 70) if hp <= 25 else rgb32(88, 238, 145)

        self.armor_text.text = str(max(0, armor))
        self.armor_bar.scale_x = max(0.001, 0.145 * clamp(armor / 100.0, 0.0, 1.0))
        self.stamina_bar.scale_x = max(0.002, 0.41 * clamp(stamina / 100.0, 0.0, 1.0))

        self.cash_text.text = f"$ {cash}"
        self.rank_hud_text.text = f"{self.settings.get_rank_title()} ({self.settings.player_xp} XP)"

        cam_tag = "3RD" if third_person else "1ST"
        light_tag = "ON" if flashlight_on else "OFF"
        self.gear_sub_text.text = f"[X] STIM:{stimshots}  |  [T] LIGHT:{light_tag}  |  [C] РАЦИЯ  |  [F5] CAM:{cam_tag}"

        skin_name = WEAPON_SKINS[skin_idx % len(WEAPON_SKINS)]["name"]
        mode_suffix = " [BURST]" if burst_active else ""
        if is_reloading:
            self.weapon_name_text.text = f"{weapon_display_name}  •  ПЕРЕЗАРЯДКА..."
            self.weapon_name_text.color = rgb32(255, 218, 92)
        else:
            self.weapon_name_text.text = f"{weapon_display_name}{mode_suffix}  •  {skin_name}"
            self.weapon_name_text.color = rgb32(255, 192, 62)

        if ammo_mag < 0:
            self.ammo_text.text = "ЛКМ SLASH / ПКМ STAB"
            self.ammo_text.color = rgb32(210, 228, 245)
        else:
            self.ammo_text.text = f"{ammo_mag} / {ammo_reserve}"
            self.ammo_text.color = rgb32(255, 92, 78) if ammo_mag <= 5 else color.white

        if grenades is not None:
            g_parts = []
            for gid in GRENADE_ORDER:
                cnt = grenades.get(gid, 0)
                short = GRENADE_SPECS[gid]["short"]
                lbl = f"{short}({cnt})"
                g_parts.append(f">{lbl}<" if gid == selected_grenade else lbl)
            self.grenade_belt_text.text = "[G] БРОСОК / [V] ТИП:  " + "  ".join(g_parts)

        self.ct_score_text.text = f"CT  {ct_score}"
        self.t_score_text.text = f"{t_score}  T"

        if c4_planted:
            self.timer_text.text = f"C4 {c4_timer:04.1f}s"
            self.timer_text.color = rgb32(255, 65, 55)
            self.c4_alert_text.text = f"⚠ БОМБА C4 ЗАЛОЖЕНА НА {c4_site}! ЗАЖМИТЕ [E] РЯДОМ С БОМБОЙ!"
        else:
            secs_total = max(0, int(time_left))
            mm, ss = divmod(secs_total, 60)
            self.timer_text.text = f"{mm:02d}:{ss:02d}"
            self.timer_text.color = rgb32(255, 85, 75) if secs_total <= 15 else color.white
            self.c4_alert_text.text = ""

        if defuse_progress > 0.01:
            self.defuse_bar_bg.enabled = True
            self.defuse_label.enabled = True
            self.defuse_bar_fill.scale_x = max(0.01, 0.98 * clamp(defuse_progress, 0.0, 1.0))
        else:
            self.defuse_bar_bg.enabled = False
            self.defuse_label.enabled = False

        self.round_sub_text.text = f"РАУНД {round_num}  •  {self.settings.game_mode}  •  ВРАГИ: {alive_bots}"
        self.set_scope_visible(is_scoped)
        if not is_scoped:
            self.update_crosshair(spread)

    def update(self, dt: float) -> None:
        if self._hitmarker_timer > 0.0:
            self._hitmarker_timer = max(0.0, self._hitmarker_timer - dt)
            alpha = int(255.0 * (self._hitmarker_timer / 0.18))
            col = rgba32(255, 62, 48, alpha) if self._hitmarker_headshot else rgba32(255, 255, 255, alpha)
            for bar in self.hitmarker_bars:
                bar.color = col

        if self._damage_alpha > 0.0:
            self._damage_alpha = max(0.0, self._damage_alpha - dt * 310.0)
            self.damage_flash.color = rgba32(215, 24, 24, int(self._damage_alpha))

        if self._damage_arc_alpha > 0.0:
            self._damage_arc_alpha = max(0.0, self._damage_arc_alpha - dt * 195.0)
            self.damage_arc_bar.color = rgba32(255, 48, 42, int(self._damage_arc_alpha))

        if self._heal_alpha > 0.0:
            self._heal_alpha = max(0.0, self._heal_alpha - dt * 220.0)
            self.heal_flash.color = rgba32(45, 225, 115, int(self._heal_alpha))

        if self._flashbang_alpha > 0.0:
            fade_spd = 72.0 if self._flashbang_alpha > 140.0 else 155.0
            self._flashbang_alpha = max(0.0, self._flashbang_alpha - dt * fade_spd)
            self.flashbang_overlay.color = rgba32(255, 255, 255, int(self._flashbang_alpha))

        if self._streak_timer > 0.0:
            self._streak_timer = max(0.0, self._streak_timer - dt)
            if self._streak_timer <= 0.0:
                self.streak_text.enabled = False

        if self._notice_timer > 0.0:
            self._notice_timer = max(0.0, self._notice_timer - dt)
            if self._notice_timer <= 0.0:
                self.notice_text.enabled = False

        if self._killfeed_entries:
            changed = False
            updated: list[tuple[str, float, bool]] = []
            for line, ttl, is_hs in self._killfeed_entries:
                new_ttl = ttl - dt
                if new_ttl > 0.0:
                    updated.append((line, new_ttl, is_hs))
                else:
                    changed = True
            self._killfeed_entries = updated
            if changed:
                self._refresh_killfeed_ui()
