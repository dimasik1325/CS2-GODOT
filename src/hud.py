"""
Боевой интерфейс игрока (HUD) в стиле Counter-Strike 2:
- Динамический крестовой прицел CS2 (расширяется при стрельбе, беге и прыжках)
- Хитмаркер попаданий (белый — корпус, алый — Headshot)
- Панели здоровья (HP) и брони (Kevlar) с PNG-иконками (и fallback)
- Счётчик патронов, индикатор перезарядки и полоска слотов оружия (1–4)
- Верхнее табло раундов (счёт CT : T, таймер MM:SS, число живых врагов)
- Киллфид в правом верхнем углу, виньетка урона и баннер конца раунда
"""

from __future__ import annotations

from typing import Any

from ursina import Entity, Text, camera, clamp, color

from src.settings import load_safe_texture, resolve_font_path


class CS2HUD:
    """Управляет всеми 2D-элементами боевого интерфейса (camera.ui)."""

    def __init__(self) -> None:
        self.root = Entity(parent=camera.ui, enabled=False)
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        # ── 1. КРАСНАЯ ВИНЬЕТКА ПОЛУЧЕНИЯ УРОНА ──
        self._damage_alpha: float = 0.0
        self.damage_flash = Entity(
            parent=self.root,
            model="quad",
            scale=(2.2, 1.3),
            z=0.05,
            color=color.rgba(210, 20, 20, 0),
        )

        # ── 2. ВЕРХНЕЕ ТАБЛО РАУНДА И СЧЁТА (CT / ТАЙМЕР / T) ──
        self.top_bar = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.445),
            scale=(0.44, 0.075),
            color=color.rgba(14, 18, 24, 215),
        )
        # Плашка счёта CT (слева)
        Entity(
            parent=self.root,
            model="quad",
            position=(-0.145, 0.445, -0.01),
            scale=(0.11, 0.062),
            color=color.rgba(48, 108, 185, 220),
        )
        # Плашка счёта T (справа)
        Entity(
            parent=self.root,
            model="quad",
            position=(0.145, 0.445, -0.01),
            scale=(0.11, 0.062),
            color=color.rgba(196, 138, 42, 220),
        )

        self.ct_score_text = self._make_text(
            "CT  0", pos=(-0.145, 0.446), scale=1.15, col=color.rgb(225, 240, 255)
        )
        self.timer_text = self._make_text(
            "01:45", pos=(0.0, 0.456), scale=1.25, col=color.white
        )
        self.round_sub_text = self._make_text(
            "ROUND 1  |  ENEMIES: 5",
            pos=(0.0, 0.422),
            scale=0.68,
            col=color.rgb(185, 195, 210),
        )
        self.t_score_text = self._make_text(
            "0  T", pos=(0.145, 0.446), scale=1.15, col=color.rgb(255, 244, 215)
        )

        # ── 3. НИЖНЯЯ ЛЕВАЯ ПАНЕЛЬ: HP И ARMOR ──
        Entity(
            parent=self.root,
            model="quad",
            position=(-0.56, -0.425),
            scale=(0.40, 0.095),
            color=color.rgba(12, 16, 22, 210),
        )
        hp_tex = load_safe_texture("assets/textures/icon_hp.png")
        Entity(
            parent=self.root,
            model="quad",
            texture=hp_tex,
            position=(-0.72, -0.415, -0.01),
            scale=(0.036, 0.036),
            color=color.rgb(110, 235, 165) if hp_tex is None else color.white,
        )
        self.hp_text = self._make_text(
            "100", pos=(-0.645, -0.415), scale=1.65, col=color.white
        )
        Entity(
            parent=self.root,
            model="quad",
            position=(-0.665, -0.455, -0.01),
            scale=(0.14, 0.010),
            color=color.rgba(55, 62, 72, 220),
        )
        self.hp_bar = Entity(
            parent=self.root,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.735, -0.455, -0.02),
            scale=(0.14, 0.010),
            color=color.rgb(95, 230, 145),
        )

        armor_tex = load_safe_texture("assets/textures/icon_armor.png")
        Entity(
            parent=self.root,
            model="quad",
            texture=armor_tex,
            position=(-0.52, -0.415, -0.01),
            scale=(0.036, 0.036),
            color=color.rgb(95, 175, 255) if armor_tex is None else color.white,
        )
        self.armor_text = self._make_text(
            "100", pos=(-0.445, -0.415), scale=1.65, col=color.rgb(195, 225, 255)
        )
        Entity(
            parent=self.root,
            model="quad",
            position=(-0.465, -0.455, -0.01),
            scale=(0.14, 0.010),
            color=color.rgba(55, 62, 72, 220),
        )
        self.armor_bar = Entity(
            parent=self.root,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.535, -0.455, -0.02),
            scale=(0.14, 0.010),
            color=color.rgb(85, 170, 255),
        )

        # ── 4. НИЖНЯЯ ПРАВАЯ ПАНЕЛЬ: ПАТРОНЫ И СЛОТЫ ОРУЖИЯ ──
        Entity(
            parent=self.root,
            model="quad",
            position=(0.56, -0.420),
            scale=(0.42, 0.110),
            color=color.rgba(12, 16, 22, 210),
        )
        self.weapon_name_text = self._make_text(
            "AK-47", pos=(0.56, -0.382), scale=0.92, col=color.rgb(245, 185, 66)
        )
        self.ammo_text = self._make_text(
            "30 / 90", pos=(0.56, -0.422), scale=1.60, col=color.white
        )
        self.slots_text = self._make_text(
            "[1] AK-47   [2] DEAGLE   [3] KNIFE   [4] M4A1-S",
            pos=(0.56, -0.460),
            scale=0.58,
            col=color.rgb(170, 182, 198),
        )

        # ── 5. ДИНАМИЧЕСКИЙ ПРИЦЕЛ CS2 (4 РИСКИ + ЦЕНТРАЛЬНАЯ ТОЧКА) ──
        ch_col = color.rgb(65, 255, 130)
        bar_len = 0.012
        bar_thick = 0.0024
        self.ch_top = Entity(parent=self.root, model="quad", scale=(bar_thick, bar_len), color=ch_col, z=-0.02)
        self.ch_bottom = Entity(parent=self.root, model="quad", scale=(bar_thick, bar_len), color=ch_col, z=-0.02)
        self.ch_left = Entity(parent=self.root, model="quad", scale=(bar_len, bar_thick), color=ch_col, z=-0.02)
        self.ch_right = Entity(parent=self.root, model="quad", scale=(bar_len, bar_thick), color=ch_col, z=-0.02)
        self.ch_dot = Entity(parent=self.root, model="quad", scale=(0.0026, 0.0026), color=ch_col, z=-0.02)
        self.update_crosshair(0.01)

        # ── 6. HITMARKER (4 ДИАГОНАЛЬНЫХ ЛУЧА ПОПАДАНИЯ) ──
        self._hitmarker_timer: float = 0.0
        self._hitmarker_headshot: bool = False
        self.hitmarker_bars: list[Entity] = []
        hm_offsets = [
            ((-0.011, 0.011), -45.0),
            ((0.011, 0.011), 45.0),
            ((-0.011, -0.011), 45.0),
            ((0.011, -0.011), -45.0),
        ]
        for (hx, hy), rot_z in hm_offsets:
            bar = Entity(
                parent=self.root,
                model="quad",
                position=(hx, hy, -0.03),
                scale=(0.0024, 0.011),
                rotation_z=rot_z,
                color=color.rgba(255, 255, 255, 0),
            )
            self.hitmarker_bars.append(bar)

        # ── 7. КИЛЛФИД (ПРАВЫЙ ВЕРХНИЙ УГОЛ) ──
        self._killfeed_entries: list[tuple[str, float, bool]] = []
        self._killfeed_labels: list[Text] = []
        for idx in range(4):
            lbl = self._make_text(
                "",
                pos=(0.56, 0.44 - idx * 0.038),
                scale=0.72,
                col=color.rgb(245, 220, 165),
            )
            self._killfeed_labels.append(lbl)

        # ── 8. ЦЕНТРАЛЬНЫЙ БАННЕР ИТОГОВ РАУНДА ──
        self.banner_box = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.16, -0.03),
            scale=(0.68, 0.13),
            color=color.rgba(12, 16, 24, 228),
            enabled=False,
        )
        self.banner_title = self._make_text(
            "", pos=(0.0, 0.18, -0.04), scale=1.55, col=color.rgb(95, 185, 255)
        )
        self.banner_sub = self._make_text(
            "", pos=(0.0, 0.125, -0.04), scale=0.85, col=color.rgb(215, 222, 232)
        )
        self.banner_title.enabled = False
        self.banner_sub.enabled = False

    def _make_text(
        self,
        content: str,
        pos: tuple[float, ...],
        scale: float = 1.0,
        col: Any = color.white,
    ) -> Text:
        kwargs: dict[str, Any] = {
            "parent": self.root,
            "text": content,
            "origin": (0.0, 0.0),
            "scale": scale,
            "color": col,
        }
        if self._font is not None:
            kwargs["font"] = self._font
        txt = Text(**kwargs)
        if len(pos) == 2:
            txt.position = (pos[0], pos[1], -0.02)
        else:
            txt.position = pos
        return txt

    def set_visible(self, visible: bool) -> None:
        self.root.enabled = visible

    def update_crosshair(self, spread: float) -> None:
        """Раздвигает риски прицела пропорционально текущему разбросу оружия."""
        gap = clamp(0.008 + spread * 0.34, 0.007, 0.048)
        half_len = 0.006
        self.ch_top.position = (0.0, gap + half_len, -0.02)
        self.ch_bottom.position = (0.0, -(gap + half_len), -0.02)
        self.ch_left.position = (-(gap + half_len), 0.0, -0.02)
        self.ch_right.position = (gap + half_len, 0.0, -0.02)

    def show_hitmarker(self, is_headshot: bool = False) -> None:
        """Показывает перекрестие попадания (красное для Headshot, белое для обычного попадания)."""
        self._hitmarker_timer = 0.18
        self._hitmarker_headshot = is_headshot
        col = color.rgba(255, 62, 48, 255) if is_headshot else color.rgba(255, 255, 255, 245)
        for bar in self.hitmarker_bars:
            bar.color = col

    def flash_damage(self) -> None:
        """Кратковременная красная вспышка экрана при получении урона игроком."""
        self._damage_alpha = 115.0
        self.damage_flash.color = color.rgba(215, 24, 24, int(self._damage_alpha))

    def push_killfeed(self, weapon_name: str, victim_name: str, is_headshot: bool) -> None:
        hs_tag = " [HS]" if is_headshot else ""
        line = f"YOU  [{weapon_name}{hs_tag}]  {victim_name}"
        self._killfeed_entries.insert(0, (line, 4.8, is_headshot))
        self._killfeed_entries = self._killfeed_entries[:4]
        self._refresh_killfeed_ui()

    def clear_killfeed(self) -> None:
        self._killfeed_entries.clear()
        self._refresh_killfeed_ui()

    def _refresh_killfeed_ui(self) -> None:
        for idx, lbl in enumerate(self._killfeed_labels):
            if idx < len(self._killfeed_entries):
                text_str, _, is_hs = self._killfeed_entries[idx]
                lbl.text = text_str
                lbl.color = color.rgb(255, 110, 95) if is_hs else color.rgb(245, 224, 175)
            else:
                lbl.text = ""

    def show_round_banner(self, title: str, subtitle: str, ct_won: bool = True) -> None:
        self.banner_box.enabled = True
        self.banner_title.enabled = True
        self.banner_sub.enabled = True
        self.banner_title.text = title
        self.banner_title.color = color.rgb(95, 190, 255) if ct_won else color.rgb(255, 165, 65)
        self.banner_sub.text = subtitle

    def hide_round_banner(self) -> None:
        self.banner_box.enabled = False
        self.banner_title.enabled = False
        self.banner_sub.enabled = False

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
    ) -> None:
        """Синхронизирует все численные индикаторы HUD за один вызов."""
        # HP & Armor
        self.hp_text.text = str(max(0, hp))
        self.hp_text.color = color.rgb(255, 75, 70) if hp <= 25 else color.white
        self.hp_bar.scale_x = max(0.001, 0.14 * clamp(hp / 100.0, 0.0, 1.0))
        self.hp_bar.color = color.rgb(255, 75, 70) if hp <= 25 else color.rgb(95, 230, 145)

        self.armor_text.text = str(max(0, armor))
        self.armor_bar.scale_x = max(0.001, 0.14 * clamp(armor / 100.0, 0.0, 1.0))

        # Оружие и боезапас
        if is_reloading:
            self.weapon_name_text.text = f"{weapon_display_name}  (RELOADING...)"
            self.weapon_name_text.color = color.rgb(255, 215, 90)
        else:
            self.weapon_name_text.text = weapon_display_name
            self.weapon_name_text.color = color.rgb(245, 185, 66)

        if ammo_mag < 0:
            self.ammo_text.text = "MELEE"
            self.ammo_text.color = color.rgb(210, 225, 240)
        else:
            self.ammo_text.text = f"{ammo_mag} / {ammo_reserve}"
            self.ammo_text.color = color.rgb(255, 95, 80) if ammo_mag <= 5 else color.white

        slot_labels = [
            ("ak47", "[1] AK-47"),
            ("deagle", "[2] DEAGLE"),
            ("knife", "[3] KNIFE"),
            ("m4a1", "[4] M4A1-S"),
        ]
        parts = [f"> {lbl} <" if wid == weapon_id else lbl for wid, lbl in slot_labels]
        self.slots_text.text = "  ".join(parts)

        # Верхняя панель раунда
        self.ct_score_text.text = f"CT  {ct_score}"
        self.t_score_text.text = f"{t_score}  T"

        secs_total = max(0, int(time_left))
        mm, ss = divmod(secs_total, 60)
        self.timer_text.text = f"{mm:02d}:{ss:02d}"
        self.timer_text.color = color.rgb(255, 85, 75) if secs_total <= 15 else color.white
        self.round_sub_text.text = f"ROUND {round_num}   |   ENEMIES: {alive_bots}"

        self.update_crosshair(spread)

    def update(self, dt: float) -> None:
        """Плавное затухание хитмаркера, виньетки урона и записей киллфида."""
        if self._hitmarker_timer > 0.0:
            self._hitmarker_timer = max(0.0, self._hitmarker_timer - dt)
            alpha = int(255.0 * (self._hitmarker_timer / 0.18))
            col = (
                color.rgba(255, 62, 48, alpha)
                if self._hitmarker_headshot
                else color.rgba(255, 255, 255, alpha)
            )
            for bar in self.hitmarker_bars:
                bar.color = col

        if self._damage_alpha > 0.0:
            self._damage_alpha = max(0.0, self._damage_alpha - dt * 310.0)
            self.damage_flash.color = color.rgba(215, 24, 24, int(self._damage_alpha))

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
