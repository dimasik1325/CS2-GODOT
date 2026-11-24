"""
Искусственный интеллект врагов-ботов (FSM: PATROL -> CHASE -> ATTACK -> DEAD).
Поддерживает загрузку 3D-модели assets/models/enemy.glb (со скелетной или процедурной анимацией),
автоматический fallback на составную фигуру из примитивов Ursina,
раздельные хитбоксы головы (Headshot) и корпуса (Bodyshot), проверку прямой видимости (Line-of-Sight)
и тактическое маневрирование со стрельбой очередями.
"""

from __future__ import annotations

import math
import random
from typing import Iterable

from direct.actor.Actor import Actor
from ursina import Entity, Vec3, color, destroy, invoke, lerp, raycast

from src.player import CS2Player
from src.settings import SoundManager, load_safe_model, resource_path


BOT_CALLSIGNS: tuple[str, ...] = (
    "BOT Phoenix",
    "BOT Viper",
    "BOT Sabre",
    "BOT Jackal",
    "BOT Corsair",
    "BOT Nomad",
    "BOT Titan",
    "BOT Raven",
)


class EnemyBot(Entity):
    """Боевой бот-противник с конечным автоматом ИИ и раздельными хитбоксами CS2."""

    MAX_HP: int = 100
    PATROL_SPEED: float = 2.9
    CHASE_SPEED: float = 4.1
    STRAFE_SPEED: float = 2.5
    SIGHT_RANGE: float = 42.0
    ATTACK_RANGE: float = 26.0

    def __init__(
        self,
        bot_name: str,
        spawn_pos: Vec3 | tuple[float, float, float],
        waypoints: list[Vec3],
        sound_mgr: SoundManager,
    ) -> None:
        super().__init__(position=Vec3(*spawn_pos))
        self.bot_name = bot_name
        self.sound_mgr = sound_mgr
        self.waypoints = waypoints if waypoints else [Vec3(*spawn_pos)]

        self.hp: int = self.MAX_HP
        self.state: str = "PATROL"  # PATROL | CHASE | ATTACK | DEAD
        self.actor: Actor | None = None

        # Визуальный узел модели (поворот 180° для стандарта glTF +Z -> Ursina +Z)
        self.visual_root = Entity(parent=self, position=(0.0, 0.0, 0.0))
        self.mesh_node = Entity(parent=self.visual_root, rotation_y=180.0)

        if not self._try_load_glb_enemy():
            self.mesh_node.rotation_y = 0.0
            self._build_primitive_enemy()

        # Вспышка выстрела на стволе оружия бота
        self.muzzle_flash = Entity(
            parent=self.visual_root,
            model="sphere",
            position=(-0.12, 1.14, 0.72),
            scale=0.14,
            color=color.rgb(255, 215, 85),
            unlit=True,
            enabled=False,
        )

        # Раздельные невидимые коллайдеры-хитбоксы для точной регистрации Headshot / Bodyshot
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

        # Компактная полоска здоровья над раненым ботом
        self.hp_bar_bg = Entity(
            parent=self,
            model="quad",
            position=(0.0, 2.06, 0.0),
            scale=(0.62, 0.065),
            color=color.rgba(15, 18, 22, 200),
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
            color=color.rgb(235, 65, 55),
            unlit=True,
        )

        # Внутренние таймеры ИИ
        self._wp_index: int = random.randrange(len(self.waypoints))
        self._reaction_timer: float = 0.38
        self._shoot_cooldown: float = random.uniform(0.3, 0.8)
        self._burst_left: int = 0
        self._strafe_dir: float = random.choice((-1.0, 1.0))
        self._strafe_switch_timer: float = random.uniform(1.1, 2.4)
        self._walk_cycle: float = random.uniform(0.0, 6.28)
        self._alert_memory: float = 0.0

    def _try_load_glb_enemy(self) -> bool:
        """Пытается загрузить assets/models/enemy.glb (со скелетом Actor или как статический меш)."""
        model_np = load_safe_model(
            "assets/models/enemy.glb",
            target_max_extent=1.86,
            align_bottom_zero=True,
        )
        if model_np is None:
            return False

        full_file = resource_path("assets/models/enemy.glb")
        if not model_np.find("**/+Character").isEmpty() and full_file.is_file():
            try:
                candidate = Actor(str(full_file))
                anims = candidate.getAnimNames()
                if anims:
                    candidate.reparentTo(self.mesh_node)
                    self.actor = candidate
                    if "idle" in anims:
                        self.actor.loop("idle")
                    return True
                candidate.cleanup()
            except Exception:
                pass

        Entity(parent=self.mesh_node, model=model_np)
        return True

    def _build_primitive_enemy(self) -> None:
        """Fallback-гуманоид в экипировке T-стороны из примитивов Ursina."""
        jacket = color.rgb(174, 142, 96)
        vest = color.rgb(46, 50, 56)
        pants = color.rgb(66, 76, 62)
        dark = color.rgb(34, 36, 40)
        visor = color.rgb(220, 52, 42)

        Entity(parent=self.mesh_node, model="cube", position=(-0.14, 0.42, 0.0), scale=(0.19, 0.84, 0.22), color=pants)
        Entity(parent=self.mesh_node, model="cube", position=(0.14, 0.42, 0.0), scale=(0.19, 0.84, 0.22), color=pants)
        Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.16, 0.0), scale=(0.50, 0.66, 0.30), color=jacket)
        Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.18, 0.02), scale=(0.44, 0.48, 0.33), color=vest)
        Entity(parent=self.mesh_node, model="cube", position=(-0.32, 1.18, 0.14), scale=(0.15, 0.52, 0.18), rotation_x=35, color=jacket)
        Entity(parent=self.mesh_node, model="cube", position=(0.32, 1.18, 0.14), scale=(0.15, 0.52, 0.18), rotation_x=35, color=jacket)
        Entity(parent=self.mesh_node, model="cube", position=(-0.12, 1.12, 0.42), scale=(0.08, 0.12, 0.56), color=dark)
        Entity(parent=self.mesh_node, model="sphere", position=(0.0, 1.68, 0.0), scale=(0.35, 0.37, 0.35), color=dark)
        Entity(parent=self.mesh_node, model="cube", position=(0.0, 1.70, 0.15), scale=(0.25, 0.08, 0.06), color=visor)

    def get_ignore_entities(self) -> tuple[Entity, ...]:
        return (self, self.body_hitbox, self.head_hitbox)

    def _has_line_of_sight(self, player: CS2Player, ignore_all_bots: list[Entity]) -> bool:
        """Проверяет прямую видимость от глаз бота до камеры игрока (стены и ящики перекрывают обзор)."""
        eye_pos = self.world_position + Vec3(0.0, 1.58, 0.0)
        target_pos = player.world_position + Vec3(0.0, player.height * 0.88, 0.0)
        to_player = target_pos - eye_pos
        dist = to_player.length()
        if dist > self.SIGHT_RANGE:
            return False
        if dist < 0.6:
            return True

        direction = to_player.normalized()
        # Проверка угла обзора (если бот не в боевой тревоге, он видит сектор ~150° спереди или слышит вблизи)
        if self.state == "PATROL" and self._alert_memory <= 0.0 and dist > 11.0:
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

    def _move_with_collision(self, move_dir: Vec3, speed: float, dt: float, ignore_list: list[Entity]) -> bool:
        """Перемещает бота по горизонтали с проверкой стен, ящиков и высоты пола."""
        flat_dir = Vec3(move_dir.x, 0.0, move_dir.z)
        if flat_dir.length() < 1e-4:
            return False
        flat_dir = flat_dir.normalized()

        # Проверка препятствия на уровне колена и груди
        low_hit = raycast(self.world_position + Vec3(0, 0.55, 0), flat_dir, distance=0.75, ignore=ignore_list)
        high_hit = raycast(self.world_position + Vec3(0, 1.35, 0), flat_dir, distance=0.75, ignore=ignore_list)
        if low_hit.hit or high_hit.hit:
            return False

        self.position += flat_dir * (speed * dt)

        # Привязка к уровню пола/платформы
        ground_ray = raycast(
            self.world_position + Vec3(0, 1.6, 0),
            Vec3(0, -1, 0),
            distance=4.0,
            ignore=ignore_list,
        )
        if ground_ray.hit and ground_ray.world_point.y - self.y < 0.65:
            self.y = lerp(self.y, ground_ray.world_point.y, min(1.0, dt * 14.0))

        # Лёгкое покачивание корпуса при шаге
        self._walk_cycle += dt * speed * 2.6
        self.visual_root.y = abs(math.sin(self._walk_cycle)) * 0.045
        return True

    def _face_point_smooth(self, target_pt: Vec3, dt: float, turn_speed: float = 9.0) -> None:
        dx = target_pt.x - self.x
        dz = target_pt.z - self.z
        if abs(dx) + abs(dz) < 1e-4:
            return
        desired_yaw = math.degrees(math.atan2(dx, dz))
        # Кратчайшая дуга поворота
        delta = (desired_yaw - self.rotation_y + 180.0) % 360.0 - 180.0
        self.rotation_y += delta * min(1.0, dt * turn_speed)

    def update_ai(
        self,
        dt: float,
        player: CS2Player,
        ignore_all_bots: list[Entity],
    ) -> None:
        """Главный шаг ИИ бота за кадр."""
        if self.state == "DEAD" or not self.enabled:
            return

        if not player.is_alive:
            self.state = "PATROL"
            self.visual_root.y = 0.0
            return

        if self._alert_memory > 0.0:
            self._alert_memory = max(0.0, self._alert_memory - dt)

        can_see = self._has_line_of_sight(player, ignore_all_bots)
        dist_to_player = (player.world_position - self.world_position).length()

        if can_see:
            if self.state == "PATROL":
                # Небольшая человеческая задержка реакции при первом обнаружении
                self._reaction_timer = random.uniform(0.26, 0.45)
            self._alert_memory = 4.5
            self.state = "ATTACK" if dist_to_player <= self.ATTACK_RANGE else "CHASE"
        elif self._alert_memory > 0.0:
            self.state = "CHASE"
        else:
            self.state = "PATROL"

        # ── СОСТОЯНИЕ 1: ПАТРУЛИРОВАНИЕ ТОЧЕК КАРТЫ ──
        if self.state == "PATROL":
            target_wp = self.waypoints[self._wp_index]
            to_wp = Vec3(target_wp.x - self.x, 0.0, target_wp.z - self.z)
            if to_wp.length() < 1.35:
                self._wp_index = (self._wp_index + random.choice((1, 2))) % len(self.waypoints)
                target_wp = self.waypoints[self._wp_index]
                to_wp = Vec3(target_wp.x - self.x, 0.0, target_wp.z - self.z)

            self._face_point_smooth(target_wp, dt, turn_speed=5.5)
            moved = self._move_with_collision(to_wp, self.PATROL_SPEED, dt, ignore_all_bots)
            if not moved:
                # Если упёрся в ящик/стену — выбирает следующий вейпоинт
                self._wp_index = (self._wp_index + 1) % len(self.waypoints)

        # ── СОСТОЯНИЕ 2: ПРЕСЛЕДОВАНИЕ ИГРОКА ──
        elif self.state == "CHASE":
            self._face_point_smooth(player.world_position, dt, turn_speed=8.5)
            to_plr = player.world_position - self.world_position
            moved = self._move_with_collision(to_plr, self.CHASE_SPEED, dt, ignore_all_bots)
            if not moved:
                # Обход препятствия боковым стрейфом
                side = Vec3(self.right.x * self._strafe_dir, 0.0, self.right.z * self._strafe_dir)
                self._move_with_collision(side, self.CHASE_SPEED * 0.85, dt, ignore_all_bots)

        # ── СОСТОЯНИЕ 3: ОГНЕВОЙ КОНТАКТ И СТРЕЙФ ──
        elif self.state == "ATTACK":
            self._face_point_smooth(player.world_position, dt, turn_speed=11.0)

            # Тактический стрейф влево-вправо, как у ботов CS2
            self._strafe_switch_timer -= dt
            if self._strafe_switch_timer <= 0.0:
                self._strafe_dir *= -1.0
                self._strafe_switch_timer = random.uniform(1.0, 2.2)

            strafe_vec = Vec3(self.right.x * self._strafe_dir, 0.0, self.right.z * self._strafe_dir)
            if dist_to_player > 16.0:
                strafe_vec += (player.world_position - self.world_position).normalized() * 0.6
            elif dist_to_player < 7.0:
                strafe_vec -= (player.world_position - self.world_position).normalized() * 0.5
            self._move_with_collision(strafe_vec, self.STRAFE_SPEED, dt, ignore_all_bots)

            if self._reaction_timer > 0.0:
                self._reaction_timer -= dt
                return

            self._shoot_cooldown -= dt
            if self._shoot_cooldown <= 0.0 and can_see:
                self._fire_at_player(player, dist_to_player)

    def _fire_at_player(self, player: CS2Player, distance: float) -> None:
        """Производит один выстрел из очереди по игроку с реалистичным разбросом."""
        if self._burst_left <= 0:
            self._burst_left = random.randint(2, 4)

        self._burst_left -= 1
        self._shoot_cooldown = 0.14 if self._burst_left > 0 else random.uniform(0.65, 1.15)

        # Вспышка выстрела и звук с затуханием от дистанции
        self.muzzle_flash.enabled = True
        invoke(setattr, self.muzzle_flash, "enabled", False, delay=0.05)

        attenuation = max(0.18, min(0.75, 10.0 / max(distance, 4.0)))
        self.sound_mgr.play_sfx("ak47_shoot", volume=attenuation, pitch=random.uniform(0.93, 1.04))

        # Расчёт вероятности попадания (дальше и в приседе у игрока — попасть сложнее)
        crouch_factor = 0.68 if player.is_crouching else 1.0
        move_evasion = 0.82 if player.is_sprinting else 1.0
        base_hit_prob = max(0.14, 0.56 - distance * 0.011) * crouch_factor * move_evasion

        if random.random() < base_hit_prob:
            dmg = random.randint(11, 18)
            player.take_damage(dmg)

    def take_damage(self, amount: int, is_headshot: bool = False) -> bool:
        """
        Применяет урон к боту. Возвращает True, если этот выстрел уничтожил бота.
        """
        if self.state == "DEAD":
            return False

        self.hp = max(0, self.hp - int(amount))
        self._alert_memory = 6.0  # Бот мгновенно разворачивается на выстрел

        # Обновляем полоску HP над ботом
        self.hp_bar_bg.enabled = self.hp > 0
        ratio = max(0.0, self.hp / float(self.MAX_HP))
        self.hp_bar_fill.scale_x = max(0.01, 0.96 * ratio)

        # Короткая подсветка попадания
        self.visual_root.y = 0.06
        invoke(setattr, self.visual_root, "y", 0.0, delay=0.06)

        if self.hp <= 0:
            self._die(is_headshot=is_headshot)
            return True
        return False

    def _die(self, is_headshot: bool = False) -> None:
        """Переводит бота в состояние DEAD, отключает коллайдеры и проигрывает падение."""
        self.state = "DEAD"
        self.hp_bar_bg.enabled = False
        self.muzzle_flash.enabled = False
        self.body_hitbox.collider = None
        self.body_hitbox.enabled = False
        self.head_hitbox.collider = None
        self.head_hitbox.enabled = False

        if self.actor is not None and "death" in self.actor.getAnimNames():
            self.actor.play("death")
        else:
            fall_angle = -88.0 if is_headshot else 86.0
            self.visual_root.animate_rotation_x(fall_angle, duration=0.28)
            self.visual_root.animate_y(0.12, duration=0.28)

    def cleanup(self) -> None:
        """Полное удаление сущности бота при перезапуске раунда."""
        if self.actor is not None:
            try:
                self.actor.cleanup()
            except Exception:
                pass
        destroy(self)


def collect_bot_ignore_list(bots: Iterable[EnemyBot]) -> list[Entity]:
    """Собирает единый список всех сущностей и хитбоксов ботов для проверки Line-of-Sight."""
    ignored: list[Entity] = []
    for bot in bots:
        ignored.extend(bot.get_ignore_entities())
    return ignored
