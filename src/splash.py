"""
Анимированная кинематографичная заставка запуска игры (Cinematic Intro Splash):
«Игра сделана уважаемым алкодимасом, для усатого Эльдара»
Включает пружинящую 2D/3D эмблему золотых гусарских усов и щита спецназа, летящие искры,
неоновый лазерный сканлайн, эффект печатной машинки, шкалу инициализации шейдеров и фанфару!
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from ursina import Entity, Text, camera, clamp, color

from src.settings import SoundManager, resolve_font_path, rgb32, rgba32


class IntroSplashScreen:
    """Управляет полноэкранной анимированной заставкой при старте игры и по кнопке повтора из меню."""

    DURATION: float = 4.6

    def __init__(self, sound_mgr: SoundManager, on_finished: Callable[[], None]) -> None:
        self.sound_mgr = sound_mgr
        self.on_finished = on_finished
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        self.active: bool = False
        self.elapsed: float = 0.0

        self.root = Entity(parent=camera.ui, z=-0.12, enabled=False, add_to_scene_entities=False)

        # 1. Глубокий обсидиановый фон + кинематографичные золотые рамки
        self.backdrop = Entity(
            parent=self.root,
            model="quad",
            scale=(2.4, 1.45),
            z=0.04,
            color=rgba32(7, 10, 17, 255),
            add_to_scene_entities=False,
        )
        self.top_bar = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.46, 0.02),
            scale=(2.2, 0.08),
            color=rgba32(4, 6, 10, 255),
            add_to_scene_entities=False,
        )
        self.bot_bar = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, -0.46, 0.02),
            scale=(2.2, 0.08),
            color=rgba32(4, 6, 10, 255),
            add_to_scene_entities=False,
        )
        self.top_gold_line = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.418, 0.015),
            scale=(0.01, 0.0035),
            color=rgb32(255, 184, 48),
            add_to_scene_entities=False,
        )
        self.bot_gold_line = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, -0.418, 0.015),
            scale=(0.01, 0.0035),
            color=rgb32(65, 215, 255),
            add_to_scene_entities=False,
        )

        # Неоновый бегущий луч-сканер
        self.scan_beam = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, 0.35, 0.025),
            scale=(1.65, 0.005),
            color=rgba32(255, 195, 65, 95),
            add_to_scene_entities=False,
        )

        # 2. Летящие золотые и голубые искры на фоне (24 частицы)
        rng = random.Random(777)
        self.sparks: list[dict[str, Any]] = []
        for i in range(24):
            is_gold = (i % 3) != 0
            sp_ent = Entity(
                parent=self.root,
                model="quad",
                position=(rng.uniform(-0.82, 0.82), rng.uniform(-0.40, 0.40), 0.03),
                scale=(rng.uniform(0.005, 0.012), rng.uniform(0.005, 0.012)),
                rotation_z=45.0,
                color=rgba32(255, 192, 62, 175) if is_gold else rgba32(72, 215, 255, 165),
                add_to_scene_entities=False,
            )
            self.sparks.append(
                {
                    "ent": sp_ent,
                    "vx": rng.uniform(-0.04, 0.04),
                    "vy": rng.uniform(0.05, 0.14),
                    "phase": rng.uniform(0.0, 6.28),
                }
            )

        # 3. ЦЕНТРАЛЬНЫЙ ГЕРБ: Щит Спецназа + Фирменные Золотые Гусарские Усы Эльдара!
        self.emblem_pivot = Entity(
            parent=self.root,
            position=(0.0, 0.165, 0.01),
            scale=0.01,
            add_to_scene_entities=False,
        )
        # Ромбовидный тактический щит с двойной окантовкой
        Entity(
            parent=self.emblem_pivot,
            model="quad",
            scale=(0.175, 0.175),
            rotation_z=45.0,
            z=0.008,
            color=rgb32(255, 182, 42),
            add_to_scene_entities=False,
        )
        Entity(
            parent=self.emblem_pivot,
            model="quad",
            scale=(0.158, 0.158),
            rotation_z=45.0,
            z=0.006,
            color=rgb32(14, 22, 36),
            add_to_scene_entities=False,
        )
        # Звезда / корона над усами внутри герба
        Entity(
            parent=self.emblem_pivot,
            model="quad",
            position=(0.0, 0.046, 0.003),
            scale=(0.026, 0.026),
            rotation_z=45.0,
            color=rgb32(75, 225, 255),
            add_to_scene_entities=False,
        )
        # Пышные симметричные золотые усы с подкрученными кончиками!
        self.mustache_root = Entity(parent=self.emblem_pivot, position=(0.0, -0.012, 0.002), add_to_scene_entities=False)
        for sign in (-1.0, 1.0):
            # Основание уса у центра
            Entity(
                parent=self.mustache_root,
                model="quad",
                position=(sign * 0.030, 0.006, 0.0),
                scale=(0.068, 0.026),
                rotation_z=sign * -14.0,
                color=rgb32(255, 196, 56),
                add_to_scene_entities=False,
            )
            # Изгиб крыла уса
            Entity(
                parent=self.mustache_root,
                model="quad",
                position=(sign * 0.078, -0.002, -0.001),
                scale=(0.062, 0.020),
                rotation_z=sign * 16.0,
                color=rgb32(242, 172, 36),
                add_to_scene_entities=False,
            )
            # Лихо закрученный вверх кончик уса!
            Entity(
                parent=self.mustache_root,
                model="quad",
                position=(sign * 0.114, 0.018, -0.002),
                scale=(0.032, 0.014),
                rotation_z=sign * 52.0,
                color=rgb32(255, 218, 92),
                add_to_scene_entities=False,
            )

        # 4. АНИМИРОВАННАЯ ТИПОГРАФИКА ПОСВЯЩЕНИЯ
        self._full_line_1 = "Игра сделана уважаемым алкодимасом,"
        self._full_line_2 = "для усатого Эльдара"

        self.badge_txt = self._make_txt(
            "★  CS2 TACTICAL 3D ENGINE  •  COLLECTOR'S EDITION  ★",
            pos=(0.0, 0.345, 0.0),
            scale=0.72,
            col=rgb32(95, 222, 255),
        )
        self.line1_txt = self._make_txt(
            "",
            pos=(0.0, -0.035, 0.0),
            scale=1.42,
            col=rgb32(244, 248, 255),
        )
        self.line2_txt = self._make_txt(
            "",
            pos=(0.0, -0.118, 0.0),
            scale=1.72,
            col=rgb32(255, 192, 52),
        )
        self.sub_dedication = self._make_txt(
            "100+ ДОБАВЛЕНИЙ  •  PBR 3D GRAPHICS  •  ULTRA OPTIMIZED",
            pos=(0.0, -0.205, 0.0),
            scale=0.62,
            col=rgb32(168, 188, 214),
        )

        # 5. ШКАЛА ЗАГРУЗКИ ШЕЙДЕРОВ И ПОДСКАЗКА ПРОПУСКА
        self.prog_bg = Entity(
            parent=self.root,
            model="quad",
            position=(0.0, -0.31, 0.005),
            scale=(0.64, 0.014),
            color=rgba32(26, 36, 52, 235),
            add_to_scene_entities=False,
        )
        self.prog_fill = Entity(
            parent=self.prog_bg,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.5, 0.0, -0.005),
            scale=(0.001, 0.86),
            color=rgb32(255, 182, 42),
            add_to_scene_entities=False,
        )
        self.prog_txt = self._make_txt(
            "ЗАГРУЗКА 3D-МОДЕЛЕЙ И ШЕЙДЕРОВ... 0%",
            pos=(0.0, -0.282, 0.0),
            scale=0.52,
            col=rgb32(205, 218, 235),
        )
        self.skip_txt = self._make_txt(
            "[ ПРОБЕЛ / ENTER / ЛКМ — ПРОПУСТИТЬ ЗАСТАВКУ ]",
            pos=(0.0, -0.365, 0.0),
            scale=0.52,
            col=rgb32(138, 156, 180),
        )

    def _make_txt(self, text_val: str, pos: tuple[float, float, float], scale: float, col: Any) -> Text:
        kwargs: dict[str, Any] = {
            "parent": self.root,
            "text": text_val,
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

    def start(self) -> None:
        self.elapsed = 0.0
        self.active = True
        self.line1_txt.text = ""
        self.line2_txt.text = ""
        self.emblem_pivot.scale = 0.01
        self.top_gold_line.scale_x = 0.01
        self.bot_gold_line.scale_x = 0.01
        self.prog_fill.scale_x = 0.001
        self.root.enabled = True
        self.sound_mgr.stop_menu_music()
        self.sound_mgr.play_sfx("intro_fanfare", volume=0.92)

    def skip(self) -> None:
        if not self.active:
            return
        self.active = False
        self.root.enabled = False
        self.on_finished()

    def update(self, dt: float) -> None:
        if not self.active:
            return

        self.elapsed += dt
        t = self.elapsed

        # 1. Раздвижение неоново-золотых линий рамки
        line_w = clamp(t / 0.65, 0.0, 1.0) * 1.62
        self.top_gold_line.scale_x = max(0.01, line_w)
        self.bot_gold_line.scale_x = max(0.01, line_w)

        # 2. Пружинящий вылет эмблемы с золотыми усами
        if t < 0.75:
            p = t / 0.75
            overshoot = 1.0 + 0.24 * math.sin(p * math.pi) * (1.0 - p * 0.5)
            sc = clamp(p * 1.15, 0.01, 1.0) * overshoot
        else:
            sc = 1.0 + 0.035 * math.sin((t - 0.75) * 3.8)
        self.emblem_pivot.scale = sc
        self.mustache_root.rotation_z = math.sin(t * 4.5) * 3.2

        # 3. Движение сканера и искр
        self.scan_beam.y = math.sin(t * 2.1) * 0.36
        for sp in self.sparks:
            ent = sp["ent"]
            ent.y += sp["vy"] * dt
            ent.x += (sp["vx"] + math.sin(t * 3.0 + sp["phase"]) * 0.025) * dt
            ent.rotation_z += dt * 95.0
            if ent.y > 0.41:
                ent.y = -0.41

        # 4. Печатная машинка для «Игра сделана уважаемым алкодимасом,» (0.35s .. 1.65s)
        if t >= 0.32:
            c1 = int(clamp((t - 0.32) / 1.25, 0.0, 1.0) * len(self._full_line_1))
            self.line1_txt.text = self._full_line_1[:c1]

        # 5. Эффектное проявление «для усатого Эльдара» (1.65s .. 2.55s) + пульсация золота
        if t >= 1.62:
            c2 = int(clamp((t - 1.62) / 0.78, 0.0, 1.0) * len(self._full_line_2))
            self.line2_txt.text = self._full_line_2[:c2]
            pulse = 1.72 + 0.07 * math.sin((t - 1.62) * 5.2)
            self.line2_txt.scale = pulse
            glow_g = int(clamp(186 + 34 * math.sin(t * 6.0), 150, 235))
            self.line2_txt.color = rgb32(255, glow_g, 52)

        # 6. Прогресс-бар загрузки
        pct = clamp(t / (self.DURATION - 0.35), 0.0, 1.0)
        self.prog_fill.scale_x = max(0.005, pct)
        stage_label = (
            "ИНИЦИАЛИЗАЦИЯ PBR-ШЕЙДЕРОВ..."
            if pct < 0.38
            else ("БАТЧИНГ 3D-ГЕОМЕТРИИ КАРТЫ..." if pct < 0.75 else "ГОТОВНОСТЬ К БОЮ!")
        )
        self.prog_txt.text = f"{stage_label}  {int(round(pct * 100))}%"

        if self.elapsed >= self.DURATION:
            self.skip()
