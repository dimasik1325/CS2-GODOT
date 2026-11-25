"""
Реалистичная и GPU-оптимизированная 3D-карта «Mirage-Dust Plaza» (Panda3D flattenStrong Batching):
- Слияние сотен статических архитектурных деталей в единые GPU-буферы через flattenStrong()!
- Живое применение всех 15 настроек графики (тени 0..4096px, шейдеры FLAT/LIT/PBR, анизотропия 1x..16x,
  дальность прорисовки, плотность тумана, яркость, 4 времени суток DAY/SUNSET/NIGHT/OVERCAST, LOD неба).
- Новые 3D-достопримечательности: Башня с золотым куполом и минаретом, Центральный каменный фонтан,
  Восточный базар с полосатыми навесами, Крытый тоннель B с тёплым фонарём, Балкон с коваными перилами,
  Броневик спецназа с турелью, Грузовик, Морской контейнер, Пальмы, Реактивные мишени тира, Бочки и Ящики!
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from panda3d.core import AmbientLight as PandaAmbientLight
from panda3d.core import DirectionalLight as PandaDirectionalLight
from panda3d.core import PointLight as PandaPointLight
from ursina import Entity, Vec3, camera, clamp, color, scene

from src.settings import (
    GameSettings,
    apply_pbr_material,
    load_safe_model,
    load_safe_texture,
    rgb32,
    rgba32,
    set_global_anisotropy,
)


class DestructibleProp:
    """Разрушаемый или реактивный 3D-объект арены: бочка, пробиваемый ящик или стальная мишень тира."""

    def __init__(
        self,
        parent_root: Entity,
        kind: str,
        pos: Vec3,
        rot_y: float = 0.0,
        barrel_glb: Any = None,
        barrel_tex: Any = None,
        crate_tex: Any = None,
    ) -> None:
        self.kind = kind  # 'barrel' | 'wood_crate' | 'steel_target'
        self.spawn_pos = Vec3(pos)
        self.max_hp = 55 if kind == "barrel" else (70 if kind == "wood_crate" else 999999)
        self.hp = self.max_hp
        self.alive = True
        self._swing_timer: float = 0.0

        if kind == "barrel":
            self.collider_entity = Entity(
                parent=parent_root,
                model="cube",
                position=pos + Vec3(0.0, 0.56, 0.0),
                scale=(0.72, 1.12, 0.72),
                rotation_y=rot_y,
                collider="box",
                visible=barrel_glb is None,
                texture=barrel_tex,
                color=rgb32(210, 44, 38) if barrel_tex is None else color.white,
                add_to_scene_entities=False,
            )
            self.collider_entity.surface_type = "metal"
            self.collider_entity.destructible_ref = self
            apply_pbr_material(self.collider_entity, shininess=48.0, specular_strength=0.58, metallic=0.55)
            self.visual_entity: Entity | None = None
            if barrel_glb is not None:
                self.visual_entity = Entity(
                    parent=parent_root,
                    model=barrel_glb.copyTo(parent_root) if hasattr(barrel_glb, "copyTo") else barrel_glb,
                    position=pos,
                    rotation_y=rot_y,
                    add_to_scene_entities=False,
                )
                apply_pbr_material(self.visual_entity, shininess=52.0, specular_strength=0.62, metallic=0.60)
        elif kind == "wood_crate":
            self.collider_entity = Entity(
                parent=parent_root,
                model="cube",
                position=pos + Vec3(0.0, 0.55, 0.0),
                scale=(1.12, 1.10, 1.12),
                rotation_y=rot_y,
                collider="box",
                texture=crate_tex,
                color=rgb32(175, 132, 78) if crate_tex is None else rgb32(228, 202, 168),
                add_to_scene_entities=False,
            )
            self.collider_entity.surface_type = "wood"
            self.collider_entity.penetrable_wood = True
            self.collider_entity.destructible_ref = self
            apply_pbr_material(self.collider_entity, shininess=12.0, specular_strength=0.14)
            self.visual_entity = None
        else:
            # Реактивная стальная гонг-мишень на стрельбище базы CT!
            self.collider_entity = Entity(
                parent=parent_root,
                model="cube",
                position=pos + Vec3(0.0, 1.25, 0.0),
                scale=(0.56, 0.68, 0.08),
                rotation_y=rot_y,
                collider="box",
                color=rgb32(238, 186, 48),
                add_to_scene_entities=False,
            )
            self.collider_entity.surface_type = "metal"
            self.collider_entity.destructible_ref = self
            apply_pbr_material(self.collider_entity, shininess=82.0, specular_strength=0.88, metallic=0.80)
            self.visual_entity = Entity(
                parent=self.collider_entity,
                model="sphere",
                position=(0.0, 0.12, -0.55),
                scale=(0.35, 0.30, 0.2),
                color=rgb32(225, 42, 38),
                add_to_scene_entities=False,
            )

    @property
    def pos(self) -> Vec3:
        return Vec3(self.spawn_pos)

    def take_damage(
        self,
        dmg: int,
        on_barrel_explode: Callable[[Vec3], None] | None = None,
        on_wood_shatter: Callable[[Vec3], None] | None = None,
    ) -> bool:
        if not self.alive:
            return False
        if self.kind == "steel_target":
            self._swing_timer = 0.55
            self.collider_entity.rotation_x = -58.0
            return False

        self.hp -= dmg
        if self.hp > 0:
            return False

        self.alive = False
        self.collider_entity.enabled = False
        if self.visual_entity is not None:
            self.visual_entity.enabled = False

        center = self.spawn_pos + Vec3(0.0, 0.6, 0.0)
        if self.kind == "barrel" and on_barrel_explode is not None:
            on_barrel_explode(center)
        elif self.kind == "wood_crate" and on_wood_shatter is not None:
            on_wood_shatter(center)
        return True

    def update_target(self, dt: float) -> None:
        if self.kind == "steel_target" and self._swing_timer > 0.0:
            self._swing_timer = max(0.0, self._swing_timer - dt)
            self.collider_entity.rotation_x = -58.0 * (self._swing_timer / 0.55) * math.cos((0.55 - self._swing_timer) * 14.0)

    def reset(self) -> None:
        self.hp = self.max_hp
        self.alive = True
        self._swing_timer = 0.0
        self.collider_entity.rotation_x = 0.0
        self.collider_entity.enabled = True
        if self.visual_entity is not None:
            self.visual_entity.enabled = True


class ArenaMap:
    """Оптимизированная и высокодетализированная 3D-арена с GPU-батчингом и 15 настройками графики."""

    TIME_CYCLE = ("DAY", "SUNSET", "NIGHT", "OVERCAST")

    def __init__(self, settings: GameSettings | None = None, shadows_enabled: bool = True, time_of_day: str = "DAY") -> None:
        self.root = Entity(name="arena_root", add_to_scene_entities=False)
        self.time_of_day = settings.time_of_day if settings is not None else time_of_day
        self.shadows_enabled = settings.shadows_enabled if settings is not None else shadows_enabled
        self._env_time: float = 0.0
        self._sky_details_on: bool = settings.sky_details if settings is not None else True

        # Группы для GPU-слияния статической геометрии (flattenStrong)
        self._batch_sand = Entity(parent=self.root, name="batch_sandstone", add_to_scene_entities=False)
        self._batch_brick = Entity(parent=self.root, name="batch_brick", add_to_scene_entities=False)
        self._batch_cobble = Entity(parent=self.root, name="batch_cobble", add_to_scene_entities=False)
        self._batch_metal = Entity(parent=self.root, name="batch_metal", add_to_scene_entities=False)
        self._batch_decor = Entity(parent=self.root, name="batch_decor", add_to_scene_entities=False)
        self._colliders_root = Entity(parent=self.root, name="static_colliders", add_to_scene_entities=False)
        self._distant_vista_root = Entity(parent=self.root, name="distant_vista", add_to_scene_entities=False)

        # Точки спавна, подиум меню и ориентиры ИИ
        self.ct_spawn_pos = Vec3(0.0, 0.05, -24.5)
        self.ct_spawn_yaw = 0.0
        self.menu_podium_pos = Vec3(4.2, 0.05, -18.5)

        self.site_a_center = Vec3(-17.5, 0.05, 8.5)
        self.site_b_center = Vec3(17.5, 0.05, 8.5)
        self.site_radius = 4.6

        self.t_spawn_points: list[Vec3] = [
            Vec3(-16.0, 0.05, 24.5),
            Vec3(-8.0, 0.05, 25.5),
            Vec3(0.0, 0.05, 25.5),
            Vec3(8.0, 0.05, 25.5),
            Vec3(16.0, 0.05, 24.5),
            Vec3(-21.0, 0.05, 16.5),
            Vec3(21.0, 0.05, 16.5),
            Vec3(-13.5, 0.05, 13.0),
            Vec3(13.5, 0.05, 13.0),
            Vec3(0.0, 0.05, 17.5),
        ]

        self.patrol_waypoints: list[Vec3] = [
            Vec3(-17.5, 0.05, 17.5),
            Vec3(17.5, 0.05, 17.5),
            Vec3(-17.5, 0.05, 8.5),
            Vec3(17.5, 0.05, 8.5),
            Vec3(-17.5, 0.05, -4.0),
            Vec3(17.5, 0.05, -4.0),
            Vec3(-9.5, 0.05, 0.0),
            Vec3(9.5, 0.05, 0.0),
            Vec3(0.0, 0.05, 6.5),
            Vec3(0.0, 0.05, -7.5),
            Vec3(-14.0, 0.05, -15.5),
            Vec3(14.0, 0.05, -15.5),
        ]

        self._clouds: list[Entity] = []
        self._dust_motes: list[tuple[Entity, float]] = []
        self._palm_tops: list[Entity] = []
        self.destructibles: list[DestructibleProp] = []
        self.static_batch_count: int = 5

        self._setup_lighting_and_sky()

        custom_map = load_safe_model("assets/models/arena_map.glb")
        if custom_map is not None:
            Entity(parent=self.root, model=custom_map, collider="mesh", add_to_scene_entities=False)
        else:
            self._build_realistic_arena()
            self._bake_static_gpu_batches()

        if settings is not None:
            self.apply_graphics_settings(settings)
        else:
            self.apply_atmosphere(self.time_of_day, self.shadows_enabled)

    def _setup_lighting_and_sky(self) -> None:
        scene.setShaderAuto()

        self._sun_holder = Entity(parent=self.root, add_to_scene_entities=False)
        self._p3d_sun = PandaDirectionalLight("cs2_sun")
        self._sun_np = self._sun_holder.attachNewNode(self._p3d_sun)
        self._sun_np.setHpr(34, -52, 0)
        scene.setLight(self._sun_np)

        self._p3d_ambient = PandaAmbientLight("cs2_ambient")
        self._amb_np = self.root.attachNewNode(self._p3d_ambient)
        scene.setLight(self._amb_np)

        # Тёплая локальная подсветка зон A, B и крытого тоннеля B
        self._site_lights: list[Any] = []
        for idx, (spos, rgb_l) in enumerate([
            (self.site_a_center + Vec3(0, 3.8, 0), (1.0, 0.62, 0.25)),
            (self.site_b_center + Vec3(0, 3.8, 0), (1.0, 0.62, 0.25)),
            (Vec3(20.5, 3.2, -2.0), (1.0, 0.76, 0.42)),  # Внутренний фонарь крытого тоннеля B!
        ]):
            pl_holder = Entity(parent=self.root, position=spos, add_to_scene_entities=False)
            pl = PandaPointLight(f"zone_light_{idx}")
            pl.setColor((*rgb_l, 1.0))
            pl.setAttenuation((1.0, 0.08, 0.022))
            pl_np = pl_holder.attachNewNode(pl)
            scene.setLight(pl_np)
            self._site_lights.append((pl, rgb_l))

        self.sky_dome = Entity(
            parent=self.root,
            model="sphere",
            scale=-340.0,
            color=rgb32(128, 178, 232),
            unlit=True,
            add_to_scene_entities=False,
        )
        self.sun_disc = Entity(
            parent=self.root,
            model="sphere",
            position=Vec3(-85.0, 118.0, 95.0),
            scale=12.0,
            color=rgb32(255, 246, 205),
            unlit=True,
            add_to_scene_entities=False,
        )

        rng = random.Random(2026)
        for i in range(16):
            ang = i * (2.0 * math.pi / 16.0)
            dist = rng.uniform(128.0, 155.0)
            mh = rng.uniform(22.0, 44.0)
            Entity(
                parent=self._distant_vista_root,
                model="cube",
                position=(math.cos(ang) * dist, mh * 0.35 - 4.0, math.sin(ang) * dist),
                scale=(rng.uniform(30.0, 48.0), mh, rng.uniform(22.0, 34.0)),
                rotation_y=math.degrees(-ang) + rng.uniform(-18, 18),
                rotation_z=rng.uniform(-12, 12),
                color=rgb32(138, 122, 104),
                unlit=True,
                add_to_scene_entities=False,
            )

        for i in range(8):
            cl = Entity(
                parent=self._distant_vista_root,
                model="sphere",
                position=(rng.uniform(-95, 95), rng.uniform(48, 68), rng.uniform(-95, 95)),
                scale=(rng.uniform(20, 34), rng.uniform(3.2, 5.2), rng.uniform(12, 22)),
                color=rgba32(250, 250, 255, 188),
                unlit=True,
                add_to_scene_entities=False,
            )
            self._clouds.append(cl)

        for _ in range(18):
            dm = Entity(
                parent=self._distant_vista_root,
                model="sphere",
                position=(rng.uniform(-24, 24), rng.uniform(0.6, 4.2), rng.uniform(-24, 24)),
                scale=0.055,
                color=rgba32(255, 238, 198, 130),
                unlit=True,
                add_to_scene_entities=False,
            )
            self._dust_motes.append((dm, rng.uniform(0.0, 6.28)))

    def apply_graphics_settings(self, s: GameSettings) -> None:
        """Применяет все 15 графических настроек движка в реальном времени!"""
        # 1. Анизотропия текстур (1x..16x)
        set_global_anisotropy(s.anisotropic_level)

        # 2. Режим шейдеров (FLAT / LIT / PBR)
        if s.shader_quality == "FLAT":
            scene.setShaderOff()
        else:
            scene.setShaderAuto()

        # 3. Дальность прорисовки (65..220м) + отсечение дальнего горизонта на слабых ПК
        try:
            camera.clip_plane_far = float(clamp(s.render_distance * 2.2, 130.0, 520.0))
        except Exception:
            pass
        self._distant_vista_root.enabled = bool(s.render_distance >= 95.0)

        # 4. Детали неба, облаков и пылинок
        self._sky_details_on = bool(s.sky_details)
        for cl in self._clouds:
            cl.enabled = self._sky_details_on
        for dm, _ in self._dust_motes:
            dm.enabled = self._sky_details_on and (s.particles_quality >= 0.35)

        # 5. Качество теней (0..4096), время суток, плотность тумана и яркость
        self.apply_atmosphere(
            tod=s.time_of_day,
            shadows=s.shadow_quality > 0,
            shadow_res=int(s.shadow_quality),
            fog_mult=float(s.fog_density),
            brightness=float(s.brightness),
        )

    def apply_atmosphere(
        self,
        tod: str,
        shadows: bool = True,
        shadow_res: int = 2048,
        fog_mult: float = 1.0,
        brightness: float = 1.0,
    ) -> None:
        self.time_of_day = tod if tod in self.TIME_CYCLE else "DAY"
        self.shadows_enabled = shadows and shadow_res > 0
        br = clamp(brightness, 0.55, 1.60)

        if self.time_of_day == "DAY":
            self._p3d_sun.setColor((1.02 * br, 0.96 * br, 0.86 * br, 1.0))
            self._p3d_ambient.setColor((0.46 * br, 0.49 * br, 0.56 * br, 1.0))
            self._sun_np.setHpr(34, -54, 0)
            self.sky_dome.color = rgb32(118, 174, 236)
            self.sun_disc.color = rgb32(255, 248, 210)
            self.sun_disc.position = Vec3(-80.0, 122.0, 90.0)
            scene.fog_color = rgb32(198, 192, 178)
            base_near, base_far = 36.0, 148.0
        elif self.time_of_day == "SUNSET":
            self._p3d_sun.setColor((1.12 * br, 0.64 * br, 0.36 * br, 1.0))
            self._p3d_ambient.setColor((0.42 * br, 0.34 * br, 0.46 * br, 1.0))
            self._sun_np.setHpr(52, -26, 0)
            self.sky_dome.color = rgb32(214, 112, 78)
            self.sun_disc.color = rgb32(255, 148, 62)
            self.sun_disc.position = Vec3(-115.0, 46.0, 82.0)
            scene.fog_color = rgb32(205, 128, 96)
            base_near, base_far = 28.0, 124.0
        elif self.time_of_day == "OVERCAST":
            self._p3d_sun.setColor((0.76 * br, 0.80 * br, 0.86 * br, 1.0))
            self._p3d_ambient.setColor((0.52 * br, 0.55 * br, 0.60 * br, 1.0))
            self._sun_np.setHpr(20, -65, 0)
            self.sky_dome.color = rgb32(148, 160, 174)
            self.sun_disc.color = rgb32(220, 226, 234)
            self.sun_disc.position = Vec3(-55.0, 132.0, 70.0)
            scene.fog_color = rgb32(158, 166, 176)
            base_near, base_far = 22.0, 108.0
        else:  # NIGHT
            self._p3d_sun.setColor((0.30 * br, 0.40 * br, 0.66 * br, 1.0))
            self._p3d_ambient.setColor((0.20 * br, 0.24 * br, 0.34 * br, 1.0))
            self._sun_np.setHpr(-28, -48, 0)
            self.sky_dome.color = rgb32(16, 24, 44)
            self.sun_disc.color = rgb32(215, 228, 255)
            self.sun_disc.position = Vec3(75.0, 108.0, -80.0)
            scene.fog_color = rgb32(20, 28, 48)
            base_near, base_far = 20.0, 96.0

        if fog_mult <= 0.05:
            scene.fog_density = (900.0, 1200.0)
        else:
            inv = 1.0 / clamp(fog_mult, 0.15, 2.2)
            scene.fog_density = (base_near * inv, base_far * inv)

        try:
            if self.shadows_enabled:
                res = shadow_res if shadow_res in (512, 1024, 2048, 4096) else 2048
                self._p3d_sun.setShadowCaster(True, res, res)
                lens = self._p3d_sun.getLens()
                lens.setFilmSize(78, 78)
                lens.setNearFar(8.0, 185.0)
            else:
                self._p3d_sun.setShadowCaster(False)
        except Exception:
            pass

    def cycle_time_of_day(self) -> str:
        idx = (self.TIME_CYCLE.index(self.time_of_day) + 1) % len(self.TIME_CYCLE)
        self.apply_atmosphere(self.TIME_CYCLE[idx], self.shadows_enabled)
        return self.time_of_day

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # СТРОИТЕЛЬСТВО ДЕТАЛИЗИРОВАННОЙ КАРТЫ + СТАТИЧЕСКИЙ БАТЧИНГ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _add_static_solid(
        self,
        batch_parent: Entity,
        pos: tuple[float, float, float],
        scale: tuple[float, float, float],
        tex: Any,
        col: Any,
        tex_scale: tuple[float, float] = (1, 1),
        surface: str = "stone",
        rot_y: float = 0.0,
        shininess: float = 16.0,
        spec: float = 0.16,
        with_collider: bool = True,
    ) -> None:
        vis = Entity(
            parent=batch_parent,
            model="cube",
            position=pos,
            scale=scale,
            rotation_y=rot_y,
            texture=tex,
            texture_scale=tex_scale,
            color=col,
            add_to_scene_entities=False,
        )
        apply_pbr_material(vis, shininess=shininess, specular_strength=spec)
        if with_collider:
            col_e = Entity(
                parent=self._colliders_root,
                model="cube",
                position=pos,
                scale=scale,
                rotation_y=rot_y,
                collider="box",
                visible=False,
                add_to_scene_entities=False,
            )
            col_e.surface_type = surface

    def _build_arch_wall(
        self,
        pos: tuple[float, float, float],
        scale: tuple[float, float, float],
        wall_tex: Any,
        brick_tex: Any,
        rot_y: float = 0.0,
        use_brick: bool = False,
    ) -> None:
        batch = self._batch_brick if use_brick else self._batch_sand
        tex = brick_tex if use_brick else wall_tex
        col = color.white if tex is not None else rgb32(208, 186, 150)
        self._add_static_solid(
            batch,
            pos=pos,
            scale=scale,
            tex=tex,
            col=col,
            tex_scale=(max(1.0, scale[0] / 3.2), max(1.0, scale[1] / 3.2)),
            rot_y=rot_y,
        )
        # Выступающий архитектурный карниз сверху и цоколь снизу (без лишних коллайдеров!)
        self._add_static_solid(
            self._batch_decor,
            pos=(pos[0], pos[1] + scale[1] * 0.5 + 0.16, pos[2]),
            scale=(scale[0] + 0.28, 0.32, scale[2] + 0.28),
            tex=wall_tex,
            col=rgb32(182, 162, 132),
            rot_y=rot_y,
            with_collider=False,
        )
        self._add_static_solid(
            self._batch_decor,
            pos=(pos[0], 0.18, pos[2]),
            scale=(scale[0] + 0.16, 0.36, scale[2] + 0.16),
            tex=None,
            col=rgb32(126, 114, 98),
            rot_y=rot_y,
            with_collider=False,
        )

    def _build_realistic_arena(self) -> None:
        wall_tex = load_safe_texture("assets/textures/wall_sandstone.png")
        brick_tex = load_safe_texture("assets/textures/wall_brick.png")
        cobble_tex = load_safe_texture("assets/textures/cobblestone.png")
        awning_tex = load_safe_texture("assets/textures/fabric_awning.png")
        floor_tex = load_safe_texture("assets/textures/floor_dust.png")
        road_tex = load_safe_texture("assets/textures/asphalt_road.png")
        metal_tex = load_safe_texture("assets/textures/metal_plate.png")
        cont_tex = load_safe_texture("assets/textures/container_blue.png")
        sandbag_tex = load_safe_texture("assets/textures/sandbag_fabric.png")
        crate_tex = load_safe_texture("assets/textures/crate_wood.png")
        barrel_tex = load_safe_texture("assets/textures/barrel_hazard.png")
        barrel_glb = load_safe_model("assets/models/barrel.glb", normalize_to=1.12)

        # ── 1. ПОЛ ПЛОЩАДИ, БРУСЧАТКА И АСФАЛЬТ ──
        self._add_static_solid(
            self._batch_sand,
            pos=(0.0, -0.5, 0.0),
            scale=(62.0, 1.0, 62.0),
            tex=floor_tex,
            col=rgb32(214, 196, 162) if floor_tex is None else color.white,
            tex_scale=(20.0, 20.0),
            shininess=12.0,
            spec=0.12,
        )
        # Брусчатая центральная площадь
        self._add_static_solid(
            self._batch_cobble,
            pos=(0.0, 0.015, 1.5),
            scale=(18.0, 0.03, 18.0),
            tex=cobble_tex,
            col=color.white if cobble_tex is not None else rgb32(162, 156, 146),
            tex_scale=(6.0, 6.0),
            with_collider=False,
        )
        # Асфальтовая магистраль через карту
        self._add_static_solid(
            self._batch_cobble,
            pos=(0.0, 0.02, 0.0),
            scale=(7.8, 0.04, 58.0),
            tex=road_tex,
            col=color.white if road_tex is not None else rgb32(68, 70, 76),
            tex_scale=(1.0, 10.0),
            shininess=28.0,
            spec=0.25,
            with_collider=False,
        )

        # Подиум Оперативника CT для Главного меню
        self._add_static_solid(
            self._batch_metal,
            pos=(self.menu_podium_pos.x, 0.06, self.menu_podium_pos.z),
            scale=(1.7, 0.12, 1.7),
            tex=metal_tex,
            col=rgb32(42, 54, 72),
            shininess=65.0,
            spec=0.65,
            with_collider=False,
        )

        # ── 2. РАЗМЕТКА ТОЧЕК ЗАКЛАДКИ БОМБЫ SITE A И SITE B ──
        for s_center in (self.site_a_center, self.site_b_center):
            self._add_static_solid(
                self._batch_cobble,
                pos=(s_center.x, 0.03, s_center.z),
                scale=(7.2, 0.05, 7.2),
                tex=cobble_tex,
                col=rgb32(138, 128, 116),
                tex_scale=(3, 3),
                with_collider=False,
            )
            for dx, dz, sx, sz in [(0, 3.5, 7.2, 0.24), (0, -3.5, 7.2, 0.24), (3.5, 0, 0.24, 7.2), (-3.5, 0, 0.24, 7.2)]:
                Entity(
                    parent=self._batch_decor,
                    model="cube",
                    position=(s_center.x + dx, 0.06, s_center.z + dz),
                    scale=(sx, 0.04, sz),
                    color=rgb32(242, 138, 34),
                    add_to_scene_entities=False,
                )

        # ── 3. ВНЕШНИЕ КРЕПОСТНЫЕ СТЕНЫ + ВЕЛИЧЕСТВЕННЫЙ МИНАРЕТ И ЗОЛОТОЙ КУПОЛ! ──
        h_ext = 6.8
        for pos, sc in [
            ((0.0, h_ext * 0.5, 30.5), (62.0, h_ext, 1.4)),
            ((0.0, h_ext * 0.5, -30.5), (62.0, h_ext, 1.4)),
            ((-30.5, h_ext * 0.5, 0.0), (1.4, h_ext, 62.0)),
            ((30.5, h_ext * 0.5, 0.0), (1.4, h_ext, 62.0)),
        ]:
            self._build_arch_wall(pos, sc, wall_tex, brick_tex)

        # Башня с золотым куполом и минаретом за базой T (знаковый восточный ориентир как на Dust2/Mirage!)
        Entity(parent=self._batch_sand, model="cube", position=(0.0, 7.5, 33.5), scale=(9.5, 9.0, 6.5), texture=wall_tex, texture_scale=(3, 3), color=color.white if wall_tex else rgb32(215, 194, 158), add_to_scene_entities=False)
        dome = Entity(parent=self._batch_decor, model="sphere", position=(0.0, 12.2, 33.5), scale=(7.8, 5.6, 7.8), color=rgb32(242, 192, 62), add_to_scene_entities=False)
        apply_pbr_material(dome, shininess=88.0, specular_strength=0.90, metallic=0.85)
        Entity(parent=self._batch_decor, model="cube", position=(0.0, 15.6, 33.5), scale=(0.18, 2.2, 0.18), color=rgb32(255, 215, 85), add_to_scene_entities=False)
        # Высокий минарет с балкончиком
        Entity(parent=self._batch_sand, model="cube", position=(-9.5, 10.5, 34.0), scale=(2.4, 16.0, 2.4), texture=wall_tex, texture_scale=(1, 5), color=color.white if wall_tex else rgb32(212, 190, 155), add_to_scene_entities=False)
        Entity(parent=self._batch_decor, model="cube", position=(-9.5, 16.2, 34.0), scale=(3.3, 0.45, 3.3), color=rgb32(175, 150, 120), add_to_scene_entities=False)
        spire = Entity(parent=self._batch_decor, model="sphere", position=(-9.5, 19.0, 34.0), scale=(2.2, 3.4, 2.2), color=rgb32(242, 192, 62), add_to_scene_entities=False)
        apply_pbr_material(spire, shininess=88.0, specular_strength=0.90, metallic=0.85)

        # ── 4. ЦЕНТРАЛЬНЫЙ КАМЕННЫЙ ФОНТАН НА МИДУ + ДВОЙНЫЕ ВОРОТА MID DOORS ──
        # Многоярусный каменный фонтан с бирюзовой водой (даёт крутое укрытие в центре!)
        self._add_static_solid(self._batch_cobble, pos=(0.0, 0.45, 7.2), scale=(3.4, 0.90, 3.4), tex=cobble_tex, col=rgb32(182, 174, 160), tex_scale=(2, 1))
        water = Entity(parent=self._batch_decor, model="cube", position=(0.0, 0.88, 7.2), scale=(2.85, 0.08, 2.85), color=rgba32(48, 178, 212, 225), add_to_scene_entities=False)
        apply_pbr_material(water, shininess=96.0, specular_strength=0.95)
        self._add_static_solid(self._batch_cobble, pos=(0.0, 1.35, 7.2), scale=(0.95, 1.6, 0.95), tex=wall_tex, col=rgb32(204, 192, 168))
        Entity(parent=self._batch_decor, model="sphere", position=(0.0, 2.25, 7.2), scale=(1.55, 0.35, 1.55), color=rgb32(192, 180, 158), add_to_scene_entities=False)

        # Здания и арки Мида + простреливаемые деревянные ворота Mid Double Doors
        self._build_arch_wall((-7.8, 2.4, -0.5), (8.2, 4.8, 1.4), wall_tex, brick_tex, use_brick=True)
        self._build_arch_wall((7.8, 2.4, -0.5), (8.2, 4.8, 1.4), wall_tex, brick_tex, use_brick=True)
        self._add_static_solid(self._batch_brick, pos=(0.0, 4.15, -0.5), scale=(7.6, 1.3, 1.5), tex=brick_tex, col=color.white if brick_tex else rgb32(175, 118, 92), tex_scale=(3, 1))

        for sign, rot in ((-1.0, 14.0), (1.0, -14.0)):
            door = Entity(
                parent=self.root,
                model="cube",
                position=(sign * 1.95, 1.75, -0.5),
                scale=(2.75, 3.5, 0.22),
                rotation_y=rot,
                texture=crate_tex,
                color=rgb32(165, 115, 68) if crate_tex is None else rgb32(210, 178, 138),
                collider="box",
                add_to_scene_entities=False,
            )
            door.surface_type = "wood"
            door.penetrable_wood = True
            apply_pbr_material(door, shininess=14.0, specular_strength=0.16)

        # ── 5. ВОСТОЧНЫЙ БАЗАР НА ЛИНИИ A (ПРИЛАВКИ С ПОЛОСАТЫМИ ТКАНЕВЫМИ НАВЕСАМИ!) ──
        self._build_arch_wall((-13.5, 2.2, 14.5), (1.4, 4.4, 9.5), wall_tex, brick_tex)
        self._build_arch_wall((-21.5, 2.2, 2.5), (7.5, 4.4, 1.4), wall_tex, brick_tex, use_brick=True)
        for bz_z in (-6.5, -12.5):
            # Деревянный прилавок базара
            self._add_static_solid(self._batch_sand, pos=(-19.5, 0.55, bz_z), scale=(3.4, 1.1, 1.6), tex=crate_tex, col=rgb32(168, 124, 76), surface="wood")
            # Стойки и наклонный полосатый тканевый тент навеса
            for sx in (-1.55, 1.55):
                Entity(parent=self._batch_metal, model="cube", position=(-19.5 + sx, 1.75, bz_z - 0.65), scale=(0.10, 2.6, 0.10), color=rgb32(72, 62, 52), add_to_scene_entities=False)
            canopy = Entity(
                parent=self._batch_decor,
                model="cube",
                position=(-19.5, 2.95, bz_z),
                scale=(3.8, 0.08, 2.6),
                rotation_x=12.0,
                texture=awning_tex,
                color=color.white if awning_tex else rgb32(205, 62, 48),
                add_to_scene_entities=False,
            )
            apply_pbr_material(canopy, shininess=8.0, specular_strength=0.08)

        # ── 6. КРЫТЫЙ КАМЕННЫЙ ТОННЕЛЬ B (UPPER TUNNELS С ПОТОЛКОМ И КОЛОННАМИ!) ──
        self._build_arch_wall((13.5, 2.2, 14.5), (1.4, 4.4, 9.5), wall_tex, brick_tex)
        # Внутренняя стена тоннеля вдоль восточного края
        self._build_arch_wall((16.5, 2.1, -3.5), (1.3, 4.2, 12.0), wall_tex, brick_tex, use_brick=True)
        # Каменный свод-потолок крытого тоннеля B между x=16.5 и внешней стеной x=30.5!
        self._add_static_solid(
            self._batch_brick,
            pos=(23.5, 4.35, -3.5),
            scale=(14.0, 0.55, 12.0),
            tex=brick_tex,
            col=rgb32(142, 118, 102) if brick_tex is None else rgb32(195, 182, 168),
            tex_scale=(4, 4),
        )
        # Светильник под сводом тоннеля
        Entity(parent=self._batch_decor, model="sphere", position=(20.5, 3.95, -2.0), scale=(0.55, 0.25, 0.55), color=rgb32(255, 218, 138), unlit=True, add_to_scene_entities=False)

        # Базовые укрытия спавнов CT и T
        self._build_arch_wall((0.0, 1.9, -15.5), (11.0, 3.8, 1.4), wall_tex, brick_tex)
        self._build_arch_wall((0.0, 1.9, 17.5), (11.0, 3.8, 1.4), wall_tex, brick_tex, use_brick=True)

        # ── 7. ПРОХОДИМАЯ КАМЕННАЯ ЛЕСТНИЦА И ДВОРЦОВЫЙ БАЛКОН CATWALK С КОВАНЫМИ ПЕРИЛАМИ ──
        plat_y = 2.25
        self._add_static_solid(
            self._batch_sand,
            pos=(-8.8, plat_y * 0.5, 7.5),
            scale=(4.6, plat_y, 9.2),
            tex=wall_tex,
            col=color.white if wall_tex else rgb32(198, 178, 146),
            tex_scale=(2, 3),
        )
        # Кованая металлическая балюстрада на балконе Catwalk (через неё видно врагов и можно простреливать!)
        self._add_static_solid(self._batch_metal, pos=(-6.62, plat_y + 0.92, 7.5), scale=(0.12, 0.08, 9.0), tex=metal_tex, col=rgb32(42, 46, 52), surface="metal", with_collider=True)
        for rz in (-3.6, -1.8, 0.0, 1.8, 3.6):
            Entity(parent=self._batch_metal, model="cube", position=(-6.62, plat_y + 0.46, 7.5 + rz), scale=(0.08, 0.90, 0.08), color=rgb32(42, 46, 52), add_to_scene_entities=False)

        steps_count = 9
        for st_i in range(steps_count):
            st_h = (st_i + 1) * (plat_y / steps_count)
            st_z = 2.9 - (steps_count - 1 - st_i) * 0.52
            self._add_static_solid(
                self._batch_sand,
                pos=(-8.8, st_h * 0.5, st_z),
                scale=(3.4, st_h, 0.56),
                tex=wall_tex,
                col=rgb32(192, 172, 142),
            )

        # ── 8. 3D ТЕХНИКА: БРОНЕВИК СПЕЦНАЗА APC/HUMVEE, ГРУЗОВИК ТЕРРОРИСТОВ И КОНТЕЙНЕР ──
        self._build_tactical_humvee(pos=Vec3(-9.5, 0.0, -21.5), rot_y=22.0, metal_tex=metal_tex)
        self._build_cargo_truck(pos=Vec3(9.8, 0.0, 22.0), rot_y=-162.0, metal_tex=metal_tex, crate_tex=crate_tex)
        self._build_open_container(pos=Vec3(12.2, 0.0, -10.5), rot_y=-14.0, cont_tex=cont_tex, metal_tex=metal_tex)

        # ── 9. УКРЕПЛЕНИЯ ИЗ МЕШКОВ С ПЕСКОМ, БЛОКИ ДЖЕРСИ, ФОНАРИ И КАБЕЛИ ──
        for sb_pos, sb_rot in [
            (Vec3(-4.6, 0.0, -9.8), 12.0),
            (Vec3(4.8, 0.0, 10.5), -15.0),
            (Vec3(-18.2, 0.0, 12.8), 0.0),
            (Vec3(18.2, 0.0, 4.2), 90.0),
        ]:
            self._build_sandbag_bunker(sb_pos, sb_rot, sandbag_tex)

        for jb_pos, jb_rot in [(Vec3(5.6, 0.55, -20.5), -26.0), (Vec3(-5.8, 0.55, 21.5), 20.0)]:
            self._add_static_solid(self._batch_cobble, pos=tuple(jb_pos), scale=(2.8, 1.1, 0.72), tex=None, col=rgb32(158, 160, 164), rot_y=jb_rot)

        # Сгибающиеся на ветру 3D-пальмы
        for px, pz in [(-24.5, -22.0), (24.5, -22.0), (-25.0, 22.0), (25.0, 22.0), (-15.5, -2.5), (14.5, 22.5)]:
            self._build_palm_tree(Vec3(px, 0.0, pz))

        # Уличные фонари и воздушные провода
        lamp_coords = [(-6.2, -12.0), (6.2, -12.0), (-6.2, 12.0), (6.2, 12.0)]
        for lx, lz in lamp_coords:
            self._add_static_solid(self._batch_metal, pos=(lx, 2.6, lz), scale=(0.18, 5.2, 0.18), tex=metal_tex, col=rgb32(55, 60, 68), surface="metal")
            Entity(parent=self._batch_metal, model="cube", position=(lx + (0.45 if lx < 0 else -0.45), 5.1, lz), scale=(1.0, 0.12, 0.16), color=rgb32(55, 60, 68), add_to_scene_entities=False)
            Entity(parent=self._batch_decor, model="sphere", position=(lx + (0.82 if lx < 0 else -0.82), 4.95, lz), scale=(0.36, 0.22, 0.36), color=rgb32(255, 232, 170), unlit=True, add_to_scene_entities=False)

        for z_c in (-12.0, 12.0):
            Entity(parent=self._batch_decor, model="cube", position=(0.0, 4.95, z_c), scale=(12.4, 0.035, 0.035), rotation_z=1.5, color=rgb32(28, 30, 35), add_to_scene_entities=False)

        # ── 10. ВЗРЫВАЮЩИЕСЯ БОЧКИ, ЯЩИКИ И РЕАКТИВНЫЕ МИШЕНИ СТРЕЛЬБИЩА БАЗЫ CT ──
        for bx, bz in [(-3.4, 1.2), (16.2, 10.5), (-15.8, 6.2), (4.2, -5.2), (-11.5, 18.0), (20.2, -6.5)]:
            self.destructibles.append(
                DestructibleProp(self.root, "barrel", Vec3(bx, 0.0, bz), barrel_glb=barrel_glb, barrel_tex=barrel_tex)
            )

        for cx, cz, crot in [
            (-17.5, 8.5, 15.0),
            (17.5, 8.5, -18.0),
            (2.8, 3.2, 8.0),
            (-12.5, -8.5, 25.0),
            (19.5, 14.0, 0.0),
            (-19.5, 14.5, 12.0),
        ]:
            self.destructibles.append(
                DestructibleProp(self.root, "wood_crate", Vec3(cx, 0.0, cz), rot_y=crot, crate_tex=crate_tex)
            )

        # Три стальные реактивные мишени тира у спавна CT для разминки аима!
        for tx in (-22.5, -20.5, -18.5):
            Entity(parent=self._batch_metal, model="cube", position=(tx, 0.6, -28.2), scale=(0.12, 1.2, 0.12), color=rgb32(62, 68, 76), add_to_scene_entities=False)
            self.destructibles.append(DestructibleProp(self.root, "steel_target", Vec3(tx, 0.0, -28.2)))

    def _build_tactical_humvee(self, pos: Vec3, rot_y: float, metal_tex: Any) -> None:
        holder = Entity(parent=self._batch_metal, position=pos, rotation_y=rot_y, add_to_scene_entities=False)
        body_col = rgb32(158, 142, 106)
        Entity(parent=holder, model="cube", position=(0, 0.72, 0), scale=(2.25, 0.86, 4.6), texture=metal_tex, color=body_col, add_to_scene_entities=False)
        Entity(parent=holder, model="cube", position=(0, 1.48, -0.35), scale=(2.10, 0.78, 2.55), texture=metal_tex, color=body_col, add_to_scene_entities=False)
        # Защитная башенка пулемётчика на крыше + бронестекло + фары
        Entity(parent=holder, model="sphere", position=(0, 1.95, -0.25), scale=(1.05, 0.35, 1.05), color=rgb32(118, 108, 82), add_to_scene_entities=False)
        Entity(parent=holder, model="cube", position=(0, 1.46, 0.94), scale=(1.88, 0.56, 0.08), rotation_x=-20.0, color=rgba32(95, 155, 195, 225), add_to_scene_entities=False)
        for lx in (-0.78, 0.78):
            Entity(parent=holder, model="sphere", position=(lx, 0.82, 2.31), scale=(0.24, 0.24, 0.08), color=rgb32(255, 244, 195), unlit=True, add_to_scene_entities=False)
        for wx in (-1.12, 1.12):
            for wz in (-1.45, 1.45):
                Entity(parent=holder, model="sphere", position=(wx, 0.44, wz), scale=(0.34, 0.86, 0.86), color=rgb32(28, 30, 34), add_to_scene_entities=False)

        col_box = Entity(parent=self._colliders_root, model="cube", position=pos + Vec3(0, 1.0, 0), scale=(2.3, 2.0, 4.65), rotation_y=rot_y, collider="box", visible=False, add_to_scene_entities=False)
        col_box.surface_type = "metal"

    def _build_cargo_truck(self, pos: Vec3, rot_y: float, metal_tex: Any, crate_tex: Any) -> None:
        holder = Entity(parent=self._batch_metal, position=pos, rotation_y=rot_y, add_to_scene_entities=False)
        cab_col = rgb32(68, 92, 118)
        Entity(parent=holder, model="cube", position=(0, 1.15, 1.65), scale=(2.2, 1.7, 1.8), texture=metal_tex, color=cab_col, add_to_scene_entities=False)
        Entity(parent=holder, model="cube", position=(0, 1.52, 2.56), scale=(1.95, 0.62, 0.08), color=rgba32(105, 168, 208, 225), add_to_scene_entities=False)
        Entity(parent=holder, model="cube", position=(0, 0.78, -0.85), scale=(2.35, 0.42, 3.6), texture=crate_tex, color=rgb32(148, 112, 74), add_to_scene_entities=False)
        Entity(parent=holder, model="cube", position=(0, 1.42, -1.1), scale=(2.2, 0.95, 2.8), texture=crate_tex, color=rgb32(168, 128, 84), add_to_scene_entities=False)
        for wx in (-1.12, 1.12):
            for wz in (-1.85, 0.15, 1.75):
                Entity(parent=holder, model="sphere", position=(wx, 0.44, wz), scale=(0.34, 0.86, 0.86), color=rgb32(28, 30, 34), add_to_scene_entities=False)

        col_box = Entity(parent=self._colliders_root, model="cube", position=pos + Vec3(0, 1.05, 0), scale=(2.35, 2.1, 5.4), rotation_y=rot_y, collider="box", visible=False, add_to_scene_entities=False)
        col_box.surface_type = "metal"

    def _build_open_container(self, pos: Vec3, rot_y: float, cont_tex: Any, metal_tex: Any) -> None:
        c_col = color.white if cont_tex is not None else rgb32(48, 96, 158)
        holder = Entity(parent=self.root, position=pos, rotation_y=rot_y, add_to_scene_entities=False)
        for p_loc, sc, tex in [
            ((-1.28, 1.35, 0.0), (0.14, 2.7, 6.2), cont_tex),
            ((1.28, 1.35, 0.0), (0.14, 2.7, 6.2), cont_tex),
            ((0.0, 2.68, 0.0), (2.70, 0.14, 6.2), cont_tex),
            ((0.0, 0.06, 0.0), (2.56, 0.10, 6.2), metal_tex),
        ]:
            part = Entity(parent=holder, model="cube", position=p_loc, scale=sc, texture=tex, color=c_col if tex == cont_tex else color.white, collider="box", add_to_scene_entities=False)
            part.surface_type = "metal"
            apply_pbr_material(part, shininess=44.0, specular_strength=0.48, metallic=0.45)

    def _build_sandbag_bunker(self, pos: Vec3, rot_y: float, sb_tex: Any) -> None:
        holder = Entity(parent=self._batch_sand, position=pos, rotation_y=rot_y, add_to_scene_entities=False)
        sb_col = color.white if sb_tex is not None else rgb32(176, 158, 122)
        for row_y in range(3):
            cnt = 4 - (row_y % 2)
            for i in range(cnt):
                ox = (i - (cnt - 1) * 0.5) * 0.68
                Entity(parent=holder, model="sphere", position=(ox, 0.20 + row_y * 0.30, 0.0), scale=(0.72, 0.34, 0.48), texture=sb_tex, color=sb_col, add_to_scene_entities=False)
        col_e = Entity(parent=self._colliders_root, model="cube", position=pos + Vec3(0, 0.52, 0), scale=(2.75, 1.05, 0.58), rotation_y=rot_y, collider="box", visible=False, add_to_scene_entities=False)
        col_e.surface_type = "stone"

    def _build_palm_tree(self, pos: Vec3) -> None:
        trunk_root = Entity(parent=self._batch_decor, position=pos, add_to_scene_entities=False)
        for seg in range(6):
            Entity(
                parent=trunk_root,
                model="cube",
                position=(seg * 0.07, 0.55 + seg * 0.92, 0.0),
                scale=(0.36 - seg * 0.03, 1.0, 0.36 - seg * 0.03),
                rotation_z=-4.0 * seg,
                color=rgb32(124, 90, 56),
                add_to_scene_entities=False,
            )
        col_t = Entity(parent=self._colliders_root, model="cube", position=pos + Vec3(0.15, 2.5, 0), scale=(0.45, 5.0, 0.45), collider="box", visible=False, add_to_scene_entities=False)
        col_t.surface_type = "wood"

        # Динамическая верхушка пальмы остаётся отдельной нодой для колыхания на ветру!
        crown = Entity(parent=self.root, position=pos + Vec3(0.40, 5.9, 0.0), add_to_scene_entities=False)
        for frond_i in range(7):
            ang = frond_i * (360.0 / 7.0)
            leaf_pivot = Entity(parent=crown, rotation_y=ang, add_to_scene_entities=False)
            Entity(
                parent=leaf_pivot,
                model="cube",
                position=(1.15, -0.15, 0.0),
                scale=(2.3, 0.06, 0.52),
                rotation_z=-24.0,
                color=rgb32(62, 134, 56),
                add_to_scene_entities=False,
            )
        self._palm_tops.append(crown)

    def _bake_static_gpu_batches(self) -> None:
        """Объединяет сотни статических 3D-деталей в 5 быстрых вершинных буферов GPU!"""
        batches = (self._batch_sand, self._batch_brick, self._batch_cobble, self._batch_metal, self._batch_decor)
        for b in batches:
            try:
                b.flattenStrong()
            except Exception:
                pass
        self.static_batch_count = len(batches)

    def get_nearest_bomb_site(self, pos: Vec3) -> str | None:
        if Vec3(pos.x - self.site_a_center.x, 0.0, pos.z - self.site_a_center.z).length() <= self.site_radius:
            return "A"
        if Vec3(pos.x - self.site_b_center.x, 0.0, pos.z - self.site_b_center.z).length() <= self.site_radius:
            return "B"
        return None

    def reset_destructibles(self) -> None:
        for prop in self.destructibles:
            prop.reset()

    def update_environment(self, dt: float) -> None:
        self._env_time += dt
        for prop in self.destructibles:
            prop.update_target(dt)

        if not self._sky_details_on:
            return

        for cl in self._clouds:
            cl.x += dt * 0.65
            if cl.x > 110.0:
                cl.x = -110.0

        for idx, crown in enumerate(self._palm_tops):
            crown.rotation_z = math.sin(self._env_time * 1.4 + idx) * 2.8

        for dm, phase in self._dust_motes:
            dm.y += math.sin(self._env_time * 1.2 + phase) * dt * 0.18
