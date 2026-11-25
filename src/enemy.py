"""
Продвинутый искусственный интеллект врагов-ботов CS2 (4 тактических класса):
- RIFLE (Штурмовик AK-47): сбалансированный бой, стрейф и приседание в перестрелке
- RUSHER (Фланговый рашер MP9): высокая скорость сближения, зелёные очки ПНВ
- SNIPER (Снайпер AWP): дальний бой, видимый красный лазерный целеуказатель при наведении!
- HEAVY (Тяжёлый боец 140 HP + бронешлем): мощный дробовик вблизи, стальная броня
Поддерживает:
- Анимированные 3D-конечности (шаг ногами и ботинками, наклон корпуса, ослепление от Flashbang!)
- Полное перекрытие обзора дымовыми гранатами (Smoke Occlusion)
- Реакцию по слуху на громкие выстрелы без глушителя (M4A1-S и USP-S остаются бесшумными!)
- Закладку бомбы C4 при выходе бота на свободный плент A или B
"""

from __future__ import annotations

import math
import random
from typing import Callable, Iterable

from direct.actor.Actor import Actor
from ursina import Entity, Vec3, color, destroy, invoke, lerp, raycast

from src.player import CS2Player
from src.settings import SoundManager, apply_pbr_material, load_safe_model, resource_path, rgb32, rgba32


BOT_CALLSIGNS: tuple[str, ...] = (
    "BOT Phoenix",
    "BOT Viper",
    "BOT Sabre",
    "BOT Jackal",
    "BOT Corsair",
    "BOT Nomad",
    "BOT Titan",
    "BOT Raven",
    "BOT Scorpion",
    "BOT Mirage",
)

ROLE_PROFILES: dict[str, dict[str, float | int | str]] = {
    "RIFLE": {
        "hp": 100,
        "patrol_spd": 3.0,
        "chase_spd": 4.3,
        "sight": 46.0,
        "attack_range": 28.0,
        "shoot_sound": "ak47_shoot",
        "dmg_min": 11,
        "dmg_max": 18,
        "burst_min": 2,
        "burst_max": 4,
    },
    "RUSHER": {
        "hp": 95,
        "patrol_spd": 3.8,
        "chase_spd": 5.5,
        "sight": 40.0,
        "attack_range": 18.0,
        "shoot_sound": "mp9_shoot",
        "dmg_min": 8,
        "dmg_max": 14,
        "burst_min": 4,
        "burst_max": 6,
    },
    "SNIPER": {
        "hp": 90,
        "patrol_spd": 2.5,
        "chase_spd": 3.5,
        "sight": 62.0,
        "attack_range": 48.0,
        "shoot_sound": "awp_shoot",
        "dmg_min": 28,
        "dmg_max": 42,
        "burst_min": 1,
        "burst_max": 1,
    },
    "HEAVY": {
        "hp": 140,
        "patrol_spd": 2.5,
        "chase_spd": 3.6,
        "sight": 42.0,
        "attack_range": 21.0,
        "shoot_sound": "shotgun_shoot",
        "dmg_min": 15,
        "dmg_max": 24,
        "burst_min": 1,
        "burst_max": 2,
    },
}


class EnemyBot(Entity):
    """Боевой 3D-бот с классами экипировки, анимацией шага, реакцией на дым/флешку и раздельными хитбоксами."""

    def __init__(
        self,
        bot_name: str,
        spawn_pos: Vec3 | tuple[float, float, float],
        waypoints: list[Vec3],
        sound_mgr: SoundManager,
        role: str = "RIFLE",
        difficulty: str = "NORMAL",
        carries_c4: bool = False,
    ) -> None:
        super().__init__(position=Vec3(*spawn_pos))
        self.bot_name = bot_name
        self.sound_mgr = sound_mgr
        self.role = role if role in ROLE_PROFILES else "RIFLE"
        self.difficulty = difficulty if difficulty in ("EASY", "NORMAL", "HARD") else "NORMAL"
        self.carries_c4: bool = carries_c4

        prof = ROLE_PROFILES[self.role]
        self.max_hp: int = int(prof["hp"])
        self.hp: int = self.max_hp
        self.patrol_speed: float = float(prof["patrol_spd"])
        self.chase_speed: float = float(prof["chase_spd"])
        self.strafe_speed: float = 2.6 if self.role != "RUSHER" else 3.4
        self.sight_range: float = float(prof["sight"])
        self.attack_range: float = float(prof["attack_range"])
        self.shoot_sound: str = str(prof["shoot_sound"])
        self.dmg_min: int = int(prof["dmg_min"])
        self.dmg_max: int = int(prof["dmg_max"])
        self.burst_min: int = int(prof["burst_min"])
        self.burst_max: int = int(prof["burst_max"])

        self.waypoints = waypoints if waypoints else [Vec3(*spawn_pos)]
        self.state: str = "PATROL"  # PATROL | CHASE | ATTACK | DEAD
        self.actor: Actor | None = None
        self.kills: int = 0
        self.deaths: int = 0

        # Корневой узел визуальной 3D-модели с раздельными ногами/руками для живой походки
        self.visual_root = Entity(parent=self, position=(0.0, 0.0, 0.0))
        self.mesh_node = Entity(parent=self.visual_root)
        self.left_leg_pivot: Entity | None = None
        self.right_leg_pivot: Entity | None = None
        self.blind_arm: Entity | None = None
        self.laser_beam: Entity | None = None

        self._build_articulated_3d_bot()

        # Вспышка выстрела на дульном срезе
        self.muzzle_flash = Entity(
            parent=self.visual_root,
            model="sphere",
            position=(0.14, 1.15, 0.78),
            scale=0.15,
            color=rgb32(255, 218, 92),
            unlit=True,
            enabled=False,
        )

        # Раздельные невидимые коллайдеры-хитбоксы для Headshot / Bodyshot
        self.body_hitbox = Entity(
            parent=self,
            model=None,
            collider="box",
            position=(0.0, 0.74, 0.0),
            scale=(0.64, 1.44, 0.50),
        )
        self.body_hitbox.enemy_ref = self
        self.body_hitbox.is_head = False

        self.head_hitbox = Entity(
            parent=self,
            model=None,
            collider="box",
            position=(0.0, 1.68, 0.0),
            scale=(0.38, 0.38, 0.38),
        )
        self.head_hitbox.enemy_ref = self
        self.head_hitbox.is_head = True

        # Полоска HP и метка класса/ослепления над головой
        self.hp_bar_bg = Entity(
            parent=self,
            model="quad",
            position=(0.0, 2.08, 0.0),
            scale=(0.64, 0.068),
            color=rgba32(15, 18, 22, 205),
            billboard=True,
            unlit=True,
            enabled=False,
        )
        self.hp_bar_fill = Entity(
            parent=self.hp_bar_bg,
            model="quad",
            origin=(-0.5, 0.0),
            position=(-0.48, 0.0, -0.01),
            scale=(0.96, 0.72),
            color=rgb32(235, 65, 55) if self.role != "HEAVY" else rgb32(255, 175, 45),
            unlit=True,
        )

        # Таймеры ИИ
        self._wp_index: int = random.randrange(len(self.waypoints))
        self._reaction_timer: float = 0.35
        self._shoot_cooldown: float = random.uniform(0.3, 0.8)
        self._burst_left: int = 0
        self._strafe_dir: float = random.choice((-1.0, 1.0))
        self._strafe_switch_timer: float = random.uniform(1.0, 2.2)
        self._walk_cycle: float = random.uniform(0.0, 6.28)
        self._alert_memory: float = 0.0
        self._investigate_pos: Vec3 | None = None
        self.blind_timer: float = 0.0
        self.recently_fired_timer: float = 0.0
        self._c4_plant_timer: float = 0.0

    def _build_articulated_3d_bot(self) -> None:
        """
        Создаёт проработанную 3D-фигуру бойца с индивидуальной экипировкой класса,
        шарнирными ногами для анимации бега, шлемом/визором и 3D-оружием в руках.
        Если пользователь положил кастомный скелетный enemy.glb с анимациями — загружает его.
        """
        full_file = resource_path("assets/models/enemy.glb")
        model_np = load_safe_model("assets/models/enemy.glb", target_max_extent=1.86, align_bottom_zero=True)
        if model_np is not None and not model_np.find("**/+Character").isEmpty() and full_file.is_file():
            try:
                candidate = Actor(str(full_file))
                anims = candidate.getAnimNames()
                if anims:
                    self.mesh_node.rotation_y = 180.0
                    candidate.reparentTo(self.mesh_node)
                    self.actor = candidate
                    if "idle" in anims:
                        self.actor.loop("idle")
                    return
                candidate.cleanup()
            except Exception:
                pass

        # Цветовая схема по классу бойца
        if self.role == "RUSHER":
            jacket = rgb32(92, 102, 114)
            vest = rgb32(34, 38, 44)
            pants = rgb32(58, 64, 72)
            visor = rgb32(72, 245, 118)   # Зелёный прибор ночного видения!
        elif self.role == "SNIPER":
            jacket = rgb32(138, 128, 86)
            vest = rgb32(58, 62, 46)
            pants = rgb32(92, 88, 62)
            visor = rgb32(255, 72, 52)
        elif self.role == "HEAVY":
            jacket = rgb32(62, 66, 74)
            vest = rgb32(32, 35, 42)
            pants = rgb32(44, 48, 56)
            visor = rgb32(255, 196, 48)   # Золотистый штурмовой забрал!
        else:  # RIFLE
            jacket = rgb32(176, 142, 96)
            vest = rgb32(44, 48, 54)
            pants = rgb32(66, 76, 60)
            visor = rgb32(232, 52, 42)

        dark = rgb32(28, 30, 34)
        gun_col = rgb32(42, 45, 50) if self.role != "SNIPER" else rgb32(56, 78, 48)

        # Левая и правая ноги с шарниром в бедре (y=0.84) для реалистичного бега!
        self.left_leg_pivot = Entity(parent=self.mesh_node, position=(-0.14, 0.84, 0.0))
        self.right_leg_pivot = Entity(parent=self.mesh_node, position=(0.14, 0.84, 0.0))
        for leg_piv in (self.left_leg_pivot, self.right_leg_pivot):
            thigh = Entity(parent=leg_piv, model="cube", position=(0.0, -0.42, 0.0), scale=(0.19, 0.82, 0.22), color=pants)
            knee = Entity(parent=leg_piv, model="cube", position=(0.0, -0.40, 0.11), scale=(0.16, 0.14, 0.06), color=dark)
            boot = Entity(parent=leg_piv, model="cube", position=(0.0, -0.78, 0.04), scale=(0.20, 0.13, 0.28), color=dark)
            apply_pbr_material(thigh, "fabric")
            apply_pbr_material(knee, "polymer")
            apply_pbr_material(boot, "polymer")

        # Торс, разгрузка с подсумками, наплечники и рюкзак (или бомба C4 за спиной!)
        torso_w = 0.56 if self.role == "HEAVY" else 0.49
        torso = Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.16, 0.0), scale=(torso_w, 0.66, 0.30), color=jacket)
        carrier = Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.18, 0.02), scale=(torso_w - 0.04, 0.48, 0.35), color=vest)
        apply_pbr_material(torso, "fabric")
        apply_pbr_material(carrier, "polymer")

        for px in (-0.11, 0.0, 0.11):
            Entity(parent=self.mesh_node, model="cube", position=(px, 1.06, 0.20), scale=(0.08, 0.14, 0.06), color=dark)

        pack_col = rgb32(198, 52, 42) if self.carries_c4 else rgb32(68, 74, 58)
        Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.20, -0.20), scale=(0.32, 0.38, 0.15), color=pack_col)

        # Руки и оружие
        self.blind_arm = Entity(
            parent=self.mesh_node,
            model="cube",
            position=(-0.33, 1.22, 0.14),
            scale=(0.15, 0.52, 0.18),
            rotation_x=-38.0,
            color=jacket,
        )
        r_arm = Entity(
            parent=self.mesh_node,
            model="cube",
            position=(0.33, 1.18, 0.15),
            scale=(0.15, 0.52, 0.18),
            rotation_x=-42.0,
            color=jacket,
        )
        apply_pbr_material(self.blind_arm, "fabric")
        apply_pbr_material(r_arm, "fabric")

        gun_len = 0.78 if self.role == "SNIPER" else (0.44 if self.role == "RUSHER" else 0.60)
        gun_ent = Entity(
            parent=self.mesh_node,
            model="cube",
            position=(0.14, 1.14, 0.44),
            scale=(0.075, 0.12, gun_len),
            color=gun_col,
        )
        apply_pbr_material(gun_ent, "steel")

        # Голова, тактический шлем и светящиеся очки/визор
        head = Entity(parent=self.mesh_node, model="sphere", position=(0.0, 1.67, 0.0), scale=(0.34, 0.36, 0.34), color=dark)
        helmet_sc = (0.40, 0.22, 0.40) if self.role == "HEAVY" else (0.37, 0.18, 0.37)
        helmet = Entity(parent=self.mesh_node, model="sphere", position=(0.0, 1.75, -0.01), scale=helmet_sc, color=vest)
        apply_pbr_material(head, "fabric")
        apply_pbr_material(helmet, "metal" if self.role == "HEAVY" else "polymer")
        Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.69, 0.16), scale=(0.25, 0.085, 0.06), color=visor, unlit=True)

        # Красный лазерный луч прицеливания у снайпера!
        if self.role == "SNIPER":
            self.laser_beam = Entity(
                parent=self.mesh_node,
                model="cube",
                position=(0.14, 1.17, 6.5),
                scale=(0.012, 0.012, 12.0),
                color=rgba32(255, 36, 36, 155),
                unlit=True,
                enabled=False,
            )

    def get_ignore_entities(self) -> tuple[Entity, ...]:
        return (self, self.body_hitbox, self.head_hitbox)

    def apply_flash_blindness(self, duration: float) -> None:
        """Ослепляет бота светошумовой гранатой: он закрывает глаза рукой и теряет прицел."""
        if self.state == "DEAD":
            return
        self.blind_timer = max(self.blind_timer, duration)
        if self.laser_beam is not None:
            self.laser_beam.enabled = False

    def alert_by_gunshot(self, shooter_pos: Vec3, radius: float = 34.0) -> None:
        """Тревожит бота звуком выстрела без глушителя."""
        if self.state == "DEAD":
            return
        if (self.world_position - shooter_pos).length() <= radius:
            self._alert_memory = max(self._alert_memory, 4.5)
            self._investigate_pos = Vec3(shooter_pos)

    def _has_line_of_sight(
        self,
        player: CS2Player,
        ignore_all_bots: list[Entity],
        smoke_blocker_fn: Callable[[Vec3, Vec3], bool] | None = None,
    ) -> bool:
        if self.blind_timer > 0.0:
            return False

        eye_pos = self.world_position + Vec3(0.0, 1.58, 0.0)
        target_pos = player.world_position + Vec3(0.0, player.height * 0.88, 0.0)
        to_player = target_pos - eye_pos
        dist = to_player.length()
        if dist > self.sight_range:
            return False

        if smoke_blocker_fn is not None and smoke_blocker_fn(eye_pos, target_pos):
            return False

        if dist < 0.65:
            return True

        direction = to_player.normalized()
        if self.state == "PATROL" and self._alert_memory <= 0.0 and dist > 12.0:
            forward_flat = Vec3(self.forward.x, 0.0, self.forward.z).normalized()
            dir_flat = Vec3(direction.x, 0.0, direction.z).normalized()
            if forward_flat.dot(dir_flat) < -0.25:
                return False

        obstacle_hit = raycast(
            eye_pos,
            direction,
            distance=max(0.2, dist - 0.45),
            ignore=ignore_all_bots,
        )
        return not obstacle_hit.hit

    def _animate_walk_limbs(self, dt: float, speed: float, moving: bool) -> None:
        if moving:
            self._walk_cycle += dt * speed * 2.8
            swing = math.sin(self._walk_cycle) * 32.0
            self.visual_root.y = abs(math.sin(self._walk_cycle)) * 0.048
            if self.left_leg_pivot is not None and self.right_leg_pivot is not None:
                self.left_leg_pivot.rotation_x = swing
                self.right_leg_pivot.rotation_x = -swing
        else:
            self.visual_root.y = lerp(self.visual_root.y, 0.0, min(1.0, dt * 10.0))
            if self.left_leg_pivot is not None and self.right_leg_pivot is not None:
                self.left_leg_pivot.rotation_x = lerp(self.left_leg_pivot.rotation_x, 0.0, min(1.0, dt * 10.0))
                self.right_leg_pivot.rotation_x = lerp(self.right_leg_pivot.rotation_x, 0.0, min(1.0, dt * 10.0))

    def _move_with_collision(self, move_dir: Vec3, speed: float, dt: float, ignore_list: list[Entity]) -> bool:
        flat_dir = Vec3(move_dir.x, 0.0, move_dir.z)
        if flat_dir.length() < 1e-4:
            self._animate_walk_limbs(dt, 0.0, False)
            return False
        flat_dir = flat_dir.normalized()

        low_hit = raycast(self.world_position + Vec3(0, 0.55, 0), flat_dir, distance=0.78, ignore=ignore_list)
        high_hit = raycast(self.world_position + Vec3(0, 1.35, 0), flat_dir, distance=0.78, ignore=ignore_list)
        if low_hit.hit or high_hit.hit:
            self._animate_walk_limbs(dt, 0.0, False)
            return False

        self.position += flat_dir * (speed * dt)
        ground_ray = raycast(
            self.world_position + Vec3(0, 1.6, 0),
            Vec3(0, -1, 0),
            distance=4.2,
            ignore=ignore_list,
        )
        if ground_ray.hit and ground_ray.world_point.y - self.y < 0.72:
            self.y = lerp(self.y, ground_ray.world_point.y, min(1.0, dt * 14.0))

        self._animate_walk_limbs(dt, speed, True)
        return True

    def _face_point_smooth(self, target_pt: Vec3, dt: float, turn_speed: float = 9.0) -> None:
        dx = target_pt.x - self.x
        dz = target_pt.z - self.z
        if abs(dx) + abs(dz) < 1e-4:
            return
        desired_yaw = math.degrees(math.atan2(dx, dz))
        delta = (desired_yaw - self.rotation_y + 180.0) % 360.0 - 180.0
        self.rotation_y += delta * min(1.0, dt * turn_speed)

    def update_ai(
        self,
        dt: float,
        player: CS2Player,
        ignore_all_bots: list[Entity],
        smoke_blocker_fn: Callable[[Vec3, Vec3], bool] | None = None,
        on_try_plant_c4: Callable[[Vec3], bool] | None = None,
    ) -> None:
        if self.state == "DEAD" or not self.enabled:
            return

        if self.recently_fired_timer > 0.0:
            self.recently_fired_timer = max(0.0, self.recently_fired_timer - dt)

        # Если бот ослеплён флешкой — шатается на месте и прикрывает глаза рукой
        if self.blind_timer > 0.0:
            self.blind_timer = max(0.0, self.blind_timer - dt)
            if self.blind_arm is not None:
                self.blind_arm.rotation_x = -115.0
            self.rotation_y += math.sin(self.blind_timer * 7.0) * 55.0 * dt
            self._animate_walk_limbs(dt, 1.5, True)
            return
        elif self.blind_arm is not None:
            self.blind_arm.rotation_x = -38.0

        if not player.is_alive:
            self.state = "PATROL"
            if self.laser_beam is not None:
                self.laser_beam.enabled = False
            self._animate_walk_limbs(dt, 0.0, False)
            return

        if self._alert_memory > 0.0:
            self._alert_memory = max(0.0, self._alert_memory - dt)

        can_see = self._has_line_of_sight(player, ignore_all_bots, smoke_blocker_fn)
        dist_to_player = (player.world_position - self.world_position).length()

        diff_mult = {"EASY": 1.35, "NORMAL": 1.0, "HARD": 0.68}[self.difficulty]

        if can_see:
            if self.state == "PATROL":
                self._reaction_timer = random.uniform(0.24, 0.44) * diff_mult
            self._alert_memory = 5.0
            self._investigate_pos = Vec3(player.world_position)
            self.state = "ATTACK" if dist_to_player <= self.attack_range else "CHASE"
        elif self._alert_memory > 0.0:
            self.state = "CHASE"
        else:
            self.state = "PATROL"

        if self.laser_beam is not None:
            self.laser_beam.enabled = bool(self.state == "ATTACK" and can_see)

        # Попытка бота-подрывника заложить бомбу C4 на точке A или B, если рядом нет огня игрока
        if self.carries_c4 and not can_see and on_try_plant_c4 is not None:
            if on_try_plant_c4(self.world_position):
                self.carries_c4 = False

        if self.state == "PATROL":
            target_wp = self.waypoints[self._wp_index]
            to_wp = Vec3(target_wp.x - self.x, 0.0, target_wp.z - self.z)
            if to_wp.length() < 1.4:
                self._wp_index = (self._wp_index + random.choice((1, 2))) % len(self.waypoints)
                target_wp = self.waypoints[self._wp_index]
                to_wp = Vec3(target_wp.x - self.x, 0.0, target_wp.z - self.z)

            self._face_point_smooth(target_wp, dt, turn_speed=5.8)
            if not self._move_with_collision(to_wp, self.patrol_speed, dt, ignore_all_bots):
                self._wp_index = (self._wp_index + 1) % len(self.waypoints)

        elif self.state == "CHASE":
            chase_goal = self._investigate_pos if self._investigate_pos is not None else player.world_position
            self._face_point_smooth(chase_goal, dt, turn_speed=8.8)
            to_goal = chase_goal - self.world_position
            if not self._move_with_collision(to_goal, self.chase_speed, dt, ignore_all_bots):
                side = Vec3(self.right.x * self._strafe_dir, 0.0, self.right.z * self._strafe_dir)
                self._move_with_collision(side, self.chase_speed * 0.85, dt, ignore_all_bots)

        elif self.state == "ATTACK":
            self._face_point_smooth(player.world_position, dt, turn_speed=11.5)

            self._strafe_switch_timer -= dt
            if self._strafe_switch_timer <= 0.0:
                self._strafe_dir *= -1.0
                self._strafe_switch_timer = random.uniform(0.9, 2.0)

            if self.role == "SNIPER":
                # Снайпер останавливается перед выстрелом для максимальной точности
                self._animate_walk_limbs(dt, 0.0, False)
            else:
                strafe_vec = Vec3(self.right.x * self._strafe_dir, 0.0, self.right.z * self._strafe_dir)
                ideal_dist = 9.0 if self.role in ("RUSHER", "HEAVY") else 16.5
                if dist_to_player > ideal_dist:
                    strafe_vec += (player.world_position - self.world_position).normalized() * 0.65
                elif dist_to_player < 6.5:
                    strafe_vec -= (player.world_position - self.world_position).normalized() * 0.50
                self._move_with_collision(strafe_vec, self.strafe_speed, dt, ignore_all_bots)

            if self._reaction_timer > 0.0:
                self._reaction_timer -= dt
                return

            self._shoot_cooldown -= dt
            if self._shoot_cooldown <= 0.0 and can_see:
                self._fire_at_player(player, dist_to_player)

    def _fire_at_player(self, player: CS2Player, distance: float) -> None:
        if self._burst_left <= 0:
            self._burst_left = random.randint(self.burst_min, self.burst_max)

        self._burst_left -= 1
        if self.role == "SNIPER":
            self._shoot_cooldown = random.uniform(1.35, 1.95)
        elif self.role == "RUSHER":
            self._shoot_cooldown = 0.09 if self._burst_left > 0 else random.uniform(0.50, 0.90)
        else:
            self._shoot_cooldown = 0.14 if self._burst_left > 0 else random.uniform(0.62, 1.12)

        self.recently_fired_timer = 1.6
        self.muzzle_flash.enabled = True
        invoke(setattr, self.muzzle_flash, "enabled", False, delay=0.05)

        attenuation = max(0.18, min(0.78, 12.0 / max(distance, 4.0)))
        self.sound_mgr.play_sfx(self.shoot_sound, volume=attenuation, pitch=random.uniform(0.94, 1.04))

        acc_mult = {"EASY": 0.72, "NORMAL": 1.0, "HARD": 1.28}[self.difficulty]
        crouch_factor = 0.68 if player.is_crouching else 1.0
        move_evasion = 0.78 if (player.is_sprinting or player.is_sliding) else 1.0
        base_hit_prob = max(0.12, 0.56 - distance * 0.010) * crouch_factor * move_evasion * acc_mult

        if random.random() < base_hit_prob:
            dmg = random.randint(self.dmg_min, self.dmg_max)
            is_hs = random.random() < 0.12
            hp_after = player.take_damage(dmg, is_headshot=is_hs)
            if hp_after <= 0:
                self.kills += 1

    def take_damage(self, amount: int, is_headshot: bool = False) -> bool:
        if self.state == "DEAD":
            return False

        dmg = int(amount)
        if self.role == "HEAVY" and is_headshot:
            dmg = int(dmg * 0.78)  # Тяжёлый штурмовой шлем снижает входящий урон!

        self.hp = max(0, self.hp - max(1, dmg))
        self._alert_memory = 6.5

        self.hp_bar_bg.enabled = self.hp > 0
        ratio = max(0.0, self.hp / float(self.max_hp))
        self.hp_bar_fill.scale_x = max(0.01, 0.96 * ratio)

        self.visual_root.y = 0.06
        invoke(setattr, self.visual_root, "y", 0.0, delay=0.06)

        if self.hp <= 0:
            self.deaths += 1
            self._die(is_headshot=is_headshot)
            return True
        return False

    def _die(self, is_headshot: bool = False) -> None:
        self.state = "DEAD"
        self.hp_bar_bg.enabled = False
        self.muzzle_flash.enabled = False
        if self.laser_beam is not None:
            self.laser_beam.enabled = False
        self.body_hitbox.collider = None
        self.body_hitbox.enabled = False
        self.head_hitbox.collider = None
        self.head_hitbox.enabled = False

        if self.actor is not None and "death" in self.actor.getAnimNames():
            self.actor.play("death")
        else:
            fall_pitch = -88.0 if is_headshot else random.choice((86.0, -84.0))
            fall_roll = random.uniform(-22.0, 22.0)
            self.visual_root.animate_rotation(Vec3(fall_pitch, 0.0, fall_roll), duration=0.28)
            self.visual_root.animate_y(0.12, duration=0.28)

    def cleanup(self) -> None:
        if self.actor is not None:
            try:
                self.actor.cleanup()
            except Exception:
                pass
        destroy(self)


def collect_bot_ignore_list(bots: Iterable[EnemyBot]) -> list[Entity]:
    ignored: list[Entity] = []
    for bot in bots:
        ignored.extend(bot.get_ignore_entities())
    return ignored
