"""
Генератор и загрузчик тактической арены в стиле de_dust2 (Counter-Strike 2).
Логика загрузки:
  1) Если в assets/models/arena_map.glb лежит готовая 3D-карта (.glb/.gltf) —
     загружает её целиком с точным коллайдером collider='mesh'.
  2) Иначе процедурно собирает проработанную арену Sandstone Dust2 Yard (56x56 м)
     с текстурами песчаника, мидом с двойными проходами, точками A и B,
     колоннами и деревянными тактическими ящиками (assets/models/crate.glb + fallback).
"""

from __future__ import annotations

from ursina import AmbientLight, DirectionalLight, Entity, Sky, Vec2, Vec3, color

from src.settings import load_safe_model, load_safe_texture


class ArenaMap:
    """Управляет геометрий арены, освещением, точками спавна CT/T и маршрутами ботов."""

    ARENA_SIZE: float = 56.0
    WALL_HEIGHT: float = 6.5

    def __init__(self) -> None:
        self.root = Entity(name="arena_map_root")
        self.entities: list[Entity] = []

        # Освещение в тёплой палитре CS2 Dust2
        self.sun_light = DirectionalLight(parent=self.root, y=22, z=-15, shadows=False)
        self.sun_light.look_at(Vec3(8, -1, 10))
        self.sun_light.color = color.rgb(255, 246, 228)

        self.ambient_light = AmbientLight(
            parent=self.root,
            color=color.rgba(168, 176, 192, 255),
        )
        self.sky = Sky(color=color.rgb(168, 206, 242))

        # Точки спавна игрока (CT — юг) и ботов (T — север и фланги A/B)
        self.ct_spawn_pos: Vec3 = Vec3(0.0, 0.2, -23.0)
        self.ct_spawn_yaw: float = 0.0

        self.t_spawn_points: list[Vec3] = [
            Vec3(0.0, 0.2, 23.0),
            Vec3(-8.5, 0.2, 22.0),
            Vec3(8.5, 0.2, 22.0),
            Vec3(-19.5, 0.2, 16.0),
            Vec3(19.5, 0.2, 16.0),
            Vec3(-18.0, 0.2, 4.0),
            Vec3(18.0, 0.2, 4.0),
            Vec3(4.5, 0.2, 13.5),
        ]

        self.patrol_waypoints: list[Vec3] = [
            Vec3(0.0, 0.2, 15.0),
            Vec3(-11.0, 0.2, 12.0),
            Vec3(11.0, 0.2, 12.0),
            Vec3(-20.0, 0.2, 3.0),
            Vec3(-20.0, 0.2, -9.0),
            Vec3(-9.0, 0.2, -4.0),
            Vec3(0.0, 0.2, 2.5),
            Vec3(0.0, 0.2, -7.5),
            Vec3(10.0, 0.2, -3.5),
            Vec3(20.0, 0.2, 4.5),
            Vec3(20.0, 0.2, -9.5),
            Vec3(-11.5, 0.2, -14.5),
            Vec3(11.5, 0.2, -14.5),
        ]

        self._wall_tex = load_safe_texture("assets/textures/wall_sandstone.png")
        self._floor_tex = load_safe_texture("assets/textures/floor_dust.png")
        self._crate_tex = load_safe_texture("assets/textures/crate_wood.png")

        if not self._try_load_custom_map_glb():
            self._build_sandstone_dust2_arena()

    def _try_load_custom_map_glb(self) -> bool:
        """Проверяет наличие пользовательской карты assets/models/arena_map.glb."""
        custom_map_np = load_safe_model("assets/models/arena_map.glb")
        if custom_map_np is None:
            return False

        try:
            map_ent = Entity(
                parent=self.root,
                model=custom_map_np,
                collider="mesh",
                position=(0.0, 0.0, 0.0),
            )
            self.entities.append(map_ent)
            # Страховочный пол под кастомной картой
            safety_floor = Entity(
                parent=self.root,
                model="cube",
                position=(0.0, -1.0, 0.0),
                scale=(120.0, 1.0, 120.0),
                collider="box",
                visible=False,
            )
            self.entities.append(safety_floor)
            print("[Map] Загружена пользовательская 3D-карта assets/models/arena_map.glb")
            return True
        except Exception as exc:
            print(f"[Map] Ошибка инициализации arena_map.glb ({exc}), строим встроенную арену.")
            return False

    def _add_wall(
        self,
        pos: tuple[float, float, float],
        scale: tuple[float, float, float],
        tint: Any = None,
    ) -> Entity:
        wall = Entity(
            parent=self.root,
            model="cube",
            position=pos,
            scale=scale,
            texture=self._wall_tex,
            texture_scale=Vec2(max(1.0, scale[0] / 3.5), max(1.0, scale[1] / 3.5)),
            color=tint if tint is not None else color.rgb(232, 212, 176),
            collider="box",
        )
        self.entities.append(wall)
        return wall

    def _add_crate(
        self,
        pos: tuple[float, float, float],
        size: float = 1.45,
        rot_y: float = 0.0,
    ) -> Entity:
        """Создаёт тактический ящик из crate.glb (или куба с текстурой дерева) + box-коллайдер."""
        crate_np = load_safe_model("assets/models/crate.glb")
        if crate_np is not None:
            crate = Entity(
                parent=self.root,
                position=pos,
                scale=(size, size, size),
                rotation_y=rot_y,
                collider="box",
            )
            Entity(parent=crate, model=crate_np)
        else:
            crate = Entity(
                parent=self.root,
                model="cube",
                position=pos,
                scale=(size, size, size),
                rotation_y=rot_y,
                texture=self._crate_tex,
                color=color.rgb(196, 152, 96),
                collider="box",
            )
        self.entities.append(crate)
        return crate

    def _build_sandstone_dust2_arena(self) -> None:
        """Строит сбалансированную симметрично-фланговую арену в духе de_dust2."""
        half = self.ARENA_SIZE * 0.5
        wh = self.WALL_HEIGHT

        # 1. Основной песчаный пол арены
        floor = Entity(
            parent=self.root,
            model="cube",
            position=(0.0, -0.5, 0.0),
            scale=(self.ARENA_SIZE, 1.0, self.ARENA_SIZE),
            texture=self._floor_tex,
            texture_scale=Vec2(22, 22),
            color=color.rgb(224, 202, 162),
            collider="box",
        )
        self.entities.append(floor)

        # Каменная дорожка на центральном Миде
        mid_road = Entity(
            parent=self.root,
            model="cube",
            position=(0.0, -0.48, 0.0),
            scale=(7.5, 1.0, 44.0),
            texture=self._wall_tex,
            texture_scale=Vec2(3, 16),
            color=color.rgb(195, 180, 154),
        )
        self.entities.append(mid_road)

        # 2. Внешний периметр высоких стен
        self._add_wall((0.0, wh * 0.5, half), (self.ARENA_SIZE + 1.0, wh, 1.2))    # Север (T)
        self._add_wall((0.0, wh * 0.5, -half), (self.ARENA_SIZE + 1.0, wh, 1.2))   # Юг (CT)
        self._add_wall((half, wh * 0.5, 0.0), (1.2, wh, self.ARENA_SIZE + 1.0))    # Восток (A)
        self._add_wall((-half, wh * 0.5, 0.0), (1.2, wh, self.ARENA_SIZE + 1.0))   # Запад (B)

        # 3. Защитные щиты спавнов CT и T (исключают прострел в первую секунду раунда)
        self._add_wall((0.0, 1.65, -17.5), (8.5, 3.3, 0.9), color.rgb(214, 194, 158))
        self._add_wall((0.0, 1.65, 18.0), (9.0, 3.3, 0.9), color.rgb(214, 194, 158))

        # 4. Центральный Мид — знаменитые «Двойные двери» (проход посередине под перестрелки)
        self._add_wall((-5.4, 1.9, -1.5), (7.2, 3.8, 1.0))
        self._add_wall((5.4, 1.9, -1.5), (7.2, 3.8, 1.0))
        # Перемычка арки над двойными дверями
        self._add_wall((0.0, 4.4, -1.5), (4.0, 1.2, 1.0), color.rgb(186, 162, 128))

        # Знаменитый ящик Xbox возле дверей Мида (можно запрыгнуть по ступеньке!)
        self._add_crate((-2.4, 0.55, 0.4), size=1.1, rot_y=8.0)
        self._add_crate((-1.2, 0.80, 0.5), size=1.6, rot_y=4.0)

        # 5. Восточное крыло — Плент A (возвышение, укрытия и тройной стек ящиков)
        a_platform = Entity(
            parent=self.root,
            model="cube",
            position=(18.5, 0.35, 0.5),
            scale=(11.0, 0.7, 15.0),
            texture=self._wall_tex,
            texture_scale=Vec2(5, 7),
            color=color.rgb(210, 186, 145),
            collider="box",
        )
        self.entities.append(a_platform)
        # Ступень подъёма на Плент A со стороны CT и Мида
        self._add_wall((12.4, 0.18, -3.5), (1.6, 0.36, 4.5), color.rgb(205, 182, 142))
        self._add_wall((14.0, 2.0, 9.8), (7.5, 4.0, 1.0))
        self._add_wall((14.0, 2.0, -9.8), (7.5, 4.0, 1.0))

        # Ящики плента A (включая укрытие под присед / хедшот-позицию)
        self._add_crate((18.5, 1.45, 2.2), size=1.5, rot_y=12.0)
        self._add_crate((20.1, 1.45, 2.0), size=1.5, rot_y=-5.0)
        self._add_crate((19.3, 2.95, 2.1), size=1.45, rot_y=20.0)
        self._add_crate((16.2, 1.25, -4.2), size=1.15, rot_y=0.0)  # Низкий ящик под присед Ctrl!

        # 6. Западное крыло — Плент B (песчаные колонны, туннельная стена и связка ящиков)
        self._add_wall((-13.5, 2.1, 8.5), (1.2, 4.2, 9.0))
        self._add_wall((-13.5, 2.1, -9.0), (1.2, 4.2, 8.5))
        # Колонны B-плента
        for pz in (-5.0, 1.5, 7.5):
            self._add_wall((-20.5, 2.2, pz), (1.5, 4.4, 1.5), color.rgb(204, 178, 138))

        # Низкий парапет («окно» для стрельбы стоя и укрытия сидя на Ctrl!)
        self._add_wall((-13.5, 0.58, -0.5), (1.0, 1.16, 4.4), color.rgb(192, 168, 130))

        # Стек ящиков на B и выходах CT/T
        self._add_crate((-17.5, 0.75, -1.8), size=1.5, rot_y=-14.0)
        self._add_crate((-17.2, 2.25, -1.8), size=1.4, rot_y=18.0)
        self._add_crate((-8.0, 0.75, -12.0), size=1.5, rot_y=10.0)
        self._add_crate((8.2, 0.75, -11.5), size=1.5, rot_y=-12.0)
        self._add_crate((7.8, 0.75, 11.5), size=1.5, rot_y=15.0)
        self._add_crate((-7.8, 0.75, 11.8), size=1.5, rot_y=-8.0)
