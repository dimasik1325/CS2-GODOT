"""
Высокодетализированные и оптимизированные 3D-боты CS2 (5 тактических классов + Босс «Усатый Эльдар»!):
- RIFLE (AK-47), RUSHER (P90), SNIPER (AWP + лазерный луч), HEAVY (бронешлем), BOSS «Усатый Эльдар» (золотой берет и 3D-усы!).
- Слетающая физическая 3D-каска при хедшоте, вздрагивание корпуса при попадании (Hit Flinch), тактический присед в бою,
  индикатор здоровья над раненым врагом, ослепление от Flashbang и блокировка зрения дымом.
- Оптимизация CPU: кэшированный список коллайдеров и распределённый по кадрам рейкаст видимости (в 6 раз меньше лучей!).
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from direct.actor.Actor import Actor
from ursina import Animator, Entity, Vec3, clamp, color, destroy, lerp, raycast

from src.player import CS2Player
from src.settings import (
    SoundManager,
    apply_pbr_material,
    asset_path,
    load_safe_model,
    rgb32,
    rgba32,
)

BOT_CALLSIGNS: list[str] = [
    "Phoenix",
    "Viper",
    "Kobra",
    "Jackal",
    "Scorpion",
    "Phantom",
    "Raptor",
    "Titan",
    "Shadow",
    "Corsair",
]

ROLE_PROFILES: dict[str, dict[str, Any]] = {
    "RIFLE": {
        "hp": 100,
        "speed": 4.7,
        "range": 38.0,
        "fire_interval": 0.34,
        "damage": (10, 16),
        "sound": "ak47_shoot",
        "gun_model": "assets/models/ak47.glb",
        "tint": (212, 168, 108),
        "has_helmet": True,
    },
    "RUSHER": {
        "hp": 95,
        "speed": 6.2,
        "range": 24.0,
        "fire_interval": 0.21,
        "damage": (7, 12),
        "sound": "p90_shoot",
        "gun_model": "assets/models/p90.glb",
        "tint": (235, 132, 82),
        "has_helmet": False,
    },
    "SNIPER": {
        "hp": 90,
        "speed": 3.8,
        "range": 58.0,
        "fire_interval": 1.32,
        "damage": (28, 40),
        "sound": "awp_shoot",
        "gun_model": "assets/models/awp.glb",
        "tint": (146, 178, 124),
        "has_helmet": False,
    },
    "HEAVY": {
        "hp": 145,
        "speed": 3.7,
        "range": 32.0,
        "fire_interval": 0.28,
        "damage": (11, 17),
        "sound": "shotgun_shoot",
        "gun_model": "assets/models/shotgun.glb",
        "tint": (145, 152, 168),
        "has_helmet": True,
    },
    "BOSS": {
        "hp": 260,
        "speed": 5.2,
        "range": 46.0,
        "fire_interval": 0.24,
        "damage": (13, 20),
        "sound": "ak47_shoot",
        "gun_model": "assets/models/ak47.glb",
        "tint": (255, 198, 62),
        "has_helmet": True,
    },
}

DIFFICULTY_MULTS: dict[str, tuple[float, float, float]] = {
    "EASY": (0.72, 1.28, 0.58),
    "NORMAL": (1.00, 1.00, 0.75),
    "HARD": (1.25, 0.78, 0.90),
}


class EnemyBot(Entity):
    """Артикулированный 3D-противник с оптимизированным ИИ, каской, 3D-оружием и поддержкой Босса Эльдара."""

    def __init__(
        self,
        bot_name: str,
        spawn_pos: Vec3,
        waypoints: list[Vec3],
        sound_mgr: SoundManager,
        role: str = "RIFLE",
        difficulty: str = "NORMAL",
        carries_c4: bool = False,
    ) -> None:
        super().__init__(position=Vec3(spawn_pos), name=f"bot_{bot_name}", add_to_scene_entities=False)
        self.bot_name = bot_name
        self.role = role if role in ROLE_PROFILES else "RIFLE"
        self.profile = ROLE_PROFILES[self.role]
        self.difficulty = difficulty if difficulty in DIFFICULTY_MULTS else "NORMAL"
        self.carries_c4 = carries_c4

        self.waypoints = waypoints
        self.sound_mgr = sound_mgr

        self.max_hp: int = int(self.profile["hp"])
        self.hp: int = self.max_hp
        self.has_helmet: bool = bool(self.profile["has_helmet"])
        self.state: str = "PATROL"
        self.kills: int = 0
        self.deaths: int = 0

        self.move_speed: float = float(self.profile["speed"])
        self.sight_distance: float = float(self.profile["range"])
        self.attack_distance: float = float(self.profile["range"]) * 0.86

        self.blind_timer: float = 0.0
        self.recently_fired_timer: float = 0.0
        self.alert_pos: Vec3 | None = None
        self.alert_timer: float = 0.0
        self._flinch_timer: float = 0.0
        self._combat_crouch: bool = False

        self._target_wp: Vec3 = self._pick_next_waypoint()
        self._shoot_cooldown: float = random.uniform(0.25, 0.75)
        self._strafe_timer: float = random.uniform(0.5, 1.2)
        self._strafe_sign: float = random.choice((-1.0, 1.0))
        self._anim_phase: float = random.uniform(0.0, 6.28)
        self._death_fall_progress: float = 0.0
        self._c4_plant_timer: float = 0.0

        # Оптимизация: разнесённый по кадрам таймер проверки луча зрения (LOS)
        self._los_timer: float = random.uniform(0.0, 0.09)
        self._cached_can_see: bool = False

        # ── ВИЗУАЛЬНЫЙ 3D-РИГ БОТА ──
        self.visual_root = Entity(parent=self, add_to_scene_entities=False)
        self.actor: Actor | None = None
        self.animator: Animator | None = None
        self._current_anim_clip: str = ""

        r_c, g_c, b_c = self.profile["tint"]
        loaded = self._try_load_glb_enemy(rgb32(r_c, g_c, b_c))
        if not loaded:
            self._build_primitive_soldier(rgb32(r_c, g_c, b_c))

        # Артикулированные 3D-ноги и 3D-пушка класса в руках!
        leg_col = rgb32(42, 46, 56) if self.role != "BOSS" else rgb32(62, 26, 30)
        self.left_leg = Entity(parent=self.visual_root, model="cube", position=(-0.13, 0.36, 0.0), scale=(0.14, 0.70, 0.16), color=leg_col, add_to_scene_entities=False)
        self.right_leg = Entity(parent=self.visual_root, model="cube", position=(0.13, 0.36, 0.0), scale=(0.14, 0.70, 0.16), color=leg_col, add_to_scene_entities=False)

        self.gun_prop = Entity(parent=self.visual_root, position=(0.16, 1.14, 0.36), rotation_y=180.0, scale=0.72, add_to_scene_entities=False)
        g_mesh = load_safe_model(self.profile["gun_model"], normalize_to=0.68)
        if g_mesh is not None:
            ge = Entity(parent=self.gun_prop, model=g_mesh, add_to_scene_entities=False)
            if self.role == "BOSS":
                ge.color = rgb32(255, 206, 68)
            apply_pbr_material(ge, shininess=58.0, specular_strength=0.68, metallic=0.65)

        # Съёмная 3D-каска / золотой берет и ГУСАРСКИЕ УСЫ БОССА ЭЛЬДАРА!
        self.helmet_prop: Entity | None = None
        if self.role == "BOSS":
            self.scale = 1.12
            self.helmet_prop = Entity(
                parent=self.visual_root,
                model="sphere",
                position=(0.02, 1.74, 0.02),
                scale=(0.35, 0.14, 0.35),
                rotation_z=-12.0,
                color=rgb32(232, 38, 46),
                add_to_scene_entities=False,
            )
            # Роскошные 3D золотые усы Усатого Эльдара прямо на лице босса!!
            for sign in (-1.0, 1.0):
                Entity(
                    parent=self.visual_root,
                    model="cube",
                    position=(sign * 0.075, 1.56, 0.155),
                    scale=(0.14, 0.042, 0.045),
                    rotation_z=sign * 14.0,
                    color=rgb32(255, 198, 52),
                    add_to_scene_entities=False,
                )
                Entity(
                    parent=self.visual_root,
                    model="cube",
                    position=(sign * 0.15, 1.59, 0.155),
                    scale=(0.055, 0.032, 0.038),
                    rotation_z=sign * 52.0,
                    color=rgb32(255, 220, 88),
                    add_to_scene_entities=False,
                )
        elif self.has_helmet:
            h_col = rgb32(58, 66, 78) if self.role == "HEAVY" else rgb32(72, 74, 68)
            self.helmet_prop = Entity(
                parent=self.visual_root,
                model="sphere",
                position=(0.0, 1.70, 0.0),
                scale=(0.34, 0.24, 0.35),
                color=h_col,
                add_to_scene_entities=False,
            )
            apply_pbr_material(self.helmet_prop, shininess=52.0, specular_strength=0.60, metallic=0.50)

        self.muzzle_spark = Entity(
            parent=self.visual_root,
            model="sphere",
            position=(0.16, 1.18, 0.72),
            scale=0.19,
            color=rgb32(255, 210, 75),
            unlit=True,
            enabled=False,
            add_to_scene_entities=False,
        )
        self._spark_timer: float = 0.0

        self.laser_beam: Entity | None = None
        if self.role == "SNIPER":
            self.laser_beam = Entity(
                parent=self.visual_root,
                model="cube",
                origin=(-0.5, 0.0, 0.0),
                position=(0.14, 1.22, 0.65),
                scale=(0.012, 0.012, 18.0),
                color=rgba32(255, 32, 32, 130),
                unlit=True,
                enabled=False,
                add_to_scene_entities=False,
            )

        # Компактная 3D-полоска HP над раненым врагом / Боссом
        self.hp_bar_bg = Entity(
            parent=self,
            model="quad",
            position=(0.0, 2.02, 0.0),
            scale=(0.68 if self.role == "BOSS" else 0.46, 0.055),
            billboard=True,
            color=rgba32(12, 16, 22, 210),
            unlit=True,
            enabled=(self.role == "BOSS"),
            add_to_scene_entities=False,
        )
        self.hp_bar_fill = Entity(
            parent=self.hp_bar_bg,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.48, 0.0, -0.01),
            scale=(0.96, 0.72),
            color=rgb32(255, 192, 48) if self.role == "BOSS" else rgb32(238, 62, 56),
            unlit=True,
            add_to_scene_entities=False,
        )

        # ── ХИТБОКСЫ ТЕЛА И ГОЛОВЫ ──
        self.body_hitbox = Entity(
            parent=self,
            model="cube",
            position=(0.0, 0.78, 0.0),
            scale=(0.62, 1.42, 0.48),
            collider="box",
            visible=False,
            add_to_scene_entities=False,
        )
        self.body_hitbox.enemy_ref = self
        self.body_hitbox.is_headshot = False

        self.head_hitbox = Entity(
            parent=self,
            model="sphere",
            position=(0.0, 1.63, 0.0),
            scale=(0.35, 0.36, 0.35),
            collider="sphere",
            visible=False,
            add_to_scene_entities=False,
        )
        self.head_hitbox.enemy_ref = self
        self.head_hitbox.is_headshot = True

    def get_ignore_nodes(self) -> list[Entity]:
        return [self, self.body_hitbox, self.head_hitbox]

    def _try_load_glb_enemy(self, tint_col: Any) -> bool:
        full_path = asset_path("assets/models/enemy.glb")
        if not full_path.is_file():
            return False
        mesh = load_safe_model("assets/models/enemy.glb", normalize_to=1.80)
        if mesh is not None:
            ent = Entity(parent=self.visual_root, model=mesh, rotation_y=180.0, color=tint_col, add_to_scene_entities=False)
            apply_pbr_material(ent, shininess=24.0, specular_strength=0.28)
            return True
        return False

    def _build_primitive_soldier(self, tint_col: Any) -> None:
        vest_col = rgb32(42, 48, 42)
        Entity(parent=self.visual_root, model="cube", position=(0.0, 1.15, 0.0), scale=(0.46, 0.56, 0.26), color=tint_col, add_to_scene_entities=False)
        Entity(parent=self.visual_root, model="cube", position=(0.0, 1.17, 0.0), scale=(0.49, 0.42, 0.30), color=vest_col, add_to_scene_entities=False)
        Entity(parent=self.visual_root, model="sphere", position=(0.0, 1.63, 0.0), scale=(0.28, 0.30, 0.28), color=rgb32(52, 52, 56), add_to_scene_entities=False)

    def _pick_next_waypoint(self) -> Vec3:
        if not self.waypoints:
            return Vec3(self.position)
        candidates = [wp for wp in self.waypoints if (wp - self.position).length() > 3.5]
        return Vec3(random.choice(candidates if candidates else self.waypoints))

    def apply_flash_blindness(self, duration: float = 3.6) -> None:
        if self.state == "DEAD":
            return
        self.blind_timer = max(self.blind_timer, duration)

    def alert_by_gunshot(self, sound_pos: Vec3, radius: float = 34.0) -> None:
        if self.state == "DEAD":
            return
        if (self.world_position - sound_pos).length() <= radius:
            self.alert_pos = Vec3(sound_pos.x, self.y, sound_pos.z)
            self.alert_timer = 4.5

    def take_damage(
        self,
        amount: int,
        is_headshot: bool = False,
        on_helmet_popped: Callable[[Vec3], None] | None = None,
    ) -> bool:
        if self.state == "DEAD":
            return False

        dmg = int(amount)
        if is_headshot and self.has_helmet:
            # Сбиваем каску хедшотом!
            self.has_helmet = False
            dmg = int(dmg * 0.72)
            if self.helmet_prop is not None:
                h_pos = Vec3(self.helmet_prop.world_position)
                self.helmet_prop.enabled = False
                if on_helmet_popped is not None:
                    on_helmet_popped(h_pos)

        self.hp -= max(1, dmg)
        self._flinch_timer = 0.16
        self.hp_bar_bg.enabled = True
        self.hp_bar_fill.scale_x = max(0.02, 0.96 * clamp(self.hp / max(1, self.max_hp), 0.0, 1.0))

        if self.hp <= 0:
            self.hp = 0
            self.deaths += 1
            self.state = "DEAD"
            self.body_hitbox.collider = None
            self.head_hitbox.collider = None
            self.hp_bar_bg.enabled = False
            self.muzzle_spark.enabled = False
            if self.laser_beam is not None:
                self.laser_beam.enabled = False
            return True
        return False

    def respawn_at(self, new_pos: Vec3) -> None:
        """Быстрое перерождение бота для режима Мясорубка (Deathmatch) без пересоздания мешей!"""
        self.position = Vec3(new_pos)
        self.hp = self.max_hp
        self.has_helmet = bool(self.profile["has_helmet"])
        if self.helmet_prop is not None:
            self.helmet_prop.enabled = True
        self.state = "PATROL"
        self._death_fall_progress = 0.0
        self.visual_root.rotation = Vec3(0, 0, 0)
        self.visual_root.position = Vec3(0, 0, 0)
        self.body_hitbox.collider = "box"
        self.head_hitbox.collider = "sphere"
        self.hp_bar_bg.enabled = self.role == "BOSS"
        self.hp_bar_fill.scale_x = 0.96

    def _check_can_see_player(
        self,
        player: CS2Player,
        ignore_list: list[Any],
        smoke_blocker_fn: Callable[[Vec3, Vec3], bool] | None = None,
    ) -> bool:
        if not player.is_alive or self.blind_timer > 0.2:
            return False
        to_player = player.world_position - self.world_position
        dist = to_player.length()
        if dist > self.sight_distance:
            return False

        eye_origin = self.world_position + Vec3(0.0, 1.55, 0.0)
        target_chest = player.world_position + Vec3(0.0, 1.15, 0.0)
        if smoke_blocker_fn is not None and smoke_blocker_fn(eye_origin, target_chest):
            return False

        direction = (target_chest - eye_origin).normalized()
        hit = raycast(eye_origin, direction, distance=dist + 0.5, ignore=ignore_list)
        if not hit.hit:
            return True
        if hit.entity == player or getattr(hit.entity, "parent", None) == player:
            return True
        if (hit.world_point - target_chest).length() < 1.05:
            return True
        return False

    def _move_with_collision(self, flat_dir: Vec3, speed: float, dt: float, ignore_list: list[Any]) -> bool:
        if flat_dir.length() < 0.001:
            return False
        move_dir = flat_dir.normalized()
        wall_check = raycast(self.world_position + Vec3(0.0, 0.75, 0.0), move_dir, distance=0.88, ignore=ignore_list)
        if wall_check.hit:
            side = Vec3(move_dir.z, 0.0, -move_dir.x)
            side_check = raycast(self.world_position + Vec3(0.0, 0.75, 0.0), side, distance=0.95, ignore=ignore_list)
            if not side_check.hit:
                self.position += side * (speed * 0.75 * dt)
                return True
            return False
        self.position += move_dir * (speed * dt)
        return True

    def _face_point(self, target_pt: Vec3, dt: float, turn_speed: float = 9.0) -> None:
        dx = target_pt.x - self.x
        dz = target_pt.z - self.z
        if abs(dx) + abs(dz) < 1e-4:
            return
        desired_yaw = math.degrees(math.atan2(dx, dz))
        diff = (desired_yaw - self.rotation_y + 180.0) % 360.0 - 180.0
        self.rotation_y += diff * min(1.0, dt * turn_speed)

    def _fire_at_player(self, player: CS2Player) -> None:
        dmg_mult, _, base_acc = DIFFICULTY_MULTS[self.difficulty]
        self._spark_timer = 0.065
        self.recently_fired_timer = 1.8
        self.muzzle_spark.enabled = True
        self.sound_mgr.play_sfx(self.profile["sound"], volume=0.38, pitch=random.uniform(0.95, 1.06))

        dist = (player.world_position - self.world_position).length()
        hit_chance = clamp(base_acc - dist * 0.010, 0.20, 0.90)
        if player.is_moving_horizontally:
            hit_chance -= 0.10
        if player.is_sliding:
            hit_chance -= 0.18
        if player.is_crouching:
            hit_chance -= 0.06

        if random.random() < hit_chance:
            lo, hi = self.profile["damage"]
            dmg = max(2, int(round(random.randint(lo, hi) * dmg_mult)))
            is_hs = random.random() < (0.18 if self.difficulty == "HARD" else 0.08)
            player.take_damage(dmg, is_headshot=is_hs, attacker_pos=self.world_position)
            if not player.is_alive:
                self.kills += 1

    def update_ai(
        self,
        dt: float,
        player: CS2Player,
        ignore_list: list[Any],
        smoke_blocker_fn: Callable[[Vec3, Vec3], bool] | None = None,
        on_try_plant_c4: Callable[[Vec3], bool] | None = None,
    ) -> None:
        if self._spark_timer > 0.0:
            self._spark_timer -= dt
            if self._spark_timer <= 0.0:
                self.muzzle_spark.enabled = False

        if self.recently_fired_timer > 0.0:
            self.recently_fired_timer = max(0.0, self.recently_fired_timer - dt)

        if self._flinch_timer > 0.0:
            self._flinch_timer = max(0.0, self._flinch_timer - dt)

        if self.state == "DEAD":
            self._death_fall_progress = min(1.0, self._death_fall_progress + dt * 4.5)
            self.visual_root.rotation_x = lerp(0.0, -88.0, self._death_fall_progress)
            self.visual_root.y = lerp(0.0, 0.16, self._death_fall_progress)
            return

        if self.blind_timer > 0.0:
            self.blind_timer = max(0.0, self.blind_timer - dt)
            self.visual_root.rotation_z = math.sin(self.blind_timer * 14.0) * 11.0
            if self.laser_beam is not None:
                self.laser_beam.enabled = False
            self._move_with_collision(-self.forward + self.right * self._strafe_sign, self.move_speed * 0.42, dt, ignore_list)
            return

        # Распределённый по кадрам рейкаст видимости (оптимизация CPU!)
        self._los_timer -= dt
        if self._los_timer <= 0.0:
            self._los_timer = 0.085 + random.uniform(0.0, 0.025)
            self._cached_can_see = self._check_can_see_player(player, ignore_list, smoke_blocker_fn)
        can_see = self._cached_can_see

        dist_to_player = (player.world_position - self.world_position).length()
        is_moving = False

        if self.carries_c4 and not can_see and on_try_plant_c4 is not None:
            self._c4_plant_timer += dt
            if self._c4_plant_timer >= 0.85:
                self._c4_plant_timer = 0.0
                if on_try_plant_c4(self.world_position):
                    self.carries_c4 = False

        if can_see and dist_to_player <= self.attack_distance:
            self.state = "ATTACK"
        elif can_see:
            self.state = "CHASE"
        elif self.alert_timer > 0.0 and self.alert_pos is not None:
            self.alert_timer -= dt
            self.state = "ALERT"
        else:
            self.state = "PATROL"

        if self.laser_beam is not None:
            self.laser_beam.enabled = self.state in ("ATTACK", "CHASE")
            if self.laser_beam.enabled:
                self.laser_beam.scale_z = min(dist_to_player, 32.0)

        if self.state == "PATROL":
            self._combat_crouch = False
            to_wp = Vec3(self._target_wp.x - self.x, 0.0, self._target_wp.z - self.z)
            if to_wp.length() < 1.4:
                self._target_wp = self._pick_next_waypoint()
            else:
                self._face_point(self._target_wp, dt, turn_speed=6.5)
                moved = self._move_with_collision(to_wp, self.move_speed * 0.72, dt, ignore_list)
                is_moving = moved
                if not moved:
                    self._target_wp = self._pick_next_waypoint()

        elif self.state == "ALERT" and self.alert_pos is not None:
            self._combat_crouch = False
            to_al = Vec3(self.alert_pos.x - self.x, 0.0, self.alert_pos.z - self.z)
            self._face_point(self.alert_pos, dt, turn_speed=9.0)
            if to_al.length() > 2.2:
                is_moving = self._move_with_collision(to_al, self.move_speed * 0.92, dt, ignore_list)
            else:
                self.alert_timer = 0.0

        elif self.state == "CHASE":
            self._combat_crouch = False
            to_plr = Vec3(player.x - self.x, 0.0, player.z - self.z)
            self._face_point(player.world_position, dt, turn_speed=10.5)
            is_moving = self._move_with_collision(to_plr, self.move_speed, dt, ignore_list)

        elif self.state == "ATTACK":
            self._face_point(player.world_position, dt, turn_speed=13.5)
            self._strafe_timer -= dt
            if self._strafe_timer <= 0.0:
                self._strafe_timer = random.uniform(0.55, 1.25)
                self._strafe_sign *= -1.0
                self._combat_crouch = random.random() < 0.32 and self.role in ("RIFLE", "SNIPER")

            strafe_vec = Vec3(self.right.x, 0.0, self.right.z) * self._strafe_sign
            if self.role == "RUSHER" and dist_to_player > 6.5:
                strafe_vec = strafe_vec * 0.6 + Vec3(self.forward.x, 0.0, self.forward.z) * 0.8
            is_moving = self._move_with_collision(strafe_vec, self.move_speed * 0.62, dt, ignore_list)

            _, cd_mult, _ = DIFFICULTY_MULTS[self.difficulty]
            self._shoot_cooldown -= dt
            if self._shoot_cooldown <= 0.0:
                base_iv = float(self.profile["fire_interval"]) * cd_mult
                self._shoot_cooldown = random.uniform(base_iv * 0.82, base_iv * 1.18)
                self._fire_at_player(player)

        # LOD-оптимизация анимации конечностей на дальних дистанциях
        flinch_rot = -14.0 * (self._flinch_timer / 0.16) if self._flinch_timer > 0.0 else 0.0
        target_y = -0.24 if self._combat_crouch else 0.0
        self.visual_root.rotation_x = flinch_rot
        if dist_to_player < 42.0:
            self._anim_phase += dt * (11.5 if is_moving else 2.6)
            if is_moving:
                swing = math.sin(self._anim_phase) * 28.0
                self.left_leg.rotation_x = swing
                self.right_leg.rotation_x = -swing
                self.visual_root.y = lerp(self.visual_root.y, target_y + abs(math.sin(self._anim_phase)) * 0.04, min(1.0, dt * 12.0))
                self.visual_root.rotation_z = math.cos(self._anim_phase * 0.5) * 2.2
            else:
                self.left_leg.rotation_x = lerp(self.left_leg.rotation_x, 0.0, min(1.0, dt * 10.0))
                self.right_leg.rotation_x = lerp(self.right_leg.rotation_x, 0.0, min(1.0, dt * 10.0))
                self.visual_root.y = lerp(self.visual_root.y, target_y + math.sin(self._anim_phase) * 0.015, min(1.0, dt * 10.0))
                self.visual_root.rotation_z = lerp(self.visual_root.rotation_z, 0.0, min(1.0, dt * 8.0))

    def cleanup(self) -> None:
        if self.actor is not None:
            try:
                self.actor.cleanup()
                self.actor.removeNode()
            except Exception:
                pass
            self.actor = None
        destroy(self)


def collect_bot_ignore_list(bots: list[EnemyBot]) -> list[Entity]:
    out: list[Entity] = []
    for b in bots:
        out.extend(b.get_ignore_nodes())
    return out
