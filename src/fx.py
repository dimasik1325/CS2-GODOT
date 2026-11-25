"""
Высокооптимизированная 3D-система спецэффектов (Ring-Buffer Object Pooling, ноль аллокаций в бою):
- Кольцевые пулы 3D-гильз, трассеров, искр/крови/щепок и электродуг Zeus x27 (без спайков GC!)
- Слетающие и отскакивающие 3D-шлемы при хедшотах (Flying Helmet Physics)
- Динамический боевой 3D-свет PointLight (управляется настройкой графики dynamic_lights)
- 4 вида физических гранат (HE, Flashbang, Smoke, Molotov) + тушение огня дымом
- Интерактивная бомба C4, вращающиеся 3D-трофеи и тактическая метка-пинг
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable

from panda3d.core import PointLight as PandaPointLight
from ursina import Entity, Text, Vec3, clamp, destroy, raycast, scene

from src.settings import (
    GRENADE_SPECS,
    GameSettings,
    SoundManager,
    apply_pbr_material,
    load_safe_model,
    resolve_font_path,
    rgb32,
    rgba32,
)


@dataclass
class _PoolShellSlot:
    entity: Entity
    vel: Vec3
    rot_vel: Vec3
    ttl: float = 0.0
    bounced: bool = False
    active: bool = False


@dataclass
class _PoolTracerSlot:
    entity: Entity
    ttl: float = 0.0
    max_ttl: float = 0.05
    active: bool = False


@dataclass
class _PoolParticleSlot:
    entity: Entity
    vel: Vec3
    gravity: float = 9.8
    ttl: float = 0.0
    max_ttl: float = 0.35
    base_scale: float = 0.05
    active: bool = False


@dataclass
class _DamageNumber:
    entity: Text
    ttl: float
    vel_y: float


@dataclass
class ActiveGrenade:
    entity: Entity
    g_type: str
    vel: Vec3
    fuse: float
    bounces: int = 0


@dataclass
class SmokeCloud:
    root: Entity
    puffs: list[Entity]
    center: Vec3
    radius: float
    ttl: float
    max_ttl: float


@dataclass
class FireZone:
    root: Entity
    flames: list[Entity]
    center: Vec3
    radius: float
    ttl: float
    tick_accum: float = 0.0


@dataclass
class LootDrop:
    entity: Entity
    kind: str
    pos: Vec3
    ttl: float
    phase: float


class FXManager:
    """Единый пул-менеджер 3D-физики снарядов, частиц, света, C4 и трофеев без просадок FPS."""

    MAX_SHELL_POOL = 80
    MAX_TRACER_POOL = 36
    MAX_PARTICLE_POOL = 96

    def __init__(self, sound_mgr: SoundManager, settings: GameSettings | None = None) -> None:
        self.sound_mgr = sound_mgr
        self.settings = settings
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        # ── 1. ДИНАМИЧЕСКИЙ БОЕВОЙ СВЕТ (POINTLIGHT) ──
        self._combat_light_root = Entity(parent=scene, position=(0.0, -50.0, 0.0), add_to_scene_entities=False)
        self._p3d_point_light = PandaPointLight("cs2_combat_light")
        self._p3d_point_light.setColor((0.0, 0.0, 0.0, 1.0))
        self._p3d_point_light.setAttenuation((1.0, 0.065, 0.018))
        self._light_np = self._combat_light_root.attachNewNode(self._p3d_point_light)
        scene.setLight(self._light_np)
        self._light_ttl: float = 0.0
        self._light_max_ttl: float = 0.1
        self._light_rgb: tuple[float, float, float] = (1.0, 0.8, 0.4)

        # ── 2. ПРЕДВАРИТЕЛЬНО СОЗДАННЫЕ КОЛЬЦЕВЫЕ ПУЛЫ ОБЪЕКТОВ (ZERO GC ALLOCATION!) ──
        brass_col = rgb32(226, 184, 72)
        self._shell_pool: list[_PoolShellSlot] = []
        for _ in range(self.MAX_SHELL_POOL):
            ent = Entity(
                parent=scene,
                model="cube",
                scale=(0.015, 0.015, 0.044),
                color=brass_col,
                enabled=False,
                add_to_scene_entities=False,
            )
            apply_pbr_material(ent, shininess=76.0, specular_strength=0.85, metallic=0.82)
            self._shell_pool.append(_PoolShellSlot(entity=ent, vel=Vec3(0, 0, 0), rot_vel=Vec3(0, 0, 0)))
        self._shell_cursor: int = 0

        self._tracer_pool: list[_PoolTracerSlot] = []
        for _ in range(self.MAX_TRACER_POOL):
            ent = Entity(
                parent=scene,
                model="cube",
                unlit=True,
                enabled=False,
                add_to_scene_entities=False,
            )
            self._tracer_pool.append(_PoolTracerSlot(entity=ent))
        self._tracer_cursor: int = 0

        self._particle_pool: list[_PoolParticleSlot] = []
        for _ in range(self.MAX_PARTICLE_POOL):
            ent = Entity(
                parent=scene,
                model="cube",
                unlit=True,
                enabled=False,
                add_to_scene_entities=False,
            )
            self._particle_pool.append(_PoolParticleSlot(entity=ent, vel=Vec3(0, 0, 0)))
        self._particle_cursor: int = 0

        # Редкие динамические контейнеры (гранаты, дымы, C4, трофеи)
        self.popups: list[_DamageNumber] = []
        self.grenades: list[ActiveGrenade] = []
        self.smokes: list[SmokeCloud] = []
        self.fires: list[FireZone] = []
        self.loot_drops: list[LootDrop] = []

        # ── 3. ИНТЕРАКТИВНАЯ БОМБА C4 ──
        self.c4_planted: bool = False
        self.c4_defused: bool = False
        self.c4_exploded: bool = False
        self.c4_timer: float = 40.0
        self.c4_defuse_progress: float = 0.0
        self.c4_pos: Vec3 = Vec3(0.0, 0.0, 0.0)
        self.c4_site_name: str = "A"
        self._c4_beep_accum: float = 0.0
        self.c4_entity: Entity | None = None
        self.c4_led: Entity | None = None

        # ── 4. 3D ПИНГ ──
        self.ping_entity: Entity = Entity(parent=scene, enabled=False, add_to_scene_entities=False)
        Entity(
            parent=self.ping_entity,
            model="sphere",
            position=(0.0, 0.35, 0.0),
            scale=(0.24, 0.36, 0.24),
            color=rgb32(65, 228, 255),
            unlit=True,
            add_to_scene_entities=False,
        )
        Entity(
            parent=self.ping_entity,
            model="cube",
            position=(0.0, 1.15, 0.0),
            scale=(0.035, 2.2, 0.035),
            color=rgba32(65, 228, 255, 130),
            unlit=True,
            add_to_scene_entities=False,
        )
        self.ping_ttl: float = 0.0
        self.ping_pos: Vec3 | None = None

        # ── КОЛБЭКИ ──
        self.on_explosion_damage: Callable[[Vec3, float, float, str], None] | None = None
        self.on_flashbang_pop: Callable[[Vec3], None] | None = None
        self.on_fire_tick: Callable[[Vec3, float], None] | None = None
        self.on_c4_exploded: Callable[[], None] | None = None
        self.on_c4_defused: Callable[[], None] | None = None

    @property
    def active_pooled_count(self) -> int:
        return (
            sum(1 for s in self._shell_pool if s.active)
            + sum(1 for t in self._tracer_pool if t.active)
            + sum(1 for p in self._particle_pool if p.active)
        )

    def flash_world_light(
        self,
        pos: Vec3,
        rgb: tuple[float, float, float] = (1.0, 0.78, 0.36),
        intensity: float = 2.6,
        duration: float = 0.08,
    ) -> None:
        if self.settings is not None and not self.settings.dynamic_lights:
            return
        self._combat_light_root.position = pos
        self._light_rgb = (rgb[0] * intensity, rgb[1] * intensity, rgb[2] * intensity)
        self._p3d_point_light.setColor((*self._light_rgb, 1.0))
        self._light_max_ttl = max(0.02, duration)
        self._light_ttl = self._light_max_ttl

    def spawn_shell_casing(self, origin: Vec3, right_dir: Vec3, up_dir: Vec3, is_shotgun: bool = False) -> None:
        limit = int(self.settings.decal_shell_limit) if self.settings is not None else 48
        if limit <= 0:
            return
        pool_cap = min(limit, self.MAX_SHELL_POOL)
        slot = self._shell_pool[self._shell_cursor % pool_cap]
        self._shell_cursor = (self._shell_cursor + 1) % pool_cap

        ent = slot.entity
        ent.position = origin
        ent.scale = (0.024, 0.024, 0.062) if is_shotgun else (0.015, 0.015, 0.044)
        ent.color = rgb32(205, 38, 34) if is_shotgun else rgb32(226, 184, 72)
        ent.rotation = Vec3(random.uniform(0, 180), random.uniform(0, 180), 0)
        ent.enabled = True

        slot.vel = right_dir * random.uniform(1.8, 2.9) + up_dir * random.uniform(1.5, 2.4)
        slot.rot_vel = Vec3(random.uniform(280, 620), random.uniform(220, 540), random.uniform(180, 480))
        slot.ttl = 2.2
        slot.bounced = False
        slot.active = True

    def spawn_flying_helmet(self, head_pos: Vec3) -> None:
        """Сбитая при хедшоте каска врага улетает вверх с вращением!"""
        slot = self._shell_pool[self._shell_cursor % self.MAX_SHELL_POOL]
        self._shell_cursor = (self._shell_cursor + 1) % self.MAX_SHELL_POOL
        ent = slot.entity
        ent.position = head_pos
        ent.scale = (0.24, 0.16, 0.26)
        ent.color = rgb32(62, 68, 76)
        ent.enabled = True
        slot.vel = Vec3(random.uniform(-2.2, 2.2), random.uniform(4.2, 5.8), random.uniform(-2.2, 2.2))
        slot.rot_vel = Vec3(random.uniform(320, 580), random.uniform(240, 480), random.uniform(260, 520))
        slot.ttl = 2.6
        slot.bounced = False
        slot.active = True

    def _alloc_tracer(self, start: Vec3, end: Vec3, col: Any, thickness: float, ttl: float) -> None:
        seg = end - start
        dist = seg.length()
        if dist < 0.25:
            return
        slot = self._tracer_pool[self._tracer_cursor % self.MAX_TRACER_POOL]
        self._tracer_cursor = (self._tracer_cursor + 1) % self.MAX_TRACER_POOL
        ent = slot.entity
        ent.position = start + seg * 0.5
        ent.scale = (thickness, thickness, min(dist * 0.96, 42.0))
        ent.color = col
        ent.look_at(end)
        ent.enabled = True
        slot.ttl = ttl
        slot.max_ttl = ttl
        slot.active = True

    def spawn_tracer(self, start: Vec3, end: Vec3, is_sniper: bool = False) -> None:
        col = rgba32(255, 240, 175, 235) if is_sniper else rgba32(255, 214, 108, 195)
        thick = 0.024 if is_sniper else 0.013
        self._alloc_tracer(start, end, col, thick, 0.085 if is_sniper else 0.048)

    def spawn_zeus_arc(self, start: Vec3, end: Vec3) -> None:
        """Рисует зигзагообразную высоковольтную молнию электрошокера Zeus x27!"""
        steps = 5
        pts = [start]
        for i in range(1, steps):
            f = i / steps
            jitter = Vec3(random.uniform(-0.18, 0.18), random.uniform(-0.14, 0.18), random.uniform(-0.18, 0.18))
            pts.append(start + (end - start) * f + jitter)
        pts.append(end)
        for i in range(len(pts) - 1):
            self._alloc_tracer(pts[i], pts[i + 1], rgba32(85, 225, 255, 255), 0.028, 0.18)
        self.flash_world_light(end, rgb=(0.35, 0.88, 1.0), intensity=3.8, duration=0.14)

    def _emit_particle(
        self,
        pos: Vec3,
        vel: Vec3,
        col: Any,
        scale: float,
        ttl: float,
        gravity: float = 9.8,
    ) -> None:
        slot = self._particle_pool[self._particle_cursor % self.MAX_PARTICLE_POOL]
        self._particle_cursor = (self._particle_cursor + 1) % self.MAX_PARTICLE_POOL
        ent = slot.entity
        ent.position = pos
        ent.scale = scale
        ent.color = col
        ent.enabled = True
        slot.vel = vel
        slot.gravity = gravity
        slot.ttl = ttl
        slot.max_ttl = max(0.05, ttl)
        slot.base_scale = scale
        slot.active = True

    def spawn_surface_impact(self, hit_pos: Vec3, normal: Vec3, surface: str = "stone") -> None:
        p_mult = float(self.settings.particles_quality) if self.settings is not None else 1.0
        if p_mult <= 0.05:
            return
        palette = {
            "blood": (rgb32(198, 22, 26), 6, 3.2, 0.055),
            "metal": (rgb32(255, 215, 82), 7, 5.4, 0.035),
            "wood": (rgb32(168, 118, 62), 5, 3.6, 0.048),
            "stone": (rgb32(214, 198, 168), 4, 3.0, 0.044),
            "electric": (rgb32(95, 232, 255), 9, 5.8, 0.042),
        }
        col, base_cnt, spd, sc = palette.get(surface, palette["stone"])
        count = max(1, int(round(base_cnt * p_mult)))
        nrm = normal.normalized() if normal.length() > 0.01 else Vec3(0, 1, 0)

        for _ in range(count):
            spread = Vec3(random.uniform(-0.85, 0.85), random.uniform(0.15, 1.05), random.uniform(-0.85, 0.85))
            vel = (nrm + spread).normalized() * random.uniform(spd * 0.5, spd)
            self._emit_particle(hit_pos + nrm * 0.04, vel, col, sc, random.uniform(0.20, 0.36), gravity=10.5)

        if surface == "metal" and random.random() < 0.45:
            self.sound_mgr.play_sfx("shell_clink", volume=0.35, pitch=random.uniform(1.25, 1.55))

    def spawn_damage_popup(self, world_pos: Vec3, damage: int, is_headshot: bool = False) -> None:
        col = rgb32(255, 72, 58) if is_headshot else rgb32(255, 232, 92)
        kwargs: dict[str, Any] = {
            "parent": scene,
            "text": f"-{damage}{' HS!' if is_headshot else ''}",
            "position": world_pos + Vec3(random.uniform(-0.18, 0.18), 0.25, random.uniform(-0.18, 0.18)),
            "billboard": True,
            "origin": (0.0, 0.0),
            "scale": 5.8 if is_headshot else 4.5,
            "color": col,
        }
        if self._font is not None:
            try:
                txt = Text(**kwargs, font=self._font)
            except Exception:
                txt = Text(**kwargs)
        else:
            txt = Text(**kwargs)
        self.popups.append(_DamageNumber(entity=txt, ttl=0.72, vel_y=1.65))

    def throw_grenade(self, g_type: str, origin: Vec3, forward: Vec3, inherited_vel: Vec3 = Vec3(0, 0, 0)) -> None:
        spec = GRENADE_SPECS[g_type]
        r, g, b = spec["color"]
        gren_ent = Entity(
            parent=scene,
            model="sphere" if g_type in ("he", "smoke") else "cube",
            position=origin,
            scale=(0.15, 0.19, 0.15) if g_type != "molotov" else (0.12, 0.25, 0.12),
            color=rgb32(r, g, b),
            add_to_scene_entities=False,
        )
        apply_pbr_material(gren_ent, shininess=42.0, specular_strength=0.50)
        throw_vel = forward.normalized() * 19.5 + Vec3(0.0, 4.2, 0.0) + inherited_vel * 0.35
        self.grenades.append(ActiveGrenade(entity=gren_ent, g_type=g_type, vel=throw_vel, fuse=float(spec["fuse"])))
        self.sound_mgr.play_sfx("knife_slash", volume=0.45, pitch=0.85)

    def trigger_explosion_vfx(
        self,
        center: Vec3,
        radius: float = 8.5,
        max_damage: float = 98.0,
        source_label: str = "HE GRENADE",
    ) -> None:
        self.sound_mgr.play_sfx("explosion", volume=0.95, pitch=random.uniform(0.92, 1.06))
        self.flash_world_light(center + Vec3(0, 0.8, 0), rgb=(1.0, 0.62, 0.20), intensity=4.5, duration=0.28)
        self._emit_particle(center + Vec3(0, 0.5, 0), Vec3(0, 1.2, 0), rgba32(255, 165, 42, 220), 2.4, 0.26, gravity=0.0)

        p_mult = float(self.settings.particles_quality) if self.settings is not None else 1.0
        for _ in range(max(4, int(14 * p_mult))):
            dir_v = Vec3(random.uniform(-1, 1), random.uniform(0.2, 1.2), random.uniform(-1, 1)).normalized()
            c = rgb32(255, 185, 55) if random.random() < 0.55 else rgb32(72, 72, 76)
            self._emit_particle(center + Vec3(0, 0.3, 0), dir_v * random.uniform(5.0, 12.0), c, 0.16, 0.48, gravity=9.5)

        if self.on_explosion_damage is not None:
            self.on_explosion_damage(center, radius, max_damage, source_label)

    def _detonate_grenade(self, gren: ActiveGrenade) -> None:
        pos = Vec3(gren.entity.world_position)
        g_type = gren.g_type
        destroy(gren.entity)

        if g_type == "he":
            self.trigger_explosion_vfx(pos, radius=8.5, max_damage=98.0, source_label="HE GRENADE")
        elif g_type == "flash":
            self.sound_mgr.play_sfx("flashbang", volume=0.90)
            self.flash_world_light(pos + Vec3(0, 0.5, 0), rgb=(1.0, 1.0, 1.0), intensity=6.0, duration=0.18)
            if self.on_flashbang_pop is not None:
                self.on_flashbang_pop(pos + Vec3(0, 0.35, 0))
        elif g_type == "smoke":
            self._spawn_smoke_cloud(pos)
        elif g_type == "molotov":
            self._spawn_fire_zone(pos)

    def _spawn_smoke_cloud(self, pos: Vec3) -> None:
        self.sound_mgr.play_sfx("smoke_hiss", volume=0.82)
        kept_fires: list[FireZone] = []
        for fz in self.fires:
            if (fz.center - pos).length() <= 5.2:
                destroy(fz.root)
            else:
                kept_fires.append(fz)
        self.fires = kept_fires

        root = Entity(parent=scene, position=pos, add_to_scene_entities=False)
        puffs: list[Entity] = []
        puff_offsets = [
            (0.0, 1.35, 0.0, 3.6),
            (1.45, 1.05, 0.85, 2.8),
            (-1.45, 1.10, -0.75, 2.9),
            (0.80, 1.15, -1.40, 2.7),
            (-0.95, 1.05, 1.35, 2.7),
            (0.0, 2.25, 0.0, 2.6),
        ]
        for ox, oy, oz, sc in puff_offsets:
            pf = Entity(
                parent=root,
                model="sphere",
                position=(ox, oy, oz),
                scale=sc * 0.25,
                color=rgba32(196, 202, 208, 226),
                unlit=True,
                add_to_scene_entities=False,
            )
            pf._target_scale = sc
            puffs.append(pf)
        self.smokes.append(SmokeCloud(root=root, puffs=puffs, center=pos + Vec3(0, 1.2, 0), radius=3.75, ttl=15.0, max_ttl=15.0))

    def _spawn_fire_zone(self, pos: Vec3) -> None:
        for sm in self.smokes:
            if (sm.center - pos).length() <= 4.6:
                self.sound_mgr.play_sfx("smoke_hiss", volume=0.65, pitch=1.25)
                return
        self.sound_mgr.play_sfx("explosion", volume=0.60, pitch=1.35)
        self.flash_world_light(pos + Vec3(0, 0.7, 0), rgb=(1.0, 0.45, 0.12), intensity=3.2, duration=0.45)
        root = Entity(parent=scene, position=pos, add_to_scene_entities=False)
        Entity(parent=root, model="sphere", position=(0.0, 0.04, 0.0), scale=(5.2, 0.08, 5.2), color=rgba32(235, 78, 18, 175), unlit=True, add_to_scene_entities=False)
        flames: list[Entity] = []
        for idx in range(9):
            ang = idx * (2.0 * math.pi / 9.0)
            rad = 0.55 + (idx % 3) * 0.72
            fl = Entity(
                parent=root,
                model="cube",
                position=(math.cos(ang) * rad, 0.42, math.sin(ang) * rad),
                scale=(0.42, 0.85, 0.42),
                rotation_y=random.uniform(0, 90),
                color=rgba32(255, 165, 32, 215),
                unlit=True,
                add_to_scene_entities=False,
            )
            flames.append(fl)
        self.fires.append(FireZone(root=root, flames=flames, center=pos, radius=2.85, ttl=7.0))

    def is_segment_blocked_by_smoke(self, p1: Vec3, p2: Vec3) -> bool:
        if not self.smokes:
            return False
        seg = p2 - p1
        seg_len_sq = seg.x * seg.x + seg.y * seg.y + seg.z * seg.z
        if seg_len_sq < 1e-5:
            return False
        for sm in self.smokes:
            t = clamp((sm.center - p1).dot(seg) / seg_len_sq, 0.0, 1.0)
            closest = p1 + seg * t
            if (closest - sm.center).length() < sm.radius:
                return True
        return False

    def plant_c4(self, pos: Vec3, site_name: str = "A") -> bool:
        if self.c4_planted:
            return False
        self.c4_planted = True
        self.c4_defused = False
        self.c4_exploded = False
        self.c4_timer = 40.0
        self.c4_defuse_progress = 0.0
        self.c4_site_name = site_name
        self.c4_pos = Vec3(pos.x, 0.04, pos.z)
        self._c4_beep_accum = 0.0

        self.c4_entity = Entity(parent=scene, position=self.c4_pos, add_to_scene_entities=False)
        c4_mesh = load_safe_model("assets/models/c4.glb", normalize_to=0.38)
        if c4_mesh is not None:
            Entity(parent=self.c4_entity, model=c4_mesh, add_to_scene_entities=False)
        else:
            Entity(parent=self.c4_entity, model="cube", position=(0, 0.06, 0), scale=(0.32, 0.12, 0.24), color=rgb32(158, 142, 98), add_to_scene_entities=False)
        self.c4_led = Entity(
            parent=self.c4_entity,
            model="sphere",
            position=(0.0, 0.17, 0.0),
            scale=0.065,
            color=rgb32(255, 38, 32),
            unlit=True,
            add_to_scene_entities=False,
        )
        self.sound_mgr.play_sfx("c4_plant", volume=0.90)
        return True

    def step_defuse(self, dt: float, player_pos: Vec3, has_defuse_kit: bool, holding_use: bool) -> float:
        if not self.c4_planted or self.c4_defused or self.c4_exploded:
            return 0.0
        dist = Vec3(player_pos.x - self.c4_pos.x, 0.0, player_pos.z - self.c4_pos.z).length()
        if not holding_use or dist > 3.3:
            self.c4_defuse_progress = max(0.0, self.c4_defuse_progress - dt * 1.5)
            return 0.0
        req_time = 2.5 if has_defuse_kit else 4.5
        if self.c4_defuse_progress <= 0.01:
            self.sound_mgr.play_sfx("c4_defuse", volume=0.78)
        self.c4_defuse_progress += dt
        progress_ratio = clamp(self.c4_defuse_progress / req_time, 0.0, 1.0)
        if progress_ratio >= 1.0:
            self.c4_defused = True
            self.c4_planted = False
            if self.c4_led is not None:
                self.c4_led.color = rgb32(65, 245, 120)
            self.sound_mgr.play_sfx("c4_defuse", volume=0.95, pitch=1.25)
            if self.on_c4_defused is not None:
                self.on_c4_defused()
        return progress_ratio

    def spawn_loot_drop(self, pos: Vec3) -> None:
        kind = random.choice(("medkit", "armor", "ammo", "cash"))
        colors = {
            "medkit": rgb32(72, 232, 132),
            "armor": rgb32(78, 168, 255),
            "ammo": rgb32(242, 192, 68),
            "cash": rgb32(115, 245, 95),
        }
        drop_pos = Vec3(pos.x, 0.30, pos.z)
        ent = Entity(
            parent=scene,
            model="cube",
            position=drop_pos,
            scale=(0.28, 0.22, 0.28),
            color=colors[kind],
            add_to_scene_entities=False,
        )
        apply_pbr_material(ent, shininess=48.0, specular_strength=0.55)
        self.loot_drops.append(LootDrop(entity=ent, kind=kind, pos=drop_pos, ttl=18.0, phase=random.uniform(0, 6.28)))

    def place_tactical_ping(self, origin: Vec3, direction: Vec3, ignore_list: list[Any]) -> Vec3 | None:
        hit = raycast(origin, direction, distance=120.0, ignore=ignore_list)
        if not hit.hit:
            return None
        self.ping_pos = Vec3(hit.world_point)
        self.ping_entity.position = self.ping_pos
        self.ping_entity.enabled = True
        self.ping_ttl = 5.5
        self.sound_mgr.play_sfx("c4_beep", volume=0.45, pitch=1.45)
        return self.ping_pos

    def reset_round_fx(self) -> None:
        for slot in self._shell_pool:
            slot.active = False
            slot.entity.enabled = False
        for slot in self._tracer_pool:
            slot.active = False
            slot.entity.enabled = False
        for slot in self._particle_pool:
            slot.active = False
            slot.entity.enabled = False
        for pop in self.popups:
            destroy(pop.entity)
        for gr in self.grenades:
            destroy(gr.entity)
        for sm in self.smokes:
            destroy(sm.root)
        for fz in self.fires:
            destroy(fz.root)
        for ld in self.loot_drops:
            destroy(ld.entity)
        if self.c4_entity is not None:
            destroy(self.c4_entity)
            self.c4_entity = None
            self.c4_led = None

        self.popups.clear()
        self.grenades.clear()
        self.smokes.clear()
        self.fires.clear()
        self.loot_drops.clear()

        self.c4_planted = False
        self.c4_defused = False
        self.c4_exploded = False
        self.c4_defuse_progress = 0.0
        self.ping_entity.enabled = False
        self.ping_pos = None
        self._p3d_point_light.setColor((0.0, 0.0, 0.0, 1.0))

    def update(self, dt: float, ignore_entities: list[Any]) -> None:
        if self._light_ttl > 0.0:
            self._light_ttl = max(0.0, self._light_ttl - dt)
            fade = self._light_ttl / self._light_max_ttl
            self._p3d_point_light.setColor(
                (self._light_rgb[0] * fade, self._light_rgb[1] * fade, self._light_rgb[2] * fade, 1.0)
            )

        # Обновление кольцевых пулов гильз, трассеров и частиц (без создания/удаления нод!)
        for sh in self._shell_pool:
            if not sh.active:
                continue
            sh.ttl -= dt
            if sh.ttl <= 0.0:
                sh.active = False
                sh.entity.enabled = False
                continue
            sh.vel.y -= 14.5 * dt
            sh.entity.position += sh.vel * dt
            sh.entity.rotation += sh.rot_vel * dt
            if sh.entity.y <= 0.03:
                sh.entity.y = 0.03
                sh.vel.y = abs(sh.vel.y) * 0.36
                sh.vel.x *= 0.62
                sh.vel.z *= 0.62
                sh.rot_vel *= 0.55
                if not sh.bounced:
                    sh.bounced = True
                    self.sound_mgr.play_sfx("shell_clink", volume=0.30, pitch=random.uniform(0.92, 1.15))

        for tr in self._tracer_pool:
            if not tr.active:
                continue
            tr.ttl -= dt
            if tr.ttl <= 0.0:
                tr.active = False
                tr.entity.enabled = False

        for pt in self._particle_pool:
            if not pt.active:
                continue
            pt.ttl -= dt
            if pt.ttl <= 0.0:
                pt.active = False
                pt.entity.enabled = False
                continue
            pt.vel.y -= pt.gravity * dt
            pt.entity.position += pt.vel * dt
            pt.entity.scale = max(0.004, pt.base_scale * (pt.ttl / pt.max_ttl))

        if self.popups:
            kept_p: list[_DamageNumber] = []
            for dm in self.popups:
                dm.ttl -= dt
                if dm.ttl <= 0.0:
                    destroy(dm.entity)
                else:
                    dm.entity.y += dm.vel_y * dt
                    kept_p.append(dm)
            self.popups = kept_p

        if self.grenades:
            kept_g: list[ActiveGrenade] = []
            for gr in self.grenades:
                gr.fuse -= dt
                gr.vel.y -= 17.5 * dt
                step_vec = gr.vel * dt
                step_len = step_vec.length()
                if step_len > 0.001:
                    hit = raycast(gr.entity.world_position, step_vec.normalized(), distance=step_len + 0.14, ignore=[gr.entity, *ignore_entities])
                    if hit.hit:
                        if gr.g_type == "molotov" and hit.world_normal.y > 0.55:
                            gr.entity.position = Vec3(hit.world_point) + Vec3(0, 0.05, 0)
                            self._detonate_grenade(gr)
                            continue
                        nrm = Vec3(hit.world_normal)
                        gr.vel = (gr.vel - nrm * (2.0 * gr.vel.dot(nrm))) * 0.52
                        gr.entity.position = Vec3(hit.world_point) + nrm * 0.15
                        if gr.bounces < 3:
                            gr.bounces += 1
                            self.sound_mgr.play_sfx("empty_click", volume=0.35, pitch=0.78)
                    else:
                        gr.entity.position += step_vec
                gr.entity.rotation_x += 340.0 * dt
                gr.entity.rotation_z += 240.0 * dt
                if gr.entity.y < 0.10:
                    gr.entity.y = 0.10
                    gr.vel.y = abs(gr.vel.y) * 0.42
                    gr.vel.x *= 0.72
                    gr.vel.z *= 0.72
                if gr.fuse <= 0.0:
                    self._detonate_grenade(gr)
                else:
                    kept_g.append(gr)
            self.grenades = kept_g

        if self.smokes:
            kept_sm: list[SmokeCloud] = []
            for sm in self.smokes:
                sm.ttl -= dt
                if sm.ttl <= 0.0:
                    destroy(sm.root)
                else:
                    grow = clamp((sm.max_ttl - sm.ttl) / 0.85, 0.25, 1.0)
                    alpha = int(226 * clamp(sm.ttl / 2.2, 0.0, 1.0))
                    for pf in sm.puffs:
                        pf.scale = pf._target_scale * grow
                        pf.color = rgba32(196, 202, 208, alpha)
                    kept_sm.append(sm)
            self.smokes = kept_sm

        if self.fires:
            kept_f: list[FireZone] = []
            for fz in self.fires:
                fz.ttl -= dt
                if fz.ttl <= 0.0:
                    destroy(fz.root)
                else:
                    fz.tick_accum += dt
                    for idx, fl in enumerate(fz.flames):
                        fl.scale_y = 0.55 + 0.45 * abs(math.sin(fz.ttl * 9.0 + idx))
                    if fz.tick_accum >= 0.35:
                        fz.tick_accum = 0.0
                        self.flash_world_light(fz.center + Vec3(0, 0.6, 0), rgb=(1.0, 0.44, 0.10), intensity=2.0, duration=0.22)
                        if self.on_fire_tick is not None:
                            self.on_fire_tick(fz.center, fz.radius)
                    kept_f.append(fz)
            self.fires = kept_f

        if self.c4_planted and not self.c4_defused and not self.c4_exploded:
            self.c4_timer -= dt
            beep_interval = clamp(0.12 + (self.c4_timer / 40.0) * 0.82, 0.11, 0.95)
            self._c4_beep_accum += dt
            if self._c4_beep_accum >= beep_interval:
                self._c4_beep_accum = 0.0
                self.sound_mgr.play_sfx("c4_beep", volume=0.72, pitch=clamp(1.38 - self.c4_timer * 0.008, 0.95, 1.45))
                if self.c4_led is not None:
                    self.c4_led.enabled = True
                    self.flash_world_light(self.c4_pos + Vec3(0, 0.35, 0), rgb=(1.0, 0.12, 0.10), intensity=2.2, duration=0.07)
            elif self.c4_led is not None and self._c4_beep_accum > beep_interval * 0.45:
                self.c4_led.enabled = False

            if self.c4_timer <= 0.0:
                self.c4_exploded = True
                self.c4_planted = False
                self.trigger_explosion_vfx(self.c4_pos, radius=24.0, max_damage=240.0, source_label="C4 BOMB")
                if self.on_c4_exploded is not None:
                    self.on_c4_exploded()

        if self.loot_drops:
            kept_ld: list[LootDrop] = []
            for ld in self.loot_drops:
                ld.ttl -= dt
                if ld.ttl <= 0.0:
                    destroy(ld.entity)
                else:
                    ld.phase += dt * 3.2
                    ld.entity.rotation_y += dt * 85.0
                    ld.entity.y = 0.28 + math.sin(ld.phase) * 0.06
                    kept_ld.append(ld)
            self.loot_drops = kept_ld

        if self.ping_entity.enabled:
            self.ping_ttl -= dt
            self.ping_entity.rotation_y += dt * 120.0
            if self.ping_ttl <= 0.0:
                self.ping_entity.enabled = False
                self.ping_pos = None
