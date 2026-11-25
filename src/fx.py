"""
Движок 3D-спецэффектов, баллистики и тактических гаджетов CS2:
- Физические латунные гильзы с отскоком от пола и металлическим звоном
- 3D-трассеры пуль, динамический свет вспышек/взрывов и частицы материалов (камень, дерево, металл, кровь)
- Всплывающие 3D-индикаторы урона (Damage Numbers)
- Физические 3D-гранаты с отскоком от стен: Осколочная (HE), Светошумовая (Flashbang с учётом отворота камеры!),
  Дымовая завеса (Smoke, перекрывающая обзор ботам и тушащая огонь!) и Коктейль Молотова (горящая зона)
- Интерактивная бомба C4 (установка на плентах A/B, ускоряющийся таймер и писк, обезвреживание по клавише E, взрыв)
- Подбираемые трофеи с врагов (аптечки, бронепластины, патроны, пачки денег) и 3D тактическая метка (Ping на Z)
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from ursina import Entity, PointLight, Text, Vec3, camera, clamp, color, destroy, lerp, raycast

from src.settings import (
    GRENADE_SPECS,
    SoundManager,
    apply_pbr_material,
    load_safe_model,
    resolve_font_path,
    rgb32,
    rgba32,
)


@dataclass
class ShellCasing:
    entity: Entity
    vel: Vec3
    rot_vel: Vec3
    ttl: float
    bounced: bool = False


@dataclass
class ParticleItem:
    entity: Entity
    vel: Vec3
    gravity: float
    ttl: float
    max_ttl: float
    shrink: bool = True


@dataclass
class DamagePopup:
    entity: Text
    vel_y: float
    ttl: float


@dataclass
class GrenadeInstance:
    grenade_type: str
    entity: Entity
    vel: Vec3
    fuse: float
    bounces: int = 0


@dataclass
class SmokeCloud:
    center: Vec3
    radius: float
    ttl: float
    puffs: list[Entity]


@dataclass
class FireZone:
    center: Vec3
    radius: float
    ttl: float
    tick_timer: float
    flames: list[Entity]
    scorch: Entity


@dataclass
class LootDrop:
    kind: str  # medkit | armor | ammo | cash
    entity: Entity
    pos: Vec3
    ttl: float
    phase: float


class FXManager:
    """Централизованный менеджер всех 3D-эффектов, гранат, C4, разрушаемых бочек и трофеев."""

    def __init__(self, sound_mgr: SoundManager) -> None:
        self.sound_mgr = sound_mgr
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        self.root = Entity(name="fx_world_root")

        # Переиспользуемый динамический источник света для выстрелов, взрывов, огня и C4
        self.dynamic_light = PointLight(
            parent=self.root,
            position=(0.0, -50.0, 0.0),
            color=rgb32(0, 0, 0),
        )
        try:
            self.dynamic_light._light.setAttenuation((1.0, 0.09, 0.032))
        except Exception:
            pass
        self._dyn_light_timer: float = 0.0

        self.shells: deque[ShellCasing] = deque(maxlen=28)
        self.particles: list[ParticleItem] = []
        self.popups: list[DamagePopup] = []
        self.grenades: list[GrenadeInstance] = []
        self.smokes: list[SmokeCloud] = []
        self.fires: list[FireZone] = []
        self.loot_drops: list[LootDrop] = []
        self.scorch_decals: deque[Entity] = deque(maxlen=18)

        # ── СОСТОЯНИЕ БОМБЫ C4 ──
        self.c4_planted: bool = False
        self.c4_defused: bool = False
        self.c4_exploded: bool = False
        self.c4_site_name: str = ""
        self.c4_pos: Vec3 = Vec3(0.0, 0.0, 0.0)
        self.c4_timer: float = 40.0
        self.c4_beep_cooldown: float = 1.0
        self.c4_defuse_progress: float = 0.0
        self.c4_entity: Entity | None = None
        self.c4_led: Entity | None = None

        # ── 3D ТАКТИЧЕСКИЙ ПИНГ (КЛАВИША Z / СКМ) ──
        self.ping_entity: Entity | None = None
        self.ping_label: Text | None = None
        self.ping_pos: Vec3 | None = None
        self.ping_timer: float = 0.0

        # Колбэки взаимодействия с миром (подключаются из контроллера матча)
        self.on_explosion_damage: Callable[[Vec3, float, float, str], None] | None = None
        self.on_flashbang_pop: Callable[[Vec3], None] | None = None
        self.on_fire_tick: Callable[[Vec3, float], None] | None = None
        self.on_c4_exploded: Callable[[], None] | None = None
        self.on_c4_defused: Callable[[], None] | None = None

    def pulse_dynamic_light(
        self,
        pos: Vec3,
        rgb: tuple[int, int, int],
        duration: float = 0.06,
    ) -> None:
        """Мгновенная 3D-вспышка света на стенах и полу от выстрела или взрыва."""
        self.dynamic_light.position = pos
        self.dynamic_light.color = rgb32(*rgb)
        self._dyn_light_timer = max(self._dyn_light_timer, duration)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. ГИЛЬЗЫ, ТРАССЕРЫ, ЧАСТИЦЫ МАТЕРИАЛОВ И ЦИФРЫ УРОНА
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def spawn_shell_casing(self, origin: Vec3, right_vec: Vec3, up_vec: Vec3, is_shotgun: bool = False) -> None:
        """Выбрасывает вращающуюся 3D-гильзу вправо-вверх из окна выброса оружия."""
        if len(self.shells) >= (self.shells.maxlen or 28):
            oldest = self.shells.popleft()
            if oldest.entity is not None:
                destroy(oldest.entity)

        col = rgb32(205, 42, 36) if is_shotgun else rgb32(232, 188, 72)
        shell = Entity(
            parent=self.root,
            model="cube",
            position=origin,
            scale=(0.014, 0.014, 0.042) if not is_shotgun else (0.018, 0.018, 0.052),
            color=col,
        )
        apply_pbr_material(shell, "gold" if not is_shotgun else "polymer")

        vel = (
            right_vec * random.uniform(1.8, 2.9)
            + up_vec * random.uniform(1.4, 2.3)
            + Vec3(random.uniform(-0.3, 0.3), 0.0, random.uniform(-0.3, 0.3))
        )
        rot_vel = Vec3(
            random.uniform(360.0, 780.0),
            random.uniform(260.0, 620.0),
            random.uniform(300.0, 720.0),
        )
        self.shells.append(ShellCasing(entity=shell, vel=vel, rot_vel=rot_vel, ttl=3.2))

    def spawn_tracer(self, start_pt: Vec3, end_pt: Vec3, col: Any = None) -> None:
        """Создаёт стремительный светящийся 3D-трассер пули от дула до точки попадания."""
        diff = end_pt - start_pt
        dist = diff.length()
        if dist < 1.2:
            return
        mid = start_pt + diff * 0.52
        tracer_len = min(dist * 0.55, 14.0)
        tracer = Entity(
            parent=self.root,
            model="cube",
            position=mid,
            scale=(0.014, 0.014, tracer_len),
            color=col if col is not None else rgba32(255, 228, 130, 210),
            unlit=True,
        )
        tracer.look_at(end_pt)
        tracer.animate_scale((0.002, 0.002, tracer_len * 0.4), duration=0.065)
        destroy(tracer, delay=0.075)

    def spawn_surface_impact(self, world_pt: Vec3, normal: Vec3, material_kind: str = "stone") -> None:
        """Создаёт объёмный разлёт 3D-частиц (искры металла, щепки дерева, пыль камня или брызги крови)."""
        if len(self.particles) > 85:
            return

        if material_kind == "blood":
            count = 7
            palette = [rgb32(195, 22, 22), rgb32(145, 14, 16), rgb32(228, 38, 34)]
            spd_min, spd_max = 1.4, 3.8
            base_scale = 0.055
            grav = 9.5
        elif material_kind == "metal":
            count = 7
            palette = [rgb32(255, 232, 120), rgb32(255, 175, 55), rgb32(255, 250, 200)]
            spd_min, spd_max = 2.8, 6.2
            base_scale = 0.038
            grav = 11.0
        elif material_kind == "wood":
            count = 6
            palette = [rgb32(168, 118, 64), rgb32(132, 88, 44), rgb32(196, 152, 92)]
            spd_min, spd_max = 1.8, 4.4
            base_scale = 0.048
            grav = 10.5
        else:  # stone / sand
            count = 5
            palette = [rgb32(218, 198, 162), rgb32(188, 168, 136), rgb32(235, 220, 190)]
            spd_min, spd_max = 1.2, 3.4
            base_scale = 0.065
            grav = 6.5

        n_safe = normal.normalized() if normal.length() > 1e-4 else Vec3(0.0, 1.0, 0.0)
        for _ in range(count):
            jitter = Vec3(
                random.uniform(-0.85, 0.85),
                random.uniform(-0.35, 0.95),
                random.uniform(-0.85, 0.85),
            )
            dir_v = (n_safe + jitter).normalized()
            p_ent = Entity(
                parent=self.root,
                model="cube" if material_kind in ("wood", "metal") else "sphere",
                position=world_pt + n_safe * 0.04,
                scale=base_scale * random.uniform(0.7, 1.35),
                color=random.choice(palette),
                unlit=(material_kind == "metal"),
            )
            ttl = random.uniform(0.18, 0.42)
            self.particles.append(
                ParticleItem(
                    entity=p_ent,
                    vel=dir_v * random.uniform(spd_min, spd_max),
                    gravity=grav,
                    ttl=ttl,
                    max_ttl=ttl,
                )
            )

    def spawn_damage_popup(self, world_pt: Vec3, damage: int, is_headshot: bool = False) -> None:
        """Показывает всплывающее 3D-число нанесённого урона над точкой попадания."""
        if len(self.popups) >= 10:
            oldest = self.popups.pop(0)
            destroy(oldest.entity)

        label_str = f"-{damage} HS!" if is_headshot else f"-{damage}"
        col = rgb32(255, 72, 58) if is_headshot else rgb32(255, 232, 145)
        kwargs: dict[str, Any] = {
            "parent": self.root,
            "text": label_str,
            "position": world_pt + Vec3(random.uniform(-0.18, 0.18), 0.25, random.uniform(-0.18, 0.18)),
            "origin": (0.0, 0.0),
            "scale": 5.5 if is_headshot else 4.2,
            "color": col,
            "billboard": True,
        }
        try:
            txt = Text(**kwargs, font=self._font) if self._font else Text(**kwargs)
        except Exception:
            txt = Text(**kwargs)
        self.popups.append(DamagePopup(entity=txt, vel_y=1.45, ttl=0.72))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. ФИЗИЧЕСКИЕ 3D-ГРАНАТЫ (HE, FLASHBANG, SMOKE, MOLOTOV)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def throw_grenade(self, grenade_type: str, origin: Vec3, forward: Vec3, up: Vec3) -> None:
        """Бросает 3D-гранату по параболической траектории с отскоками от стен и пола."""
        spec = GRENADE_SPECS.get(grenade_type, GRENADE_SPECS["he"])
        r, g, b = spec["color_rgb"]

        g_ent = Entity(
            parent=self.root,
            position=origin + forward * 0.55,
        )
        body = Entity(
            parent=g_ent,
            model="sphere" if grenade_type == "he" else "cube",
            scale=(0.14, 0.18, 0.14) if grenade_type != "he" else (0.16, 0.18, 0.16),
            color=rgb32(r, g, b),
        )
        apply_pbr_material(body, "metal")
        # Чека / индикаторное кольцо гранаты
        Entity(
            parent=g_ent,
            model="cube",
            position=(0.0, 0.10, 0.0),
            scale=(0.06, 0.04, 0.06),
            color=rgb32(255, 80, 50) if grenade_type in ("he", "molotov") else rgb32(70, 210, 255),
            unlit=True,
        )

        throw_vel = forward.normalized() * 17.5 + up * 4.2
        self.sound_mgr.play_sfx("knife_slash", volume=0.55, pitch=1.25)
        self.grenades.append(
            GrenadeInstance(
                grenade_type=grenade_type,
                entity=g_ent,
                vel=throw_vel,
                fuse=float(spec["fuse"]),
            )
        )

    def trigger_explosion_vfx(self, center: Vec3, radius: float = 8.5, source_label: str = "HE GRENADE") -> None:
        """Создаёт мощный 3D-взрыв (ударная волна, огненное ядро, осколки, воронка и урон)."""
        self.sound_mgr.play_sfx("explosion", volume=0.95, pitch=random.uniform(0.92, 1.05))
        self.pulse_dynamic_light(center + Vec3(0, 0.8, 0), (255, 165, 55), duration=0.28)

        # Огненная сфера взрыва
        fireball = Entity(
            parent=self.root,
            model="sphere",
            position=center + Vec3(0.0, 0.4, 0.0),
            scale=0.5,
            color=rgba32(255, 168, 48, 225),
            unlit=True,
        )
        fireball.animate_scale(radius * 0.72, duration=0.22)
        fireball.animate_color(rgba32(90, 80, 75, 0), duration=0.28)
        destroy(fireball, delay=0.30)

        # Внешняя ударная волна
        shock = Entity(
            parent=self.root,
            model="sphere",
            position=center + Vec3(0.0, 0.4, 0.0),
            scale=0.8,
            color=rgba32(255, 235, 195, 120),
            unlit=True,
        )
        shock.animate_scale(radius * 1.15, duration=0.26)
        destroy(shock, delay=0.28)

        # Чёрная воронка копоти на полу
        ground_hit = raycast(center + Vec3(0, 1.0, 0), Vec3(0, -1, 0), distance=3.0)
        scorch_y = ground_hit.world_point.y + 0.015 if ground_hit.hit else max(0.02, center.y)
        if len(self.scorch_decals) >= (self.scorch_decals.maxlen or 18):
            old_s = self.scorch_decals.popleft()
            if old_s is not None:
                destroy(old_s)
        scorch = Entity(
            parent=self.root,
            model="quad",
            position=Vec3(center.x, scorch_y, center.z),
            rotation_x=90.0,
            scale=radius * 0.42,
            color=rgba32(22, 20, 18, 205),
            unlit=True,
        )
        self.scorch_decals.append(scorch)

        # Разлёт искр и обломков
        self.spawn_surface_impact(center + Vec3(0, 0.3, 0), Vec3(0, 1, 0), "metal")
        self.spawn_surface_impact(center + Vec3(0, 0.3, 0), Vec3(0, 1, 0), "stone")

        if self.on_explosion_damage is not None:
            self.on_explosion_damage(center, radius, 112.0, source_label)

    def _detonate_grenade(self, g: GrenadeInstance) -> None:
        pos = Vec3(g.entity.world_position)
        destroy(g.entity)

        if g.grenade_type == "he":
            self.trigger_explosion_vfx(pos, radius=8.5, source_label="HE GRENADE")

        elif g.grenade_type == "flash":
            self.sound_mgr.play_sfx("flashbang", volume=0.92)
            self.pulse_dynamic_light(pos, (255, 255, 255), duration=0.18)
            burst = Entity(
                parent=self.root,
                model="sphere",
                position=pos,
                scale=0.35,
                color=rgba32(255, 255, 255, 245),
                unlit=True,
            )
            burst.animate_scale(4.2, duration=0.14)
            destroy(burst, delay=0.16)
            if self.on_flashbang_pop is not None:
                self.on_flashbang_pop(pos)

        elif g.grenade_type == "smoke":
            self.sound_mgr.play_sfx("smoke_hiss", volume=0.85)
            # Дым тушит активные коктейли Молотова поблизости (как в настоящем CS2!)
            kept_fires: list[FireZone] = []
            for fz in self.fires:
                if (fz.center - pos).length() <= 5.2:
                    for fl in fz.flames:
                        destroy(fl)
                    destroy(fz.scorch)
                else:
                    kept_fires.append(fz)
            self.fires = kept_fires

            puffs: list[Entity] = []
            offsets = [
                (0.0, 1.3, 0.0, 4.4),
                (-1.7, 1.1, 0.9, 3.5),
                (1.7, 1.1, -0.8, 3.5),
                (0.7, 1.2, 1.7, 3.4),
                (-0.8, 1.1, -1.7, 3.4),
                (0.0, 2.5, 0.0, 3.6),
            ]
            for ox, oy, oz, target_sc in offsets:
                shade = random.randint(188, 218)
                puff = Entity(
                    parent=self.root,
                    model="sphere",
                    position=pos + Vec3(ox, oy, oz),
                    scale=0.4,
                    color=rgba32(shade, shade + 2, shade + 6, 228),
                    unlit=True,
                )
                puff.animate_scale(target_sc, duration=0.55)
                puffs.append(puff)
            self.smokes.append(SmokeCloud(center=pos + Vec3(0, 1.2, 0), radius=4.6, ttl=15.0, puffs=puffs))

        elif g.grenade_type == "molotov":
            # Если рядом уже лежит дым — Молотов сразу шипит и гаснет!
            for sm in self.smokes:
                if (sm.center - pos).length() <= sm.radius + 1.0:
                    self.sound_mgr.play_sfx("smoke_hiss", volume=0.75, pitch=1.2)
                    return

            self.sound_mgr.play_sfx("smoke_hiss", volume=0.88, pitch=0.82)
            self.pulse_dynamic_light(pos + Vec3(0, 0.6, 0), (255, 128, 28), duration=0.45)

            ground_ray = raycast(pos + Vec3(0, 1.5, 0), Vec3(0, -1, 0), distance=4.5)
            floor_y = ground_ray.world_point.y if ground_ray.hit else max(0.0, pos.y - 0.1)
            center_floor = Vec3(pos.x, floor_y, pos.z)

            scorch = Entity(
                parent=self.root,
                model="quad",
                position=center_floor + Vec3(0, 0.02, 0),
                rotation_x=90.0,
                scale=5.8,
                color=rgba32(235, 88, 20, 155),
                unlit=True,
            )
            flames: list[Entity] = []
            for idx in range(11):
                ang = idx * (2.0 * math.pi / 11.0)
                dist_r = random.uniform(0.35, 2.5) if idx > 0 else 0.0
                fx = center_floor.x + math.cos(ang) * dist_r
                fz_coord = center_floor.z + math.sin(ang) * dist_r
                f_col = rgb32(255, random.randint(115, 205), 28)
                fl = Entity(
                    parent=self.root,
                    model="cube",
                    position=Vec3(fx, floor_y + 0.38, fz_coord),
                    scale=(0.42, random.uniform(0.65, 1.15), 0.42),
                    rotation_y=random.uniform(0, 90),
                    color=f_col,
                    unlit=True,
                )
                flames.append(fl)
            self.fires.append(
                FireZone(
                    center=center_floor,
                    radius=3.4,
                    ttl=7.5,
                    tick_timer=0.15,
                    flames=flames,
                    scorch=scorch,
                )
            )

    def is_segment_blocked_by_smoke(self, p1: Vec3, p2: Vec3) -> bool:
        """Проверяет, проходит ли луч видимости бота сквозь активное облако дыма CS2."""
        if not self.smokes:
            return False
        seg = p2 - p1
        seg_len_sq = seg.x * seg.x + seg.y * seg.y + seg.z * seg.z
        if seg_len_sq < 1e-5:
            return False
        for sm in self.smokes:
            to_c = sm.center - p1
            t = clamp((to_c.x * seg.x + to_c.y * seg.y + to_c.z * seg.z) / seg_len_sq, 0.0, 1.0)
            closest = p1 + seg * t
            if (closest - sm.center).length() <= sm.radius * 0.85:
                return True
        return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. ИНТЕРАКТИВНАЯ БОМБА C4 (УСТАНОВКА, ТАЙМЕР, САПЁРНЫЙ НАБОР)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def plant_c4(self, world_pos: Vec3, site_name: str = "A") -> None:
        """Устанавливает 3D-бомбу C4 на точке A или B с мигающим диодом и обратным отсчётом 40 сек."""
        if self.c4_planted:
            return
        self.c4_planted = True
        self.c4_defused = False
        self.c4_exploded = False
        self.c4_site_name = site_name
        self.c4_timer = 40.0
        self.c4_beep_cooldown = 0.95
        self.c4_defuse_progress = 0.0

        ground_ray = raycast(world_pos + Vec3(0, 1.5, 0), Vec3(0, -1, 0), distance=4.0)
        floor_y = ground_ray.world_point.y if ground_ray.hit else world_pos.y
        self.c4_pos = Vec3(world_pos.x, floor_y, world_pos.z)

        self.c4_entity = Entity(parent=self.root, position=self.c4_pos)
        c4_np = load_safe_model("assets/models/c4.glb", target_max_extent=0.38, align_bottom_zero=True)
        if c4_np is not None:
            Entity(parent=self.c4_entity, model=c4_np)
        else:
            Entity(
                parent=self.c4_entity,
                model="cube",
                position=(0, 0.05, 0),
                scale=(0.28, 0.10, 0.34),
                color=rgb32(168, 154, 112),
            )
        self.c4_led = Entity(
            parent=self.c4_entity,
            model="sphere",
            position=(0.0, 0.14, 0.04),
            scale=0.065,
            color=rgb32(255, 38, 32),
            unlit=True,
        )
        self.sound_mgr.play_sfx("c4_plant", volume=0.92)

    def step_defuse(self, dt: float, player_pos: Vec3, has_defuse_kit: bool, holding_use: bool) -> float:
        """
        Обновляет прогресс обезвреживания C4 (0.0 .. 1.0).
        С набором сапёра — 2.5 сек, без набора — 5.0 сек.
        """
        if not self.c4_planted or self.c4_defused or self.c4_exploded:
            self.c4_defuse_progress = 0.0
            return 0.0

        dist = (Vec3(player_pos.x, self.c4_pos.y, player_pos.z) - self.c4_pos).length()
        if holding_use and dist <= 3.3:
            need_secs = 2.5 if has_defuse_kit else 5.0
            if self.c4_defuse_progress <= 0.001:
                self.sound_mgr.play_sfx("empty_click", volume=0.65, pitch=1.35)
            self.c4_defuse_progress = min(1.0, self.c4_defuse_progress + dt / need_secs)
            if self.c4_defuse_progress >= 1.0:
                self.c4_defused = True
                self.c4_planted = False
                if self.c4_led is not None:
                    self.c4_led.color = rgb32(55, 245, 115)
                self.sound_mgr.play_sfx("c4_defuse", volume=0.95)
                if self.on_c4_defused is not None:
                    self.on_c4_defused()
        else:
            self.c4_defuse_progress = max(0.0, self.c4_defuse_progress - dt * 2.2)

        return self.c4_defuse_progress

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. ВЫПАДАЮЩИЕ ТРОФЕИ И 3D ТАКТИЧЕСКИЙ ПИНГ (Z)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def spawn_loot_drop(self, world_pos: Vec3) -> None:
        """Создаёт вращающийся 3D-трофей на месте ликвидированного противника."""
        kind = random.choice(("medkit", "armor", "ammo", "cash"))
        ground_ray = raycast(world_pos + Vec3(0, 1.2, 0), Vec3(0, -1, 0), distance=3.5)
        y0 = (ground_ray.world_point.y if ground_ray.hit else world_pos.y) + 0.28
        base_pos = Vec3(world_pos.x, y0, world_pos.z)

        palette = {
            "medkit": rgb32(72, 235, 128),
            "armor": rgb32(78, 168, 255),
            "ammo": rgb32(245, 188, 58),
            "cash": rgb32(115, 228, 92),
        }
        holder = Entity(parent=self.root, position=base_pos)
        box = Entity(
            parent=holder,
            model="cube",
            scale=(0.28, 0.20, 0.28),
            color=palette[kind],
        )
        apply_pbr_material(box, "metal")
        Entity(
            parent=holder,
            model="cube",
            position=(0, 0.13, 0),
            scale=(0.12, 0.05, 0.12),
            color=color.white,
            unlit=True,
        )
        self.loot_drops.append(
            LootDrop(kind=kind, entity=holder, pos=base_pos, ttl=18.0, phase=random.uniform(0, 6.28))
        )

    def place_tactical_ping(self, origin: Vec3, direction: Vec3, ignore_list: list[Entity]) -> Vec3 | None:
        """Ставит 3D-ромб тактической метки с дистанцией в точку прицела (клавиша Z)."""
        hit = raycast(origin, direction, distance=130.0, ignore=ignore_list)
        if not hit.hit:
            return None

        pt = hit.world_point + hit.world_normal * 0.12
        self._clear_ping()

        self.ping_pos = pt
        self.ping_timer = 6.5
        self.ping_entity = Entity(
            parent=self.root,
            model="sphere",
            position=pt + Vec3(0.0, 0.35, 0.0),
            scale=(0.24, 0.38, 0.24),
            color=rgb32(65, 235, 255),
            unlit=True,
        )
        dist_m = int(round((pt - origin).length()))
        kwargs: dict[str, Any] = {
            "parent": self.root,
            "text": f"PING [{dist_m}m]",
            "position": pt + Vec3(0.0, 0.85, 0.0),
            "origin": (0.0, 0.0),
            "scale": 4.2,
            "color": rgb32(95, 245, 255),
            "billboard": True,
        }
        try:
            self.ping_label = Text(**kwargs, font=self._font) if self._font else Text(**kwargs)
        except Exception:
            self.ping_label = Text(**kwargs)

        self.sound_mgr.play_sfx("hitmarker", volume=0.55, pitch=1.45)
        return pt

    def _clear_ping(self) -> None:
        if self.ping_entity is not None:
            destroy(self.ping_entity)
            self.ping_entity = None
        if self.ping_label is not None:
            destroy(self.ping_label)
            self.ping_label = None
        self.ping_pos = None
        self.ping_timer = 0.0

    def reset_round_fx(self) -> None:
        """Очищает временные объекты раунда (дымы, огонь, гранаты, C4, гильзы, лут)."""
        while self.shells:
            sh = self.shells.popleft()
            if sh.entity is not None:
                destroy(sh.entity)
        for p in self.particles:
            destroy(p.entity)
        self.particles.clear()
        for pop in self.popups:
            destroy(pop.entity)
        self.popups.clear()
        for g in self.grenades:
            destroy(g.entity)
        self.grenades.clear()
        for sm in self.smokes:
            for pf in sm.puffs:
                destroy(pf)
        self.smokes.clear()
        for fz in self.fires:
            for fl in fz.flames:
                destroy(fl)
            destroy(fz.scorch)
        self.fires.clear()
        for ld in self.loot_drops:
            destroy(ld.entity)
        self.loot_drops.clear()
        while self.scorch_decals:
            sc = self.scorch_decals.popleft()
            if sc is not None:
                destroy(sc)

        if self.c4_entity is not None:
            destroy(self.c4_entity)
            self.c4_entity = None
        self.c4_led = None
        self.c4_planted = False
        self.c4_defused = False
        self.c4_exploded = False
        self.c4_defuse_progress = 0.0
        self._clear_ping()
        self.dynamic_light.color = rgb32(0, 0, 0)
        self._dyn_light_timer = 0.0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. ПОКАДРОВОЕ ОБНОВЛЕНИЕ ФИЗИКИ ЭФФЕКТОВ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def update(self, dt: float, ignore_entities: list[Entity]) -> None:
        # 1. Затухание динамического света
        if self._dyn_light_timer > 0.0:
            self._dyn_light_timer = max(0.0, self._dyn_light_timer - dt)
            if self._dyn_light_timer <= 0.0:
                self.dynamic_light.color = rgb32(0, 0, 0)

        # 2. Физика латунных гильз
        expired_shells = 0
        for sh in self.shells:
            sh.ttl -= dt
            if sh.ttl <= 0.0:
                expired_shells += 1
                continue
            if not sh.bounced or sh.vel.length() > 0.25:
                sh.vel.y -= 13.5 * dt
                sh.entity.position += sh.vel * dt
                sh.entity.rotation += sh.rot_vel * dt
                if sh.entity.y <= 0.03:
                    sh.entity.y = 0.03
                    sh.vel.y = abs(sh.vel.y) * 0.35
                    sh.vel.x *= 0.45
                    sh.vel.z *= 0.45
                    sh.rot_vel *= 0.30
                    if not sh.bounced:
                        sh.bounced = True
                        self.sound_mgr.play_sfx("shell_clink", volume=0.28, pitch=random.uniform(0.92, 1.12))
        while expired_shells > 0 and self.shells:
            old = self.shells.popleft()
            if old.entity is not None:
                destroy(old.entity)
            expired_shells -= 1

        # 3. Частицы попаданий
        alive_particles: list[ParticleItem] = []
        for pt in self.particles:
            pt.ttl -= dt
            if pt.ttl <= 0.0:
                destroy(pt.entity)
                continue
            pt.vel.y -= pt.gravity * dt
            pt.entity.position += pt.vel * dt
            if pt.shrink:
                pt.entity.scale *= max(0.82, 1.0 - dt * 3.5)
            alive_particles.append(pt)
        self.particles = alive_particles

        # 4. Всплывающие цифры урона
        alive_popups: list[DamagePopup] = []
        for pop in self.popups:
            pop.ttl -= dt
            if pop.ttl <= 0.0:
                destroy(pop.entity)
                continue
            pop.entity.y += pop.vel_y * dt
            alive_popups.append(pop)
        self.popups = alive_popups

        # 5. Полёт и отскок 3D-гранат
        active_grenades: list[GrenadeInstance] = []
        for g in self.grenades:
            g.fuse -= dt
            g.vel.y -= 16.5 * dt
            step_vec = g.vel * dt
            step_dist = step_vec.length()
            if step_dist > 1e-4:
                hit = raycast(
                    g.entity.world_position,
                    step_vec.normalized(),
                    distance=step_dist + 0.16,
                    ignore=[g.entity, *ignore_entities],
                )
                if hit.hit:
                    n = hit.world_normal.normalized()
                    # Молотов разбивается сразу при ударе о горизонтальный пол!
                    if g.grenade_type == "molotov" and n.y > 0.65:
                        g.entity.position = hit.world_point + n * 0.08
                        self._detonate_grenade(g)
                        continue
                    dot_vn = g.vel.dot(n)
                    g.vel = (g.vel - n * (2.0 * dot_vn)) * 0.52
                    g.entity.position = hit.world_point + n * 0.15
                    g.bounces += 1
                    self.sound_mgr.play_sfx("empty_click", volume=0.40, pitch=0.85)
                else:
                    g.entity.position += step_vec
                    g.entity.rotation += Vec3(260 * dt, 190 * dt, 310 * dt)

            if g.fuse <= 0.0:
                self._detonate_grenade(g)
            else:
                active_grenades.append(g)
        self.grenades = active_grenades

        # 6. Дымовые завесы
        active_smokes: list[SmokeCloud] = []
        for sm in self.smokes:
            sm.ttl -= dt
            if sm.ttl <= 0.0:
                for pf in sm.puffs:
                    destroy(pf)
                continue
            if sm.ttl < 1.5:
                fade_a = int(228 * (sm.ttl / 1.5))
                for pf in sm.puffs:
                    pf.color = rgba32(200, 204, 210, max(0, fade_a))
            active_smokes.append(sm)
        self.smokes = active_smokes

        # 7. Огненные лужи Молотова
        active_fires: list[FireZone] = []
        for fz in self.fires:
            fz.ttl -= dt
            if fz.ttl <= 0.0:
                for fl in fz.flames:
                    destroy(fl)
                destroy(fz.scorch)
                continue
            for fl in fz.flames:
                fl.scale_y = random.uniform(0.55, 1.28)
                fl.rotation_y += dt * 120.0
            fz.tick_timer -= dt
            if fz.tick_timer <= 0.0:
                fz.tick_timer = 0.35
                self.pulse_dynamic_light(fz.center + Vec3(0, 0.7, 0), (255, 130, 30), duration=0.20)
                if self.on_fire_tick is not None:
                    self.on_fire_tick(fz.center, fz.radius)
            active_fires.append(fz)
        self.fires = active_fires

        # 8. Таймер и писк установленной бомбы C4
        if self.c4_planted and not self.c4_defused and not self.c4_exploded:
            self.c4_timer -= dt
            self.c4_beep_cooldown -= dt
            if self.c4_beep_cooldown <= 0.0:
                # Частота писка ускоряется по мере приближения взрыва (как в CS2!)
                ratio = clamp(self.c4_timer / 40.0, 0.05, 1.0)
                self.c4_beep_cooldown = max(0.11, 0.95 * (ratio ** 1.35))
                pitch = 1.0 + (1.0 - ratio) * 0.45
                self.sound_mgr.play_sfx("c4_beep", volume=0.78, pitch=pitch)
                if self.c4_led is not None:
                    self.c4_led.enabled = True
                    self.c4_led.scale = 0.09
                self.pulse_dynamic_light(self.c4_pos + Vec3(0, 0.35, 0), (255, 35, 30), duration=0.08)
            elif self.c4_led is not None and self.c4_beep_cooldown < 0.08:
                self.c4_led.scale = 0.05

            if self.c4_timer <= 0.0:
                self.c4_timer = 0.0
                self.c4_exploded = True
                self.c4_planted = False
                self.trigger_explosion_vfx(self.c4_pos, radius=24.0, source_label="C4 EXPLOSIVE")
                if self.on_c4_exploded is not None:
                    self.on_c4_exploded()

        # 9. Вращение выпавших трофеев
        kept_loot: list[LootDrop] = []
        for ld in self.loot_drops:
            ld.ttl -= dt
            if ld.ttl <= 0.0:
                destroy(ld.entity)
                continue
            ld.phase += dt * 3.2
            ld.entity.rotation_y += dt * 95.0
            ld.entity.y = ld.pos.y + math.sin(ld.phase) * 0.07
            kept_loot.append(ld)
        self.loot_drops = kept_loot

        # 10. Пульсация 3D-пинга
        if self.ping_timer > 0.0:
            self.ping_timer -= dt
            if self.ping_entity is not None:
                pulse = 1.0 + 0.18 * math.sin(self.ping_timer * 9.0)
                self.ping_entity.scale = Vec3(0.22 * pulse, 0.36 * pulse, 0.22 * pulse)
            if self.ping_timer <= 0.0:
                self._clear_ping()
