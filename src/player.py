"""
Контроллер игрока от первого лица в стиле Counter-Strike 2.
Реализует передвижение WASD, бег (Shift), плавный присед (Ctrl), прыжок (Space),
отдачу камеры с возвратом, систему здоровья и брони Kevlar, а также звуки шагов.
"""

from __future__ import annotations

import random
from typing import Callable

from ursina import Vec2, Vec3, camera, clamp, curve, held_keys, invoke, lerp, mouse, raycast, time
from ursina.prefabs.first_person_controller import FirstPersonController

from src.settings import GameSettings, SoundManager


class CS2Player(FirstPersonController):
    """Игрок от первого лица с физикой CS2, бронёй, отдачей и динамикой разброса."""

    STAND_HEIGHT: float = 1.80
    CROUCH_HEIGHT: float = 1.08
    WALK_SPEED: float = 5.8
    SPRINT_SPEED: float = 8.5
    CROUCH_SPEED: float = 3.0

    def __init__(
        self,
        settings: GameSettings,
        sound_mgr: SoundManager,
        on_death_callback: Callable[[], None] | None = None,
        on_hurt_callback: Callable[[], None] | None = None,
        position: tuple[float, float, float] = (0.0, 0.5, -20.0),
    ) -> None:
        super().__init__(
            position=position,
            speed=self.WALK_SPEED,
            height=self.STAND_HEIGHT,
            jump_height=1.65,
            jump_up_duration=0.42,
            fall_after=0.32,
            gravity=1.0,
        )
        # Скрываем стандартный розовый ромб FirstPersonController — у нас свой прицел CS2
        if hasattr(self, "cursor") and self.cursor is not None:
            self.cursor.enabled = False
            self.cursor.visible = False

        # Настраиваем ближнюю плоскость отсечения камеры, чтобы оружие в руках не резалось стенами
        if hasattr(camera, "lens") and camera.lens is not None:
            camera.clip_plane_near = 0.05
        camera.fov = settings.fov

        self.settings = settings
        self.sound_mgr = sound_mgr
        self.on_death_callback = on_death_callback
        self.on_hurt_callback = on_hurt_callback

        self.apply_sensitivity(settings.mouse_sensitivity)

        # Боевые параметры CS2
        self.max_hp: int = 100
        self.hp: int = 100
        self.max_armor: int = 100
        self.armor: int = 100
        self.is_alive: bool = True

        # Состояния движения и оружия
        self.is_crouching: bool = False
        self.is_sprinting: bool = False
        self.is_moving_horizontally: bool = False
        self.weapon_mobility: float = 1.0
        self.horizontal_speed_ratio: float = 0.0

        # Накопленная отдача для плавного возврата прицела
        self._recoil_pitch_accum: float = 0.0
        self._flinch_pitch: float = 0.0
        self._footstep_timer: float = 0.0

    def apply_sensitivity(self, sensitivity: float) -> None:
        """Обновляет чувствительность мыши по обеим осям."""
        sens = max(5.0, min(140.0, float(sensitivity)))
        self.mouse_sensitivity = Vec2(sens, sens)

    def on_enable(self) -> None:
        super().on_enable()
        if hasattr(self, "cursor") and self.cursor is not None:
            self.cursor.enabled = False
            self.cursor.visible = False

    def jump(self) -> None:
        """Безопасный прыжок с защитой от деления на ноль при малом time.dt."""
        if not self.grounded or self.is_crouching or not self.is_alive:
            return
        self.grounded = False
        dt_safe = max(float(time.dt), 1.0 / 120.0)
        self.animate_y(
            self.y + self.jump_height,
            self.jump_up_duration,
            resolution=max(10, int(1.0 / dt_safe)),
            curve=curve.out_expo,
        )
        self.sound_mgr.play_sfx("footstep", volume=0.55, pitch=0.88)
        invoke(self.start_fall, delay=self.fall_after)

    def land(self) -> None:
        was_airborne = self.air_time > 0.12
        super().land()
        if was_airborne and self.is_alive:
            self.sound_mgr.play_sfx("footstep", volume=0.70, pitch=0.80)

    def input(self, key: str) -> None:
        if not self.enabled or not self.is_alive:
            return
        if key == "space":
            self.jump()

    def _can_stand_up(self) -> bool:
        """Проверяет лучом вверх, не мешает ли низкое препятствие встать из приседа."""
        overhead = raycast(
            self.world_position + Vec3(0.0, self.CROUCH_HEIGHT, 0.0),
            Vec3(0.0, 1.0, 0.0),
            distance=(self.STAND_HEIGHT - self.CROUCH_HEIGHT + 0.18),
            ignore=self.ignore_list,
        )
        return not overhead.hit

    def update(self) -> None:
        if not self.enabled:
            return

        dt = min(float(time.dt), 0.05)
        if not self.is_alive:
            return

        # 1. Обработка приседа (Ctrl) и бега (Shift)
        want_crouch = bool(held_keys["left control"] or held_keys["right control"] or held_keys["c"])
        if want_crouch:
            self.is_crouching = True
        elif self.is_crouching and self._can_stand_up():
            self.is_crouching = False

        target_height = self.CROUCH_HEIGHT if self.is_crouching else self.STAND_HEIGHT
        self.height = lerp(self.height, target_height, min(1.0, dt * 13.0))
        self.camera_pivot.y = self.height

        want_sprint = bool(held_keys["left shift"]) and not self.is_crouching and held_keys["w"] > 0
        self.is_sprinting = want_sprint

        if self.is_crouching:
            base_spd = self.CROUCH_SPEED
        elif self.is_sprinting:
            base_spd = self.SPRINT_SPEED
        else:
            base_spd = self.WALK_SPEED

        self.speed = base_spd * self.weapon_mobility

        # 2. Базовая физика и обзор мыши из FirstPersonController
        prev_pos = Vec3(self.position)
        super().update()

        # 3. Плавная компенсация отдачи и вздрагивания при попадании (aim punch)
        if self._recoil_pitch_accum > 0.001 and not mouse.left:
            recover = min(self._recoil_pitch_accum, dt * 14.0)
            self._recoil_pitch_accum -= recover
            self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x + recover, -89.0, 89.0)

        if abs(self._flinch_pitch) > 0.01:
            self._flinch_pitch = lerp(self._flinch_pitch, 0.0, min(1.0, dt * 12.0))

        # 4. Расчёт фактической горизонтальной скорости и звуков шагов
        horiz_delta = Vec3(self.x - prev_pos.x, 0.0, self.z - prev_pos.z)
        moved_dist = horiz_delta.length()
        inst_speed = moved_dist / max(dt, 1e-4)
        self.is_moving_horizontally = inst_speed > 0.45
        self.horizontal_speed_ratio = clamp(inst_speed / self.SPRINT_SPEED, 0.0, 1.25)

        if self.grounded and self.is_moving_horizontally and not self.is_crouching:
            self._footstep_timer -= dt
            if self._footstep_timer <= 0.0:
                step_interval = 0.31 if self.is_sprinting else 0.44
                self._footstep_timer = step_interval
                self.sound_mgr.play_sfx(
                    "footstep",
                    volume=0.58 if self.is_sprinting else 0.38,
                    pitch=random.uniform(0.92, 1.08),
                )
        else:
            self._footstep_timer = min(self._footstep_timer, 0.12)

    def apply_recoil(self, pitch_kick: float, yaw_kick: float) -> None:
        """Подбрасывает камеру вверх (отрицательный rotation_x в Ursina) и уводит по горизонтали."""
        self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x - pitch_kick, -89.0, 89.0)
        self.rotation_y += yaw_kick
        self._recoil_pitch_accum = min(16.0, self._recoil_pitch_accum + pitch_kick * 0.72)

    def get_movement_spread_penalty(self) -> float:
        """
        Возвращает штраф к разбросу пуль в зависимости от стойки и скорости (как в CS2):
        - В прыжке: высокий разброс
        - На бегу (Shift): повышенный разброс
        - При обычной ходьбе: умеренный разброс
        - В приседе (Ctrl): бонус точности (уменьшение разброса)
        """
        if not self.grounded:
            return 0.075
        if self.is_sprinting and self.is_moving_horizontally:
            return 0.038
        if self.is_moving_horizontally:
            return 0.018 if not self.is_crouching else 0.006
        if self.is_crouching:
            return -0.003
        return 0.0

    def take_damage(self, raw_damage: int) -> int:
        """
        Наносит урон игроку с учётом бронежилета Kevlar (поглощает 45% урона).
        Возвращает текущий остаток HP.
        """
        if not self.is_alive:
            return 0

        dmg = max(1, int(raw_damage))
        if self.armor > 0:
            absorbed = int(dmg * 0.45)
            armor_cost = max(1, int(dmg * 0.30))
            actual_armor_used = min(self.armor, armor_cost)
            if actual_armor_used < armor_cost:
                absorbed = int(absorbed * (actual_armor_used / max(1, armor_cost)))
            self.armor = max(0, self.armor - actual_armor_used)
            hp_loss = max(1, dmg - absorbed)
        else:
            hp_loss = dmg

        self.hp = max(0, self.hp - hp_loss)
        self.sound_mgr.play_sfx("player_hurt", volume=0.80, pitch=random.uniform(0.95, 1.05))

        # Лёгкий aim-punch при ранении
        self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x - 1.1, -89.0, 89.0)
        self._flinch_pitch = 1.1

        if self.on_hurt_callback is not None:
            self.on_hurt_callback()

        if self.hp <= 0:
            self.is_alive = False
            if self.on_death_callback is not None:
                self.on_death_callback()

        return self.hp

    def respawn(self, spawn_pos: Vec3 | tuple[float, float, float], yaw: float = 0.0) -> None:
        """Полный сброс игрока в начале нового раунда."""
        self.hp = self.max_hp
        self.armor = self.max_armor
        self.is_alive = True
        self.is_crouching = False
        self.is_sprinting = False
        self.height = self.STAND_HEIGHT
        self.camera_pivot.y = self.STAND_HEIGHT
        self.position = Vec3(*spawn_pos)
        self.rotation = Vec3(0.0, yaw, 0.0)
        self.camera_pivot.rotation = Vec3(0.0, 0.0, 0.0)
        self._recoil_pitch_accum = 0.0
        self._flinch_pitch = 0.0
        self.air_time = 0.0
        self.grounded = True
