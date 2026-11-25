"""
Расширенный тактический интерфейс Counter-Strike 2 (HUD + Радар + Закупка B + Таблица счёта Tab):
- Вращающийся 2D тактический радар-миникарта (пленты A/B, враги, дымы, C4, пинг)
- Оптическая сетка снайперского прицела AWP (при зуме ПКМ)
- Эффект ослепления светошумовой гранатой (Flashbang Whiteout) + виньетки урона/лечения
- Интерактивное меню закупки снаряжения CS2 по клавише B (12 позиций + баланс $ Cash)
- Полная таблица статистики матча по клавише Tab (K / D / HS% / Accuracy% / Damage / Роли ботов)
- Полоса обезвреживания C4 (клавиша E), анонсер серий убийств (FIRST BLOOD .. ACE!), пояс гранат и выносливость
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
    load_safe_texture,
    resolve_font_path,
    rgb32,
    rgba32,
)


class CS2HUD:
    """Управляет боевым 2D-интерфейсом, радаром, снайперским прицелом, меню закупки и таблицей счёта."""

    def __init__(self, on_buy_item: Callable[[str], None] | None = None) -> None:
        self.root = Entity(parent=camera.ui, enabled=False)
        self.on_buy_item = on_buy_item
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        # ── 1. ЭКРАННЫЕ ЭФФЕКТЫ: УРОН, ЛЕЧЕНИЕ И ОСЛЕПЛЕНИЕ FLASHBANG ──
        self._damage_alpha: float = 0.0
        self._heal_alpha: float = 0.0
        self._flashbang_alpha: float = 0.0

        self.damage_flash = Entity(
            parent=self.root,
            model="quad",
            scale=(2.4, 1.4),
            z=0.05,
            color=rgba32(215, 22, 22, 0),
        )
        self.heal_flash = Entity(
            parent=self.root,
            model="quad",
            scale=(2.4, 1.4),
            z=0.048,
            color=rgba32(45, 225, 115, 0),
        )
        self.flashbang_overlay = Entity(
            parent=self.root,
            model="quad",
            scale=(2.5, 1.5),
            z=-0.085,
            color=rgba32(255, 255, 255, 0),
        )

        # ── 2. СНАЙПЕРСКИЙ ОПТИЧЕСКИЙ ПРИЦЕЛ AWP ──
        self.scope_root = Entity(parent=self.root, z=-0.06, enabled=False)
        # Затемнённые поля вокруг линзы прицела
        Entity(parent=self.scope_root, model="quad", position=(-0.66, 0.0), scale=(0.68, 1.3), color=rgba32(6, 8, 12, 246))
        Entity(parent=self.scope_root, model="quad", position=(0.66, 0.0), scale=(0.68, 1.3), color=rgba32(6, 8, 12, 246))
        Entity(parent=self.scope_root, model="quad", position=(0.0, 0.44), scale=(0.66, 0.42), color=rgba32(6, 8, 12, 246))
        Entity(parent=self.scope_root, model="quad", position=(0.0, -0.44), scale=(0.66, 0.42), color=rgba32(6, 8, 12, 246))
        # Тонкие перекрестия и красная центральная точка дальномера
        Entity(parent=self.scope_root, model="quad", scale=(0.66, 0.0018), color=rgba32(15, 18, 22, 245), z=-0.01)
        Entity(parent=self.scope_root, model="quad", scale=(0.0018, 0.66), color=rgba32(15, 18, 22, 245), z=-0.01)
        Entity(parent=self.scope_root, model="quad", scale=(0.0055, 0.0055), color=rgb32(255, 48, 42), z=-0.02)

        # ── 3. ВРАЩАЮЩИЙСЯ 2D РАДАР-МИНИКАРТА (ЛЕВЫЙ ВЕРХНИЙ УГОЛ) ──
        self.radar_center = (-0.68, 0.355)
        self.radar_half = 0.098
        self.radar_bg = Entity(
            parent=self.root,
            model="quad",
            position=(self.radar_center[0], self.radar_center[1], 0.01),
            scale=(self.radar_half * 2.08, self.radar_half * 2.08),
            color=rgba32(10, 16, 22, 215),
        )
        Entity(
            parent=self.root,
            model="quad",
            position=(self.radar_center[0], self.radar_center[1], 0.005),
            scale=(self.radar_half * 2.0, self.radar_half * 2.0),
            color=rgba32(22, 34, 42, 210),
        )
        # Зелёная точка игрока в центре радара + луч взгляда
        Entity(
            parent=self.root,
            model="quad",
            position=(self.radar_center[0], self.radar_center[1] + 0.014, -0.015),
            scale=(0.003, 0.024),
            color=rgba32(95, 255, 155, 160),
        )
        Entity(
            parent=self.root,
            model="quad",
            position=(self.radar_center[0], self.radar_center[1], -0.02),
            scale=(0.009, 0.009),
            color=rgb32(85, 255, 135),
        )
        self.radar_site_a = self._make_text("A", pos=(self.radar_center[0], self.radar_center[1], -0.02), scale=0.62, col=rgb32(255, 185, 75))
        self.radar_site_b = self._make_text("B", pos=(self.radar_center[0], self.radar_center[1], -0.02), scale=0.62, col=rgb32(255, 185, 75))
        self.radar_c4_dot = Entity(
            parent=self.root,
            model="quad",
            scale=(0.012, 0.012),
            color=rgb32(255, 45, 45),
            z=-0.025,
            enabled=False,
        )
        self.radar_ping_dot = Entity(
            parent=self.root,
            model="quad",
            scale=(0.010, 0.010),
            color=rgb32(65, 235, 255),
            z=-0.024,
            enabled=False,
        )
        self.radar_enemy_dots: list[Entity] = [
            Entity(
                parent=self.root,
                model="quad",
                scale=(0.009, 0.009),
                color=rgb32(255, 62, 52),
                z=-0.022,
                enabled=False,
            )
            for _ in range(10)
        ]
        # Баланс денег $ под радаром
        self.cash_text = self._make_text(
            "$ 800",
            pos=(-0.68, 0.228),
            scale=1.08,
            col=rgb32(115, 242, 128),
        )
        self.buy_hint_text = self._make_text(
            "[B] BUY MENU   [F6] SKY   [F11] FULLSCREEN",
            pos=(-0.60, 0.196),
            scale=0.50,
            col=rgb32(168, 184, 204),
        )

        # ── 4. ВЕРХНЕЕ ТАБЛО РАУНДА И СЧЁТА (CT / ТАЙМЕР / T) ──
        self.top_bar = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.445),
            scale=(0.46, 0.078),
            color=rgba32(12, 16, 24, 220),
        )
        Entity(
            parent=self.root,
            model="quad",
            position=(-0.152, 0.445, -0.01),
            scale=(0.115, 0.064),
            color=rgba32(46, 108, 188, 225),
        )
        Entity(
            parent=self.root,
            model="quad",
            position=(0.152, 0.445, -0.01),
            scale=(0.115, 0.064),
            color=rgba32(198, 138, 42, 225),
        )
        self.ct_score_text = self._make_text("CT  0", pos=(-0.152, 0.446), scale=1.15, col=rgb32(225, 240, 255))
        self.timer_text = self._make_text("01:55", pos=(0.0, 0.456), scale=1.25, col=color.white)
        self.round_sub_text = self._make_text(
            "ROUND 1  |  ENEMIES: 5",
            pos=(0.0, 0.422),
            scale=0.64,
            col=rgb32(185, 195, 210),
        )
        self.t_score_text = self._make_text("0  T", pos=(0.152, 0.446), scale=1.15, col=rgb32(255, 244, 215))

        # Индикатор заложенной бомбы C4 и прогресс-бар обезвреживания (E)
        self.c4_alert_text = self._make_text(
            "",
            pos=(0.0, 0.375),
            scale=0.92,
            col=rgb32(255, 68, 58),
        )
        self.defuse_bar_bg = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, -0.14, -0.02),
            scale=(0.34, 0.024),
            color=rgba32(14, 18, 26, 225),
            enabled=False,
        )
        self.defuse_bar_fill = Entity(
            parent=self.defuse_bar_bg,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.49, 0.0, -0.01),
            scale=(0.01, 0.76),
            color=rgb32(75, 215, 255),
        )
        self.defuse_label = self._make_text(
            "DEFUSING C4 (HOLD E)...",
            pos=(0.0, -0.108),
            scale=0.72,
            col=rgb32(125, 228, 255),
        )
        self.defuse_label.enabled = False

        # ── 5. НИЖНЯЯ ЛЕВАЯ ПАНЕЛЬ: HP, ARMOR+HELMET, STAMINA & STIMSHOT ──
        Entity(
            parent=self.root,
            model="quad",
            position=(-0.55, -0.422),
            scale=(0.44, 0.108),
            color=rgba32(12, 16, 22, 215),
        )
        hp_tex = load_safe_texture("assets/textures/icon_hp.png")
        Entity(
            parent=self.root,
            model="quad",
            texture=hp_tex,
            position=(-0.73, -0.408, -0.01),
            scale=(0.034, 0.034),
            color=rgb32(110, 235, 165) if hp_tex is None else color.white,
        )
        self.hp_text = self._make_text("100", pos=(-0.655, -0.408), scale=1.55, col=color.white)
        Entity(parent=self.root, model="quad", position=(-0.675, -0.444, -0.01), scale=(0.14, 0.009), color=rgba32(55, 62, 72, 220))
        self.hp_bar = Entity(
            parent=self.root,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.745, -0.444, -0.02),
            scale=(0.14, 0.009),
            color=rgb32(95, 230, 145),
        )

        armor_tex = load_safe_texture("assets/textures/icon_armor.png")
        Entity(
            parent=self.root,
            model="quad",
            texture=armor_tex,
            position=(-0.53, -0.408, -0.01),
            scale=(0.034, 0.034),
            color=rgb32(95, 175, 255) if armor_tex is None else color.white,
        )
        self.armor_text = self._make_text("100", pos=(-0.455, -0.408), scale=1.55, col=rgb32(195, 225, 255))
        Entity(parent=self.root, model="quad", position=(-0.475, -0.444, -0.01), scale=(0.14, 0.009), color=rgba32(55, 62, 72, 220))
        self.armor_bar = Entity(
            parent=self.root,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.545, -0.444, -0.02),
            scale=(0.14, 0.009),
            color=rgb32(85, 170, 255),
        )

        # Нижняя полоска выносливости (Stamina) + индикатор стимулятора X и фонаря T
        self.gear_sub_text = self._make_text(
            "HELMET+KIT  |  [X] STIM: 1  |  [T] LIGHT  |  [Z] PING",
            pos=(-0.55, -0.464),
            scale=0.50,
            col=rgb32(172, 188, 206),
        )

        # ── 6. НИЖНЯЯ ПРАВАЯ ПАНЕЛЬ: ОРУЖИЕ, ПАТРОНЫ И ПОЯС ГРАНАТ ──
        Entity(
            parent=self.root,
            model="quad",
            position=(0.54, -0.418),
            scale=(0.46, 0.118),
            color=rgba32(12, 16, 22, 215),
        )
        self.weapon_name_text = self._make_text("AK-47", pos=(0.54, -0.376), scale=0.88, col=rgb32(245, 185, 66))
        self.ammo_text = self._make_text("30 / 90", pos=(0.54, -0.414), scale=1.52, col=color.white)
        self.grenade_belt_text = self._make_text(
            "[G] THROW: HE(1)  FLASH(1)  SMOKE(1)  MOLO(1)",
            pos=(0.54, -0.448),
            scale=0.52,
            col=rgb32(215, 226, 240),
        )
        self.slots_text = self._make_text(
            "[1] RIFLE  [2] PISTOL  [3] KNIFE  [6-0] ARSENAL  [F] INSPECT",
            pos=(0.54, -0.468),
            scale=0.47,
            col=rgb32(158, 172, 190),
        )

        # ── 7. ДИНАМИЧЕСКИЙ ПРИЦЕЛ CS2 (С ПЕРЕКЛЮЧЕНИЕМ ЦВЕТА НА F7) ──
        ch_col = rgb32(*CROSSHAIR_PALETTE[0][1])
        bar_len = 0.012
        bar_thick = 0.0024
        self.ch_top = Entity(parent=self.root, model="quad", scale=(bar_thick, bar_len), color=ch_col, z=-0.02)
        self.ch_bottom = Entity(parent=self.root, model="quad", scale=(bar_thick, bar_len), color=ch_col, z=-0.02)
        self.ch_left = Entity(parent=self.root, model="quad", scale=(bar_len, bar_thick), color=ch_col, z=-0.02)
        self.ch_right = Entity(parent=self.root, model="quad", scale=(bar_len, bar_thick), color=ch_col, z=-0.02)
        self.ch_dot = Entity(parent=self.root, model="quad", scale=(0.0026, 0.0026), color=ch_col, z=-0.02)
        self.update_crosshair(0.01)

        # ── 8. HITMARKER ──
        self._hitmarker_timer: float = 0.0
        self._hitmarker_headshot: bool = False
        self.hitmarker_bars: list[Entity] = []
        for (hx, hy), rot_z in [
            ((-0.011, 0.011), -45.0),
            ((0.011, 0.011), 45.0),
            ((-0.011, -0.011), 45.0),
            ((0.011, -0.011), -45.0),
        ]:
            bar = Entity(
                parent=self.root,
                model="quad",
                position=(hx, hy, -0.03),
                scale=(0.0024, 0.011),
                rotation_z=rot_z,
                color=rgba32(255, 255, 255, 0),
            )
            self.hitmarker_bars.append(bar)

        # ── 9. КИЛЛФИД + БАННЕРЫ СЕРИЙ УБИЙСТВ И УВЕДОМЛЕНИЙ ──
        self._killfeed_entries: list[tuple[str, float, bool]] = []
        self._killfeed_labels: list[Text] = []
        for idx in range(5):
            lbl = self._make_text("", pos=(0.56, 0.44 - idx * 0.036), scale=0.68, col=rgb32(245, 220, 165))
            self._killfeed_labels.append(lbl)

        self._streak_timer: float = 0.0
        self.streak_text = self._make_text("", pos=(0.0, 0.28, -0.03), scale=1.35, col=rgb32(255, 198, 62))
        self.streak_text.enabled = False

        self._notice_timer: float = 0.0
        self.notice_text = self._make_text("", pos=(0.0, -0.26, -0.03), scale=0.78, col=rgb32(195, 232, 255))
        self.notice_text.enabled = False

        # ── 10. ЦЕНТРАЛЬНЫЙ БАННЕР ИТОГОВ РАУНДА ──
        self.banner_box = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.16, -0.03),
            scale=(0.72, 0.13),
            color=rgba32(12, 16, 24, 230),
            enabled=False,
        )
        self.banner_title = self._make_text("", pos=(0.0, 0.18, -0.04), scale=1.52, col=rgb32(95, 185, 255))
        self.banner_sub = self._make_text("", pos=(0.0, 0.125, -0.04), scale=0.82, col=rgb32(215, 222, 232))
        self.banner_title.enabled = False
        self.banner_sub.enabled = False

        # ── 11. МЕНЮ ЗАКУПКИ СНАРЯЖЕНИЯ CS2 (КЛАВИША B) ──
        self.buy_panel = Entity(parent=self.root, z=-0.07, enabled=False)
        Entity(
            parent=self.buy_panel,
            model="quad",
            scale=(1.18, 0.72),
            color=rgba32(12, 16, 26, 238),
        )
        self.buy_title = self._make_parent_text(
            self.buy_panel,
            "CS2 TACTICAL BUY MENU  —  PRESS [B] TO CLOSE",
            pos=(0.0, 0.30, -0.01),
            scale=1.05,
            col=rgb32(245, 182, 56),
        )
        self.buy_buttons: list[Button] = []
        for i, item in enumerate(BUY_ITEMS):
            col_i = i % 3
            row_i = i // 3
            bx = -0.36 + col_i * 0.36
            by = 0.17 - row_i * 0.12
            item_id = str(item["id"])
            btn = Button(
                parent=self.buy_panel,
                text=f"{item['label']}\n${item['price']}",
                position=(bx, by, -0.015),
                scale=(0.33, 0.095),
                color=rgb32(32, 44, 62),
                highlight_color=rgb32(58, 92, 138),
                pressed_color=rgb32(228, 138, 28),
                on_click=(lambda iid=item_id: self._click_buy(iid)),
            )
            if self._font is not None and btn.text_entity is not None:
                try:
                    btn.text_entity.font = self._font
                except Exception:
                    pass
                btn.text_entity.scale *= 0.72
            self.buy_buttons.append(btn)

        # ── 12. ТАБЛИЦА СТАТИСТИКИ МАТЧА SCOREBOARD (КЛАВИША TAB) ──
        self.scoreboard_panel = Entity(parent=self.root, z=-0.075, enabled=False)
        Entity(
            parent=self.scoreboard_panel,
            model="quad",
            scale=(1.12, 0.68),
            color=rgba32(10, 14, 22, 236),
        )
        self.sb_header = self._make_parent_text(
            self.scoreboard_panel,
            "MATCH SCOREBOARD  (HOLD / PRESS TAB)",
            pos=(0.0, 0.28, -0.01),
            scale=1.08,
            col=rgb32(245, 185, 62),
        )
        self.sb_body = self._make_parent_text(
            self.scoreboard_panel,
            "",
            pos=(0.0, -0.02, -0.01),
            scale=0.72,
            col=rgb32(222, 232, 245),
        )

    def _make_text(
        self,
        content: str,
        pos: tuple[float, ...],
        scale: float = 1.0,
        col: Any = color.white,
    ) -> Text:
        return self._make_parent_text(self.root, content, pos, scale, col)

    def _make_parent_text(
        self,
        parent_ent: Entity,
        content: str,
        pos: tuple[float, ...],
        scale: float = 1.0,
        col: Any = color.white,
    ) -> Text:
        kwargs: dict[str, Any] = {
            "parent": parent_ent,
            "text": content,
            "origin": (0.0, 0.0),
            "scale": scale,
            "color": col,
        }
        if self._font is not None:
            try:
                txt = Text(**kwargs, font=self._font)
            except Exception:
                txt = Text(**kwargs)
        else:
            txt = Text(**kwargs)
        if len(pos) == 2:
            txt.position = (pos[0], pos[1], -0.02)
        else:
            txt.position = pos
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

    def apply_crosshair_color(self, palette_idx: int) -> str:
        name, rgb = CROSSHAIR_PALETTE[palette_idx % len(CROSSHAIR_PALETTE)]
        c = rgb32(*rgb)
        for part in (self.ch_top, self.ch_bottom, self.ch_left, self.ch_right, self.ch_dot):
            part.color = c
        return name

    def set_scope_visible(self, scoped: bool) -> None:
        self.scope_root.enabled = scoped
        for part in (self.ch_top, self.ch_bottom, self.ch_left, self.ch_right, self.ch_dot):
            part.enabled = not scoped

    def update_crosshair(self, spread: float) -> None:
        gap = clamp(0.008 + spread * 0.34, 0.007, 0.050)
        half_len = 0.006
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

    def flash_damage(self) -> None:
        self._damage_alpha = 120.0
        self.damage_flash.color = rgba32(215, 24, 24, int(self._damage_alpha))

    def flash_heal(self) -> None:
        self._heal_alpha = 95.0
        self.heal_flash.color = rgba32(45, 225, 115, int(self._heal_alpha))

    def trigger_flashbang(self, strength: float) -> None:
        """Запускает белое ослепление экрана (0.0 .. 1.0)."""
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
        self.banner_title.color = rgb32(95, 190, 255) if ct_won else rgb32(255, 165, 65)
        self.banner_sub.text = subtitle

    def hide_round_banner(self) -> None:
        self.banner_box.enabled = False
        self.banner_title.enabled = False
        self.banner_sub.enabled = False

    def _world_to_radar(self, wx: float, wz: float, px: float, pz: float, yaw_deg: float) -> tuple[float, float]:
        """Поворачивает мировые координаты вокруг игрока так, чтобы взгляд игрока на радаре всегда смотрел вверх."""
        dx = wx - px
        dz = wz - pz
        rad = math.radians(yaw_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        rx = dx * cos_a - dz * sin_a
        ry = -dx * sin_a + dz * cos_a
        scale = self.radar_half / 34.0
        ux = clamp(rx * scale, -self.radar_half * 0.92, self.radar_half * 0.92)
        uy = clamp(ry * scale, -self.radar_half * 0.92, self.radar_half * 0.92)
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

        for idx, dot in enumerate(self.radar_enemy_dots):
            if idx < len(bots):
                b = bots[idx]
                visible_on_radar = b.state != "DEAD" and (
                    b.state == "ATTACK"
                    or getattr(b, "recently_fired_timer", 0.0) > 0.0
                    or (b.world_position - player_pos).length() < 18.0
                )
                if visible_on_radar:
                    ex, ey = self._world_to_radar(b.x, b.z, player_pos.x, player_pos.z, player_yaw)
                    dot.position = (ex, ey, -0.022)
                    dot.enabled = True
                else:
                    dot.enabled = False
            else:
                dot.enabled = False

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
            f"CT  {ct_score}   :   {t_score}  TERRORISTS",
            "────────────────────────────────────────────────────────",
            f"[CT] YOU           K: {player_kills:<2d}  D: {player_deaths:<2d}  HS: {hs_pct:>3d}%   ACC: {acc:>3d}%   DMG: {total_dmg:<4d}  ${cash}",
            "────────────────────────────────────────────────────────",
        ]
        for b in bots:
            status = "DEAD" if b.state == "DEAD" else f"{b.hp} HP"
            lines.append(
                f"[T ] {b.bot_name:<12s} ({b.role:<6s})   K: {b.kills:<2d}  D: {b.deaths:<2d}   STATUS: {status}"
            )
        self.sb_body.text = "\n".join(lines)

    def sync_stats(
        self,
        hp: int,
        armor: int,
        weapon_id: str,
        weapon_display_name: str,
        ammo_mag: int,
        ammo_reserve: int,
        is_reloading: bool,
        ct_score: int,
        t_score: int,
        round_num: int,
        time_left: float,
        alive_bots: int,
        spread: float,
        cash: int = 800,
        grenades: dict[str, int] | None = None,
        selected_grenade: str = "he",
        stimshots: int = 1,
        flashlight_on: bool = False,
        is_scoped: bool = False,
        burst_active: bool = False,
        c4_planted: bool = False,
        c4_site: str = "",
        c4_timer: float = 0.0,
        defuse_progress: float = 0.0,
    ) -> None:
        self.hp_text.text = str(max(0, hp))
        self.hp_text.color = rgb32(255, 75, 70) if hp <= 25 else color.white
        self.hp_bar.scale_x = max(0.001, 0.14 * clamp(hp / 100.0, 0.0, 1.0))
        self.hp_bar.color = rgb32(255, 75, 70) if hp <= 25 else rgb32(95, 230, 145)

        self.armor_text.text = str(max(0, armor))
        self.armor_bar.scale_x = max(0.001, 0.14 * clamp(armor / 100.0, 0.0, 1.0))

        self.cash_text.text = f"$ {cash}"
        light_tag = "ON" if flashlight_on else "OFF"
        self.gear_sub_text.text = f"HELMET+KIT  |  [X] STIM: {stimshots}  |  [T] LIGHT: {light_tag}  |  [Q/E] LEAN"

        mode_suffix = " [BURST]" if burst_active else ""
        if is_reloading:
            self.weapon_name_text.text = f"{weapon_display_name}{mode_suffix}  (RELOADING...)"
            self.weapon_name_text.color = rgb32(255, 215, 90)
        else:
            self.weapon_name_text.text = f"{weapon_display_name}{mode_suffix}"
            self.weapon_name_text.color = rgb32(245, 185, 66)

        if ammo_mag < 0:
            self.ammo_text.text = "LMB SLASH / RMB STAB"
            self.ammo_text.color = rgb32(210, 225, 240)
        else:
            self.ammo_text.text = f"{ammo_mag} / {ammo_reserve}"
            self.ammo_text.color = rgb32(255, 95, 80) if ammo_mag <= 5 else color.white

        if grenades is not None:
            g_parts = []
            for gid in GRENADE_ORDER:
                cnt = grenades.get(gid, 0)
                short = GRENADE_SPECS[gid]["short"]
                lbl = f"{short}({cnt})"
                g_parts.append(f">{lbl}<" if gid == selected_grenade else lbl)
            self.grenade_belt_text.text = "[G] THROW / [V] NEXT:  " + "  ".join(g_parts)

        self.ct_score_text.text = f"CT  {ct_score}"
        self.t_score_text.text = f"{t_score}  T"

        if c4_planted:
            self.timer_text.text = f"C4 {c4_timer:04.1f}s"
            self.timer_text.color = rgb32(255, 65, 55)
            self.c4_alert_text.text = f"⚠ BOMB PLANTED AT SITE {c4_site}! HOLD [E] NEAR C4 TO DEFUSE!"
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

        self.round_sub_text.text = f"ROUND {round_num}   |   ENEMIES: {alive_bots}   |   [TAB] SCORE"
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
