"""
Реалистичная 3D-арена CS2 (Sandstone Dust2 Remastered, 64x64 м):
- Попиксельное освещение Panda3D ShaderAuto + мягкие тени DirectionalLight (2048x2048) + линейный туман (Fog)
- 3 режима времени суток в реальном времени (DAY / SUNSET / NIGHT по клавише F6 или в настройках)
- 3D-небосвод: диск солнца/луны, плывущие объёмные 3D-облака, дальние горные хребты и силуэты башен за стенами
- Проработанная 3D-архитектура: стены с карнизами и зубцами, наклонные деревянные «Двойные двери» на Миде,
  ступенчатая лестница на балкон Catwalk (Short A), морской контейнер на B, бункеры из мешков с песком,
  бетонные блоки, фонарные столбы с тёплым светом, силовые кабели, кондиционеры и пальмы с качающейся кроной
- 3D-техника для укрытий: тактический броневик Humvee у базы CT и машина на Long A
- Интерактивные разрушаемые объекты: взрывающиеся красные бочки с горючим и простреливаемые деревянные ящики
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable

from panda3d.core import Fog
from ursina import AmbientLight, DirectionalLight, Entity, PointLight, Sky, Text, Vec2, Vec3, color, destroy, scene

from src.settings import (
    apply_pbr_material,
    load_safe_model,
    load_safe_texture,
    resolve_font_path,
    rgb32,
    rgba32,
)


@dataclass
class DestructibleProp:
    kind: str  # 'barrel' | 'wood_crate'
    entity: Entity
    pos: Vec3
    hp: int
    max_hp: int
    alive: bool = True

    def take_damage(
        self,
        dmg: int,
        on_barrel_explode: Callable[[Vec3], None] | None = None,
        on_wood_shatter: Callable[[Vec3], None] | None = None,
    ) -> bool:
        if not self.alive:
            return False
        self.hp -= int(dmg)
        if self.hp <= 0:
            self.alive = False
            self.entity.collider = None
            self.entity.enabled = False
            if self.kind == "barrel" and on_barrel_explode is not None:
                on_barrel_explode(self.pos)
            elif on_wood_shatter is not None:
                on_wood_shatter(self.pos)
            return True
        return False


class ArenaMap:
    """Управляет 3D-геометрией карты, освещением, атмосферой, точками плентов A/B и разрушаемыми объектами."""

    ARENA_SIZE: float = 64.0
    WALL_HEIGHT: float = 7.2

    def __init__(self, shadows_enabled: bool = True, time_of_day: str = "DAY") -> None:
        self.root = Entity(name="arena_map_root")
        self.entities: list[Entity] = []
        self._font = resolve_font_path("assets/fonts/hud_font.ttf")

        # Включаем попиксельный шейдерный генератор Panda3D для 3D-реализма (тени, блики, туман, фонари)
        try:
            scene.setShaderAuto()
        except Exception:
            pass

        # Загрузка текстур материалов с анизотропной фильтрацией
        self._wall_tex = load_safe_texture("assets/textures/wall_sandstone.png")
        self._floor_tex = load_safe_texture("assets/textures/floor_dust.png")
        self._crate_tex = load_safe_texture("assets/textures/crate_wood.png")
        self._asphalt_tex = load_safe_texture("assets/textures/asphalt_road.png")
        self._metal_tex = load_safe_texture("assets/textures/metal_plate.png")
        self._container_tex = load_safe_texture("assets/textures/container_blue.png")
        self._sandbag_tex = load_safe_texture("assets/textures/sandbag_fabric.png")
        self._barrel_tex = load_safe_texture("assets/textures/barrel_hazard.png")

        # Глобальное освещение + тени 2048x2048 + атмосферная дымка
        self.shadows_enabled = bool(shadows_enabled)
        self.time_of_day = time_of_day if time_of_day in ("DAY", "SUNSET", "NIGHT") else "DAY"

        self.sun_light = DirectionalLight(
            parent=self.root,
            y=28,
            z=-18,
            shadows=self.shadows_enabled,
            shadow_map_resolution=Vec2(2048, 2048),
        )
        self.sun_light.look_at(Vec3(10, -1, 12))

        self.ambient_light = AmbientLight(parent=self.root, color=rgba32(158, 168, 188, 255))
        self.sky = Sky(color=rgb32(155, 198, 242))

        # Тёплые точечные фонари над плентами A и B (особенно атмосферны на закате и ночью!)
        self.site_a_light = PointLight(parent=self.root, position=(19.5, 5.2, 1.0), color=rgb32(255, 198, 125))
        self.site_b_light = PointLight(parent=self.root, position=(-19.0, 5.2, 0.5), color=rgb32(255, 192, 120))
        for pl in (self.site_a_light, self.site_b_light):
            try:
                pl._light.setAttenuation((1.0, 0.065, 0.018))
            except Exception:
                pass

        self.world_fog = Fog("cs2_atmosphere_fog")
        scene.setFog(self.world_fog)

        # Координаты спавнов и плентов A / B
        self.ct_spawn_pos: Vec3 = Vec3(0.0, 0.2, -26.5)
        self.ct_spawn_yaw: float = 0.0

        self.site_a_center: Vec3 = Vec3(20.5, 0.72, 1.0)
        self.site_b_center: Vec3 = Vec3(-20.5, 0.05, 0.5)
        self.site_radius: float = 4.8

        self.t_spawn_points: list[Vec3] = [
            Vec3(0.0, 0.2, 26.5),
            Vec3(-9.5, 0.2, 25.5),
            Vec3(9.5, 0.2, 25.5),
            Vec3(-22.0, 0.2, 19.0),
            Vec3(22.0, 0.2, 19.0),
            Vec3(-21.0, 0.2, 6.5),
            Vec3(21.0, 0.2, 7.5),
            Vec3(5.0, 0.2, 16.5),
            Vec3(-5.5, 0.2, 16.5),
            Vec3(14.5, 0.2, 22.5),
        ]

        self.patrol_waypoints: list[Vec3] = [
            Vec3(0.0, 0.2, 17.5),
            Vec3(-12.5, 0.2, 14.5),
            Vec3(12.5, 0.2, 14.5),
            Vec3(-22.5, 0.2, 4.5),
            Vec3(-21.5, 0.2, -9.5),
            Vec3(-10.0, 0.2, -5.0),
            Vec3(0.0, 0.2, 3.0),
            Vec3(0.0, 0.2, -8.5),
            Vec3(11.0, 0.2, -4.5),
            Vec3(22.5, 0.2, 5.5),
            Vec3(22.5, 0.2, -10.5),
            Vec3(-12.5, 0.2, -16.5),
            Vec3(12.5, 0.2, -16.5),
            Vec3(20.0, 0.8, 1.0),
            Vec3(-20.0, 0.2, 0.5),
        ]

        # Списки анимируемых объектов окружения и разрушаемых бочек/ящиков
        self.clouds: list[Entity] = []
        self.palm_fronds: list[Entity] = []
        self.dust_motes: list[tuple[Entity, Vec3, float]] = []
        self.lamp_bulbs: list[Entity] = []
        self.sun_disc: Entity | None = None
        self.destructibles: list[DestructibleProp] = []
        self._barrel_spawns: list[Vec3] = [
            Vec3(-3.6, 0.0, -3.2),
            Vec3(15.2, 0.0, 6.8),
            Vec3(23.2, 0.70, -4.8),
            Vec3(-15.2, 0.0, 5.2),
            Vec3(-23.5, 0.0, -5.8),
            Vec3(6.8, 0.0, 14.2),
        ]
        self._breakable_crate_spawns: list[Vec3] = [
            Vec3(2.8, 0.65, -4.2),
            Vec3(-9.5, 0.65, 3.5),
            Vec3(10.2, 0.65, 4.2),
            Vec3(-16.2, 0.65, -8.5),
            Vec3(16.8, 0.65, -11.5),
            Vec3(0.0, 0.65, 11.2),
        ]
        self._env_time: float = 0.0

        if not self._try_load_custom_map_glb():
            self._build_realistic_3d_arena()

        self._build_sky_horizon_and_atmosphere()
        self._spawn_destructible_props()
        self.apply_atmosphere(self.time_of_day, self.shadows_enabled)

    def _try_load_custom_map_glb(self) -> bool:
        custom_map_np = load_safe_model("assets/models/arena_map.glb")
        if custom_map_np is None:
            return False
        try:
            map_ent = Entity(parent=self.root, model=custom_map_np, collider="mesh", position=(0, 0, 0))
            self.entities.append(map_ent)
            safety_floor = Entity(
                parent=self.root,
                model="cube",
                position=(0.0, -1.0, 0.0),
                scale=(140.0, 1.0, 140.0),
                collider="box",
                visible=False,
            )
            self.entities.append(safety_floor)
            return True
        except Exception:
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # АТМОСФЕРА И СМЕНА ВРЕМЕНИ СУТОК (DAY / SUNSET / NIGHT)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def apply_atmosphere(self, time_of_day: str, shadows_enabled: bool | None = None) -> None:
        if time_of_day in ("DAY", "SUNSET", "NIGHT"):
            self.time_of_day = time_of_day
        if shadows_enabled is not None:
            self.shadows_enabled = bool(shadows_enabled)
            try:
                self.sun_light.shadows = self.shadows_enabled
            except Exception:
                pass

        if self.time_of_day == "DAY":
            self.sun_light.position = Vec3(-18, 30, -16)
            self.sun_light.look_at(Vec3(8, -1, 10))
            self.sun_light.color = rgb32(255, 246, 224)
            self.ambient_light.color = rgba32(162, 174, 194, 255)
            self.sky.color = rgb32(138, 192, 245)
            self.world_fog.setColor(0.84, 0.79, 0.69)
            self.world_fog.setLinearRange(42.0, 155.0)
            lamp_col = rgb32(255, 215, 155)
            self.site_a_light.color = rgb32(95, 78, 52)
            self.site_b_light.color = rgb32(95, 78, 52)
            if self.sun_disc is not None:
                self.sun_disc.position = Vec3(-48, 46, -52)
                self.sun_disc.color = rgb32(255, 248, 205)

        elif self.time_of_day == "SUNSET":
            self.sun_light.position = Vec3(-32, 14, -24)
            self.sun_light.look_at(Vec3(12, -1, 8))
            self.sun_light.color = rgb32(255, 156, 88)
            self.ambient_light.color = rgba32(126, 104, 136, 255)
            self.sky.color = rgb32(218, 118, 86)
            self.world_fog.setColor(0.82, 0.48, 0.36)
            self.world_fog.setLinearRange(34.0, 135.0)
            lamp_col = rgb32(255, 198, 110)
            self.site_a_light.color = rgb32(235, 165, 85)
            self.site_b_light.color = rgb32(235, 165, 85)
            if self.sun_disc is not None:
                self.sun_disc.position = Vec3(-68, 20, -56)
                self.sun_disc.color = rgb32(255, 128, 58)

        else:  # NIGHT
            self.sun_light.position = Vec3(18, 28, -18)
            self.sun_light.look_at(Vec3(-6, -1, 8))
            self.sun_light.color = rgb32(82, 108, 162)
            self.ambient_light.color = rgba32(58, 68, 96, 255)
            self.sky.color = rgb32(18, 26, 46)
            self.world_fog.setColor(0.08, 0.11, 0.18)
            self.world_fog.setLinearRange(28.0, 118.0)
            lamp_col = rgb32(255, 214, 128)
            self.site_a_light.color = rgb32(255, 196, 112)
            self.site_b_light.color = rgb32(255, 196, 112)
            if self.sun_disc is not None:
                self.sun_disc.position = Vec3(46, 44, -52)
                self.sun_disc.color = rgb32(210, 226, 255)

        for bulb in self.lamp_bulbs:
            bulb.color = lamp_col

        try:
            self.sun_light.update_bounds(self.root)
        except Exception:
            pass

    def cycle_time_of_day(self) -> str:
        order = ("DAY", "SUNSET", "NIGHT")
        nxt = order[(order.index(self.time_of_day) + 1) % len(order)]
        self.apply_atmosphere(nxt)
        return nxt

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # СТРОИТЕЛЬНЫЕ ПРИМИТИВЫ ПОВЫШЕННОЙ 3D-ДЕТАЛИЗАЦИИ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _add_wall(
        self,
        pos: tuple[float, float, float],
        scale: tuple[float, float, float],
        tint: Any = None,
        cornice: bool = True,
    ) -> Entity:
        wall = Entity(
            parent=self.root,
            model="cube",
            position=pos,
            scale=scale,
            texture=self._wall_tex,
            texture_scale=Vec2(max(1.0, max(scale[0], scale[2]) / 3.2), max(1.0, scale[1] / 3.2)),
            color=tint if tint is not None else rgb32(232, 212, 176),
            collider="box",
        )
        apply_pbr_material(wall, "stone")
        self.entities.append(wall)

        # Каменный верхний карниз (придаёт стенам архитектурный 3D-объём!)
        if cornice and scale[1] >= 2.6:
            cap = Entity(
                parent=self.root,
                model="cube",
                position=(pos[0], pos[1] + scale[1] * 0.5 + 0.11, pos[2]),
                scale=(scale[0] + 0.22, 0.22, scale[2] + 0.22),
                texture=self._wall_tex,
                color=rgb32(196, 174, 138),
            )
            apply_pbr_material(cap, "stone")
            self.entities.append(cap)
        return wall

    def _add_crate(
        self,
        pos: tuple[float, float, float],
        size: float = 1.45,
        rot_y: float = 0.0,
    ) -> Entity:
        crate_np = load_safe_model("assets/models/crate.glb")
        if crate_np is not None:
            crate = Entity(
                parent=self.root,
                position=pos,
                scale=(size, size, size),
                rotation_y=rot_y,
                collider="box",
            )
            mesh_e = Entity(parent=crate, model=crate_np)
            apply_pbr_material(mesh_e, "wood")
        else:
            crate = Entity(
                parent=self.root,
                model="cube",
                position=pos,
                scale=(size, size, size),
                rotation_y=rot_y,
                texture=self._crate_tex,
                color=rgb32(196, 152, 96),
                collider="box",
            )
            apply_pbr_material(crate, "wood")
        crate.surface_material = "wood"
        self.entities.append(crate)
        return crate

    def _add_sandbag_bunker(self, pos: tuple[float, float, float], rot_y: float = 0.0) -> None:
        """Собирает реалистичный бруствер из уложенных вразбежку 3D-мешков с песком."""
        holder = Entity(parent=self.root, position=pos, rotation_y=rot_y)
        col_box = Entity(
            parent=holder,
            model=None,
            position=(0.0, 0.55, 0.0),
            scale=(2.5, 1.1, 0.72),
            collider="box",
        )
        col_box.surface_material = "stone"
        for row in range(3):
            y = 0.18 + row * 0.34
            shift = 0.25 if row % 2 == 1 else 0.0
            count = 3 if row == 2 else 4
            for i in range(count):
                x = -0.95 + i * 0.64 + shift
                bag = Entity(
                    parent=holder,
                    model="sphere",
                    position=(x, y, 0.0),
                    scale=(0.68, 0.36, 0.54),
                    texture=self._sandbag_tex,
                    color=rgb32(196, 176, 134),
                )
                apply_pbr_material(bag, "fabric")
        self.entities.append(holder)

    def _add_jersey_barrier(self, pos: tuple[float, float, float], rot_y: float = 0.0) -> None:
        """Бетонный дорожный отбойник с широким основанием и сужением кверху."""
        holder = Entity(parent=self.root, position=pos, rotation_y=rot_y)
        base = Entity(
            parent=holder,
            model="cube",
            position=(0.0, 0.28, 0.0),
            scale=(2.8, 0.56, 0.72),
            texture=self._asphalt_tex,
            color=rgb32(178, 180, 184),
            collider="box",
        )
        top = Entity(
            parent=holder,
            model="cube",
            position=(0.0, 0.80, 0.0),
            scale=(2.75, 0.54, 0.40),
            texture=self._asphalt_tex,
            color=rgb32(192, 194, 198),
            collider="box",
        )
        # Полоса безопасности
        Entity(
            parent=holder,
            model="cube",
            position=(0.0, 0.96, 0.0),
            scale=(2.76, 0.12, 0.42),
            color=rgb32(232, 178, 42),
        )
        apply_pbr_material(base, "stone")
        apply_pbr_material(top, "stone")
        self.entities.append(holder)

    def _add_palm_tree(self, pos: tuple[float, float, float], height_scale: float = 1.0) -> None:
        """3D-пальма оазиса с изогнутым сегментированным стволом и качающимися листьями."""
        holder = Entity(parent=self.root, position=pos, scale=height_scale)
        trunk_col = rgb32(124, 88, 54)
        lean_x = 0.0
        for seg in range(7):
            y = 0.45 + seg * 0.78
            lean_x += 0.08 * math.sin(seg * 0.45)
            t_seg = Entity(
                parent=holder,
                model="cube",
                position=(lean_x, y, 0.0),
                scale=(0.42 - seg * 0.03, 0.84, 0.42 - seg * 0.03),
                rotation_z=-seg * 1.8,
                rotation_y=seg * 25.0,
                color=trunk_col,
                collider="box" if seg < 3 else None,
            )
            t_seg.surface_material = "wood"
            apply_pbr_material(t_seg, "wood")

        crown_pos = Vec3(lean_x, 6.0, 0.0)
        leaf_col = rgb32(62, 134, 54)
        for idx in range(7):
            yaw = idx * (360.0 / 7.0)
            pivot = Entity(parent=holder, position=crown_pos, rotation_y=yaw)
            frond = Entity(
                parent=pivot,
                model="cube",
                position=(0.0, -0.15, 1.35),
                scale=(0.55, 0.08, 2.65),
                rotation_x=24.0,
                color=leaf_col,
            )
            apply_pbr_material(frond, "foliage")
            self.palm_fronds.append(frond)
        self.entities.append(holder)

    def _add_street_lamp(self, pos: tuple[float, float, float], rot_y: float = 0.0) -> None:
        """Металлический фонарный столб со светящимся плафоном."""
        holder = Entity(parent=self.root, position=pos, rotation_y=rot_y)
        pole = Entity(
            parent=holder,
            model="cube",
            position=(0.0, 2.7, 0.0),
            scale=(0.18, 5.4, 0.18),
            texture=self._metal_tex,
            color=rgb32(68, 72, 78),
            collider="box",
        )
        pole.surface_material = "metal"
        apply_pbr_material(pole, "steel")
        arm = Entity(
            parent=holder,
            model="cube",
            position=(0.0, 5.35, 0.55),
            scale=(0.14, 0.14, 1.25),
            color=rgb32(68, 72, 78),
        )
        apply_pbr_material(arm, "steel")
        bulb = Entity(
            parent=holder,
            model="sphere",
            position=(0.0, 5.18, 1.05),
            scale=(0.34, 0.22, 0.34),
            color=rgb32(255, 215, 155),
            unlit=True,
        )
        self.lamp_bulbs.append(bulb)
        self.entities.append(holder)

    def _add_tactical_humvee(self, pos: tuple[float, float, float], rot_y: float = 0.0) -> None:
        """Детализированный 3D армейский броневик спецназа (колёса, капот, кабина, турель, фары)."""
        v = Entity(parent=self.root, position=pos, rotation_y=rot_y)
        armor_col = rgb32(84, 96, 78)
        dark_metal = rgb32(36, 38, 42)
        glass_col = rgb32(62, 108, 138)

        chassis = Entity(
            parent=v,
            model="cube",
            position=(0.0, 0.78, 0.0),
            scale=(2.25, 0.92, 4.65),
            texture=self._metal_tex,
            color=armor_col,
            collider="box",
        )
        chassis.surface_material = "metal"
        apply_pbr_material(chassis, "metal")

        cabin = Entity(
            parent=v,
            model="cube",
            position=(0.0, 1.56, -0.25),
            scale=(2.10, 0.78, 2.55),
            texture=self._metal_tex,
            color=armor_col,
            collider="box",
        )
        cabin.surface_material = "metal"
        apply_pbr_material(cabin, "metal")

        # Бронестекло и турельный щиток на крыше
        ws = Entity(
            parent=v,
            model="cube",
            position=(0.0, 1.56, 1.04),
            scale=(1.86, 0.56, 0.08),
            rotation_x=-18.0,
            color=glass_col,
        )
        apply_pbr_material(ws, "glass")
        Entity(parent=v, model="cube", position=(0.0, 2.15, -0.20), scale=(0.95, 0.42, 0.95), color=dark_metal)

        # 4 массивных колеса и горящие фары
        for wx in (-1.12, 1.12):
            for wz in (-1.45, 1.45):
                wheel = Entity(
                    parent=v,
                    model="sphere",
                    position=(wx, 0.48, wz),
                    scale=(0.44, 0.94, 0.94),
                    color=dark_metal,
                )
                apply_pbr_material(wheel, "polymer")
        for hx in (-0.78, 0.78):
            Entity(
                parent=v,
                model="sphere",
                position=(hx, 0.88, 2.34),
                scale=(0.22, 0.22, 0.10),
                color=rgb32(255, 245, 200),
                unlit=True,
            )
        self.entities.append(v)

    def _add_sedan_cover_car(self, pos: tuple[float, float, float], rot_y: float = 0.0) -> None:
        """Классическая легковушка на Long A для тактического укрытия (как Car на Dust2!)."""
        car = Entity(parent=self.root, position=pos, rotation_y=rot_y)
        body_col = rgb32(146, 56, 48)
        glass_col = rgb32(52, 72, 88)
        tire_col = rgb32(30, 32, 36)

        lower = Entity(
            parent=car,
            model="cube",
            position=(0.0, 0.62, 0.0),
            scale=(1.92, 0.68, 4.15),
            texture=self._metal_tex,
            color=body_col,
            collider="box",
        )
        lower.surface_material = "metal"
        apply_pbr_material(lower, "steel")

        roof = Entity(
            parent=car,
            model="cube",
            position=(0.0, 1.24, -0.15),
            scale=(1.68, 0.62, 2.05),
            color=body_col,
            collider="box",
        )
        roof.surface_material = "metal"
        apply_pbr_material(roof, "steel")

        Entity(parent=car, model="cube", position=(0.0, 1.22, 0.90), scale=(1.56, 0.50, 0.08), rotation_x=-26, color=glass_col)
        for wx in (-0.96, 0.96):
            for wz in (-1.28, 1.28):
                Entity(parent=car, model="sphere", position=(wx, 0.38, wz), scale=(0.34, 0.76, 0.76), color=tire_col)
        self.entities.append(car)

    def _add_shipping_container(self, pos: tuple[float, float, float], rot_y: float = 0.0) -> None:
        """Открытый сквозной 3D морской стальной контейнер (можно пройти сквозь него или залезть сверху!)."""
        c = Entity(parent=self.root, position=pos, rotation_y=rot_y)
        # Пол, две продольные стенки и крыша контейнера
        parts = [
            ((0.0, 0.08, 0.0), (2.6, 0.16, 6.2)),
            ((-1.24, 1.38, 0.0), (0.14, 2.60, 6.2)),
            ((1.24, 1.38, 0.0), (0.14, 2.60, 6.2)),
            ((0.0, 2.68, 0.0), (2.62, 0.16, 6.2)),
        ]
        for p_pos, p_sc in parts:
            panel = Entity(
                parent=c,
                model="cube",
                position=p_pos,
                scale=p_sc,
                texture=self._container_tex,
                texture_scale=Vec2(2, 4),
                color=rgb32(62, 118, 178),
                collider="box",
            )
            panel.surface_material = "metal"
            apply_pbr_material(panel, "metal")
        self.entities.append(c)

    def _add_site_marker(self, pos: Vec3, site_letter: str) -> None:
        """Рисует красную тактическую зону закладки бомбы [A] / [B] и 3D-табличку."""
        zone = Entity(
            parent=self.root,
            model="quad",
            position=pos + Vec3(0.0, 0.025, 0.0),
            rotation_x=90.0,
            scale=4.8,
            color=rgba32(215, 48, 38, 88),
            unlit=True,
        )
        self.entities.append(zone)
        kwargs: dict[str, Any] = {
            "parent": self.root,
            "text": f"[ SITE {site_letter} ]",
            "position": pos + Vec3(0.0, 3.6, 0.0),
            "origin": (0.0, 0.0),
            "scale": 8.5,
            "color": rgb32(255, 92, 68),
            "billboard": True,
        }
        try:
            lbl = Text(**kwargs, font=self._font) if self._font else Text(**kwargs)
        except Exception:
            lbl = Text(**kwargs)
        self.entities.append(lbl)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ГЕНЕРАЦИЯ ГЕОМЕТРИИ АРЕНЫ, ПАНОРАМЫ НЕБА И РАЗРУШАЕМЫХ ОБЪЕКТОВ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_realistic_3d_arena(self) -> None:
        half = self.ARENA_SIZE * 0.5
        wh = self.WALL_HEIGHT

        # 1. Основной песчаный пол арены
        floor = Entity(
            parent=self.root,
            model="cube",
            position=(0.0, -0.5, 0.0),
            scale=(self.ARENA_SIZE, 1.0, self.ARENA_SIZE),
            texture=self._floor_tex,
            texture_scale=Vec2(26, 26),
            color=rgb32(224, 202, 162),
            collider="box",
        )
        floor.surface_material = "stone"
        apply_pbr_material(floor, "sand")
        self.entities.append(floor)

        # Асфальтированная центральная дорога на Миде с разметкой
        mid_road = Entity(
            parent=self.root,
            model="cube",
            position=(0.0, -0.47, 0.0),
            scale=(7.8, 1.0, 52.0),
            texture=self._asphalt_tex,
            texture_scale=Vec2(1, 14),
            color=rgb32(195, 198, 204),
        )
        apply_pbr_material(mid_road, "asphalt")
        self.entities.append(mid_road)

        # 2. Высокие крепостные стены периметра с карнизами и зубцами
        self._add_wall((0.0, wh * 0.5, half), (self.ARENA_SIZE + 1.4, wh, 1.4))
        self._add_wall((0.0, wh * 0.5, -half), (self.ARENA_SIZE + 1.4, wh, 1.4))
        self._add_wall((half, wh * 0.5, 0.0), (1.4, wh, self.ARENA_SIZE + 1.4))
        self._add_wall((-half, wh * 0.5, 0.0), (1.4, wh, self.ARENA_SIZE + 1.4))

        for bx in range(-28, 30, 8):
            self._add_wall((bx, wh + 0.55, half), (2.2, 0.9, 1.3), cornice=False)
            self._add_wall((bx, wh + 0.55, -half), (2.2, 0.9, 1.3), cornice=False)

        # 3. Базы CT (юг) и T (север): защитные стены + броневик Humvee на базе CT
        self._add_wall((0.0, 1.85, -20.5), (9.5, 3.7, 1.0), rgb32(214, 194, 158))
        self._add_wall((0.0, 1.85, 21.0), (10.0, 3.7, 1.0), rgb32(214, 194, 158))
        self._add_tactical_humvee((-8.5, 0.0, -24.5), rot_y=28.0)
        self._add_jersey_barrier((7.5, 0.0, -22.5), rot_y=-18.0)
        self._add_sandbag_bunker((-7.5, 0.0, 21.0), rot_y=15.0)

        # 4. Центральный Мид — Знаменитые «Двойные деревянные двери» с узкой щелью для прострела!
        self._add_wall((-6.2, 2.1, -1.5), (8.4, 4.2, 1.1))
        self._add_wall((6.2, 2.1, -1.5), (8.4, 4.2, 1.1))
        self._add_wall((0.0, 4.8, -1.5), (4.4, 1.3, 1.2), rgb32(186, 162, 128))

        for sign_x, door_rot in ((-1.15, 22.0), (1.15, -22.0)):
            door_leaf = Entity(
                parent=self.root,
                model="cube",
                position=(sign_x, 1.85, -1.45),
                scale=(1.55, 3.7, 0.16),
                rotation_y=door_rot,
                texture=self._crate_tex,
                color=rgb32(162, 116, 68),
                collider="box",
            )
            door_leaf.surface_material = "wood"
            door_leaf.penetrable_wood = True
            apply_pbr_material(door_leaf, "wood")
            self.entities.append(door_leaf)

        # Знаменитый ящик Xbox + лестница на балкон Catwalk (Short A)!
        self._add_crate((-2.5, 0.55, 0.6), size=1.1, rot_y=8.0)
        self._add_crate((-1.2, 0.82, 0.7), size=1.64, rot_y=4.0)

        # Ступенчатый подъём на балкон Catwalk вдоль восточной стороны Мида
        for step_i in range(6):
            st = Entity(
                parent=self.root,
                model="cube",
                position=(6.2, 0.18 + step_i * 0.30, 5.2 - step_i * 0.85),
                scale=(2.6, 0.36, 0.92),
                texture=self._wall_tex,
                color=rgb32(208, 186, 148),
                collider="box",
            )
            apply_pbr_material(st, "stone")
            self.entities.append(st)

        catwalk = Entity(
            parent=self.root,
            model="cube",
            position=(11.2, 1.85, -0.8),
            scale=(9.6, 0.36, 3.2),
            texture=self._wall_tex,
            texture_scale=Vec2(4, 2),
            color=rgb32(204, 182, 144),
            collider="box",
        )
        apply_pbr_material(catwalk, "stone")
        self.entities.append(catwalk)
        # Перила балкона Catwalk
        self._add_wall((9.2, 2.45, 0.72), (5.2, 0.85, 0.22), rgb32(175, 154, 122), cornice=False)

        # 5. Восточное крыло — Плент A (возвышение, рампа, машина на Long A, бункер и ящики)
        a_platform = Entity(
            parent=self.root,
            model="cube",
            position=(20.5, 0.35, 1.0),
            scale=(12.5, 0.70, 16.5),
            texture=self._wall_tex,
            texture_scale=Vec2(6, 8),
            color=rgb32(210, 186, 145),
            collider="box",
        )
        apply_pbr_material(a_platform, "stone")
        self.entities.append(a_platform)
        self._add_site_marker(self.site_a_center, "A")

        self._add_wall((13.6, 0.18, -4.0), (1.8, 0.36, 5.0), rgb32(205, 182, 142), cornice=False)
        self._add_wall((15.2, 2.2, 11.2), (8.2, 4.4, 1.1))
        self._add_wall((15.2, 2.2, -11.2), (8.2, 4.4, 1.1))

        self._add_crate((20.2, 1.45, 2.6), size=1.5, rot_y=12.0)
        self._add_crate((21.8, 1.45, 2.4), size=1.5, rot_y=-5.0)
        self._add_crate((21.0, 2.95, 2.5), size=1.45, rot_y=20.0)
        self._add_sandbag_bunker((18.0, 0.70, -4.8), rot_y=-12.0)
        self._add_sedan_cover_car((24.8, 0.0, -16.5), rot_y=-24.0)

        # 6. Западное крыло — Плент B (колоннада, морской контейнер, снайперское окно и туннель)
        self._add_site_marker(self.site_b_center, "B")
        self._add_wall((-14.8, 2.2, 9.8), (1.2, 4.4, 9.8))
        self._add_wall((-14.8, 2.2, -10.2), (1.2, 4.4, 9.2))
        self._add_wall((-14.8, 0.60, -0.5), (1.0, 1.20, 4.8), rgb32(192, 168, 130), cornice=False)

        for pz in (-6.0, 1.0, 8.0):
            self._add_wall((-23.5, 2.4, pz), (1.6, 4.8, 1.6), rgb32(204, 178, 138))

        self._add_shipping_container((-19.5, 0.0, 11.2), rot_y=14.0)
        self._add_sandbag_bunker((-18.5, 0.0, -8.5), rot_y=22.0)
        self._add_jersey_barrier((-8.5, 0.0, -13.5), rot_y=32.0)

        self._add_crate((-19.2, 0.75, -1.8), size=1.5, rot_y=-14.0)
        self._add_crate((-18.9, 2.25, -1.8), size=1.4, rot_y=18.0)
        self._add_crate((9.2, 0.75, -12.8), size=1.5, rot_y=-12.0)
        self._add_crate((8.8, 0.75, 13.0), size=1.5, rot_y=15.0)
        self._add_crate((-8.8, 0.75, 13.2), size=1.5, rot_y=-8.0)

        # 7. Пальмы оазиса, уличные фонари и воздушные кабели между зданиями
        self._add_palm_tree((-27.5, 0.0, -24.5), height_scale=1.05)
        self._add_palm_tree((27.5, 0.0, 24.0), height_scale=1.12)
        self._add_palm_tree((-27.0, 0.0, 24.5), height_scale=0.96)
        self._add_palm_tree((27.2, 0.0, -25.0), height_scale=1.00)

        self._add_street_lamp((16.5, 0.0, 1.0), rot_y=90.0)
        self._add_street_lamp((-16.0, 0.0, 1.0), rot_y=-90.0)
        self._add_street_lamp((-3.8, 0.0, -14.5), rot_y=0.0)
        self._add_street_lamp((3.8, 0.0, 14.5), rot_y=180.0)

        # Провисшие линии электропередач над Мидом
        for cz in (-10.0, 6.5):
            cable = Entity(
                parent=self.root,
                model="cube",
                position=(0.0, 6.4, cz),
                scale=(28.0, 0.04, 0.04),
                rotation_z=1.5,
                color=rgb32(28, 30, 34),
            )
            self.entities.append(cable)

    def _build_sky_horizon_and_atmosphere(self) -> None:
        """Создаёт 3D-солнце, облака, дальние горы за периметром и парящие пылинки в воздухе."""
        self.sun_disc = Entity(
            parent=self.root,
            model="sphere",
            position=(-48, 46, -52),
            scale=7.5,
            color=rgb32(255, 248, 205),
            unlit=True,
        )

        # Объёмные 3D-облака в небе
        rng = random.Random(77)
        for _ in range(9):
            cx = rng.uniform(-75.0, 75.0)
            cy = rng.uniform(28.0, 42.0)
            cz = rng.uniform(-75.0, 75.0)
            cloud = Entity(parent=self.root, position=(cx, cy, cz))
            for lobe in range(3):
                Entity(
                    parent=cloud,
                    model="sphere",
                    position=(lobe * 4.2 - 4.2, rng.uniform(-0.6, 0.8), rng.uniform(-1.5, 1.5)),
                    scale=(rng.uniform(7.5, 12.0), rng.uniform(2.4, 3.8), rng.uniform(6.0, 9.5)),
                    color=rgba32(248, 250, 255, 210),
                    unlit=True,
                )
            self.clouds.append(cloud)

        # Дальние пустынные горы и силуэты минаретов за пределами стен арены
        mountain_col = rgb32(164, 142, 114)
        for idx in range(12):
            ang = idx * (2.0 * math.pi / 12.0)
            dist = rng.uniform(64.0, 86.0)
            mx = math.cos(ang) * dist
            mz = math.sin(ang) * dist
            mh = rng.uniform(14.0, 28.0)
            mw = rng.uniform(18.0, 32.0)
            mtn = Entity(
                parent=self.root,
                model="cube",
                position=(mx, mh * 0.35, mz),
                scale=(mw, mh, mw),
                rotation_y=rng.uniform(0, 45),
                rotation_z=rng.uniform(-12, 12),
                color=mountain_col,
            )
            self.entities.append(mtn)

        # Атмосферные пылинки в солнечных лучах
        for _ in range(18):
            base_p = Vec3(rng.uniform(-24.0, 24.0), rng.uniform(1.0, 4.5), rng.uniform(-24.0, 24.0))
            mote = Entity(
                parent=self.root,
                model="sphere",
                position=base_p,
                scale=0.045,
                color=rgba32(255, 238, 195, 150),
                unlit=True,
            )
            self.dust_motes.append((mote, base_p, rng.uniform(0.0, 6.28)))

    def _spawn_destructible_props(self) -> None:
        """Создаёт взрывающиеся бочки с горючим и разрушаемые/простреливаемые ящики."""
        for p in self.destructibles:
            destroy(p.entity)
        self.destructibles.clear()

        for b_pos in self._barrel_spawns:
            holder = Entity(
                parent=self.root,
                position=b_pos + Vec3(0.0, 0.58, 0.0),
                scale=(0.72, 1.16, 0.72),
                collider="box",
            )
            b_np = load_safe_model("assets/models/barrel.glb")
            if b_np is not None:
                m_e = Entity(parent=holder, model=b_np, position=(0.0, -0.5, 0.0), scale=(1.35, 0.86, 1.35))
                apply_pbr_material(m_e, "metal")
            else:
                holder.model = "cube"
                holder.texture = self._barrel_tex
                holder.color = rgb32(205, 42, 36)
                apply_pbr_material(holder, "metal")

            prop = DestructibleProp(kind="barrel", entity=holder, pos=b_pos + Vec3(0, 0.58, 0), hp=45, max_hp=45)
            holder.destructible_ref = prop
            holder.surface_material = "metal"
            self.destructibles.append(prop)

        for c_pos in self._breakable_crate_spawns:
            crate = Entity(
                parent=self.root,
                model="cube",
                position=c_pos,
                scale=(1.22, 1.22, 1.22),
                texture=self._crate_tex,
                color=rgb32(215, 174, 108),
                collider="box",
            )
            apply_pbr_material(crate, "wood")
            prop = DestructibleProp(kind="wood_crate", entity=crate, pos=c_pos, hp=60, max_hp=60)
            crate.destructible_ref = prop
            crate.surface_material = "wood"
            crate.penetrable_wood = True
            self.destructibles.append(prop)

    def reset_destructibles(self) -> None:
        """Восстанавливает все взорванные бочки и разбитые ящики в начале нового раунда."""
        for prop in self.destructibles:
            prop.hp = prop.max_hp
            prop.alive = True
            prop.entity.enabled = True
            prop.entity.collider = "box"

    def get_nearest_bomb_site(self, world_pos: Vec3) -> str | None:
        """Возвращает 'A' или 'B', если игрок/бот находится в радиусе зоны закладки C4."""
        da = Vec3(world_pos.x - self.site_a_center.x, 0.0, world_pos.z - self.site_a_center.z).length()
        if da <= self.site_radius:
            return "A"
        db = Vec3(world_pos.x - self.site_b_center.x, 0.0, world_pos.z - self.site_b_center.z).length()
        if db <= self.site_radius:
            return "B"
        return None

    def update_environment(self, dt: float) -> None:
        """Плавное движение облаков, покачивание пальм на ветру и дрейф солнечных пылинок."""
        self._env_time += dt
        for idx, cloud in enumerate(self.clouds):
            cloud.x += dt * (0.65 + (idx % 3) * 0.22)
            if cloud.x > 88.0:
                cloud.x = -88.0

        sway = math.sin(self._env_time * 1.65) * 3.8
        for idx, frond in enumerate(self.palm_fronds):
            frond.rotation_x = 24.0 + sway * (0.7 if idx % 2 == 0 else -0.7)

        for mote, base_p, phase in self.dust_motes:
            t = self._env_time * 0.9 + phase
            mote.position = Vec3(
                base_p.x + math.sin(t) * 0.45,
                base_p.y + math.cos(t * 0.7) * 0.28,
                base_p.z + math.cos(t * 1.1) * 0.45,
            )
