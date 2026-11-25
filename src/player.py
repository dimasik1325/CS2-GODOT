"""
Реалистичный тактический контроллер игрока от первого лица (CS2 Tactical Edition):
- Передвижение WASD, спринт (Shift), присед (Ctrl), тактический подкат (Shift + Ctrl в движении!)
- Выглядывание из-за углов / Leaning влево и вправо (клавиши Q и E с проверкой стен!)
- Плавное прицеливание и двукратный снайперский зум (динамический FOV + задержка дыхания на Shift)
- 3D тактический подствольный фонарь SpotLight (клавиша T)
- Боевой стимулятор / аптечка Stimshot +35 HP (клавиша X)
- Бронежилет Kevlar + Шлем (Helmet dink protection) + набор сапёра (Defuse Kit)
- Реалистичная инерция камеры: крен при стрейфе, пружина приземления, тряска от взрывов и отдача
"""

from __future__ import annotations

import math
import random
from typing import Callable

from ursina import Entity, SpotLight, Vec2, Vec3, camera, clamp, curve, held_keys, invoke, lerp, mouse, raycast, time
from ursina.prefabs.first_person_controller import FirstPersonController

from src.settings import GameSettings, SoundManager, rgb32


class CS2Player(FirstPersonController):
    """Игрок от первого лица с расширенной тактической физикой, бронёй, подкатами и наклонами."""

    STAND_HEIGHT: float = 1.80
    CROUCH_HEIGHT: float = 1.06
    SLIDE_HEIGHT: float = 0.84
    WALK_SPEED: float = 5.9
    SPRINT_SPEED: float = 8.7
    CROUCH_SPEED: float = 3.1
    SLIDE_INITIAL_SPEED: float = 12.2

    def __init__(
        self,
        settings: GameSettings,
        sound_mgr: SoundManager,
        on_death_callback: Callable[[], None] | None = None,
        on_hurt_callback: Callable[[], None] | None = None,
        position: tuple[float, float, float] = (0.0, 0.5, -26.5),
    ) -> None:
        super().__init__(
            position=position,
            speed=self.WALK_SPEED,
            height=self.STAND_HEIGHT,
            jump_height=1.68,
            jump_up_duration=0.42,
            fall_after=0.32,
            gravity=1.0,
        )
        if hasattr(self, "cursor") and self.cursor is not None:
            self.cursor.enabled = False
            self.cursor.visible = False

        if hasattr(camera, "lens") and camera.lens is not None:
            camera.clip_plane_near = 0.05
        camera.fov = settings.fov

        self.settings = settings
        self.sound_mgr = sound_mgr
        self.on_death_callback = on_death_callback
        self.on_hurt_callback = on_hurt_callback

        self.apply_sensitivity(settings.mouse_sensitivity)

        # ── БОЕВЫЕ ХАРАКТЕРИСТИКИ И ЭКИПИРОВКА ──
        self.max_hp: int = 100
        self.hp: int = 100
        self.max_armor: int = 100
        self.armor: int = 100
        self.has_helmet: bool = True
        self.has_defuse_kit: bool = True
        self.stimshots: int = 1
        self.is_alive: bool = True

        # ── СОСТОЯНИЯ ДВИЖЕНИЯ, ВЫНОСЛИВОСТИ И ТАКТИКИ ──
        self.stamina: float = 100.0
        self.is_crouching: bool = False
        self.is_sprinting: bool = False
        self.is_sliding: bool = False
        self.is_moving_horizontally: bool = False
        self.holding_breath: bool = False
        self.lean_amount: float = 0.0        # -1.0 (влево Q) .. +1.0 (вправо E)
        self.target_fov: float = settings.fov
        self.zoom_fov_override: float | None = None
        self.weapon_mobility: float = 1.0
        self.horizontal_speed_ratio: float = 0.0

        # Внутренние таймеры подката, пружины приземления и тряски экрана
        self._slide_timer: float = 0.0
        self._slide_cooldown: float = 0.0
        self._slide_dir: Vec3 = Vec3(0.0, 0.0, 0.0)
        self._was_crouch_held: bool = False
        self._land_dip: float = 0.0
        self._shake_trauma: float = 0.0
        self._recoil_pitch_accum: float = 0.0
        self._flinch_pitch: float = 0.0
        self._footstep_timer: float = 0.0

        # ── 3D ПОДСТВОЛЬНЫЙ ТАКТИЧЕСКИЙ ФОНАРЬ (КЛАВИША T) ──
        self.flashlight_on: bool = False
        self.flashlight = SpotLight(
            parent=self.camera_pivot,
            position=(0.12, -0.06, 0.15),
            rotation=(0.0, 0.0, 0.0),
            color=rgb32(0, 0, 0),
        )
        try:
            lens = self.flashlight._light.getLens()
            lens.setFov(44.0)
            self.flashlight._light.setAttenuation((1.0, 0.035, 0.008))
        except Exception:
            pass

    def apply_sensitivity(self, sensitivity: float, zoom_scale: float = 1.0) -> None:
        sens = max(5.0, min(140.0, float(sensitivity))) * clamp(zoom_scale, 0.22, 1.0)
        self.mouse_sensitivity = Vec2(sens, sens)

    def toggle_flashlight(self) -> bool:
        self.flashlight_on = not self.flashlight_on
        self.flashlight.color = rgb32(235, 245, 255) if self.flashlight_on else rgb32(0, 0, 0)
        self.sound_mgr.play_sfx("empty_click", volume=0.55, pitch=1.35 if self.flashlight_on else 0.95)
        return self.flashlight_on

    def use_stimshot(self) -> bool:
        """Использует боевой инъектор здоровья (+35 HP, клавиша X)."""
        if not self.is_alive or self.stimshots <= 0 or self.hp >= self.max_hp:
            return False
        self.stimshots -= 1
        self.hp = min(self.max_hp, self.hp + 35)
        self.stamina = 100.0
        self.sound_mgr.play_sfx("buy_item", volume=0.80, pitch=1.18)
        return True

    def add_screen_shake(self, intensity: float) -> None:
        """Добавляет физическую тряску камеры от близкого взрыва гранаты, бочки или C4."""
        self._shake_trauma = min(1.0, self._shake_trauma + clamp(intensity, 0.0, 1.0))

    def on_enable(self) -> None:
        super().on_enable()
        if hasattr(self, "cursor") and self.cursor is not None:
            self.cursor.enabled = False
            self.cursor.visible = False

    def jump(self) -> None:
        if not self.grounded or not self.is_alive:
            return
        if self.is_sliding:
            self.is_sliding = False
            self._slide_timer = 0.0
        elif self.is_crouching:
            return

        self.grounded = False
        self.stamina = max(0.0, self.stamina - 12.0)
        dt_safe = max(float(time.dt), 1.0 / 120.0)
        self.animate_y(
            self.y + self.jump_height,
            self.jump_up_duration,
            resolution=max(10, int(1.0 / dt_safe)),
            curve=curve.out_expo,
        )
        self.sound_mgr.play_sfx("footstep", volume=0.58, pitch=0.88)
        invoke(self.start_fall, delay=self.fall_after)

    def land(self) -> None:
        airborne_t = float(self.air_time)
        super().land()
        if airborne_t > 0.12 and self.is_alive:
            self._land_dip = min(0.24, airborne_t * 0.36)
            self.sound_mgr.play_sfx("footstep", volume=0.72, pitch=0.78)

    def input(self, key: str) -> None:
        if not self.enabled or not self.is_alive:
            return
        if key == "space":
            self.jump()

    def _can_stand_up(self) -> bool:
        overhead = raycast(
            self.world_position + Vec3(0.0, self.CROUCH_HEIGHT, 0.0),
            Vec3(0.0, 1.0, 0.0),
            distance=(self.STAND_HEIGHT - self.CROUCH_HEIGHT + 0.18),
            ignore=self.ignore_list,
        )
        return not overhead.hit

    def _compute_safe_lean_target(self) -> float:
        """Проверяет боковым лучом, чтобы при наклоне Q/E камера не проходила сквозь стену."""
        raw_lean = float(held_keys["e"] - held_keys["q"])
        if abs(raw_lean) < 0.01 or self.is_sprinting or self.is_sliding:
            return 0.0
        check_dir = self.right * (1.0 if raw_lean > 0 else -1.0)
        side_hit = raycast(
            self.world_position + Vec3(0.0, self.height * 0.85, 0.0),
            check_dir,
            distance=0.62,
            ignore=self.ignore_list,
        )
        if side_hit.hit:
            return raw_lean * max(0.0, (side_hit.distance - 0.25) / 0.37)
        return raw_lean

    def update(self) -> None:
        if not self.enabled:
            return

        dt = min(float(time.dt), 0.05)
        if not self.is_alive:
            return

        if self._slide_cooldown > 0.0:
            self._slide_cooldown = max(0.0, self._slide_cooldown - dt)

        # 1. Обработка приседа (Ctrl), спринта (Shift) и тактического подката (Shift + Ctrl!)
        want_crouch = bool(held_keys["left control"] or held_keys["right control"] or held_keys["c"])
        want_sprint_key = bool(held_keys["left shift"])

        # Старт подката при нажатии Ctrl во время спринта вперёд
        if (
            want_crouch
            and not self._was_crouch_held
            and self.is_sprinting
            and self.grounded
            and self._slide_cooldown <= 0.0
            and self.stamina >= 18.0
        ):
            self.is_sliding = True
            self._slide_timer = 0.62
            self._slide_cooldown = 1.15
            self.stamina = max(0.0, self.stamina - 20.0)
            self._slide_dir = Vec3(self.forward.x, 0.0, self.forward.z).normalized()
            self.sound_mgr.play_sfx("footstep", volume=0.75, pitch=0.68)
        self._was_crouch_held = want_crouch

        if self.is_sliding:
            self._slide_timer -= dt
            if self._slide_timer <= 0.0 or not want_crouch:
                self.is_sliding = False

        if want_crouch or self.is_sliding:
            self.is_crouching = True
        elif self.is_crouching and self._can_stand_up():
            self.is_crouching = False

        # Задержка дыхания в снайперском прицеле на Shift
        if self.zoom_fov_override is not None and want_sprint_key and self.stamina > 5.0:
            self.holding_breath = True
            self.stamina = max(0.0, self.stamina - dt * 24.0)
        else:
            self.holding_breath = False

        can_sprint = (
            want_sprint_key
            and not self.is_crouching
            and not self.is_sliding
            and self.zoom_fov_override is None
            and held_keys["w"] > 0
            and self.stamina > 6.0
        )
        self.is_sprinting = can_sprint
        if self.is_sprinting and self.is_moving_horizontally:
            self.stamina = max(0.0, self.stamina - dt * 16.0)
        elif not self.holding_breath:
            self.stamina = min(100.0, self.stamina + dt * 22.0)

        # Скорость и высота глаз
        if self.is_sliding:
            slide_factor = clamp(self._slide_timer / 0.62, 0.25, 1.0)
            base_spd = lerp(self.CROUCH_SPEED, self.SLIDE_INITIAL_SPEED, slide_factor)
            target_height = self.SLIDE_HEIGHT
        elif self.is_crouching:
            base_spd = self.CROUCH_SPEED
            target_height = self.CROUCH_HEIGHT
        elif self.is_sprinting:
            base_spd = self.SPRINT_SPEED
            target_height = self.STAND_HEIGHT
        else:
            base_spd = self.WALK_SPEED
            target_height = self.STAND_HEIGHT

        zoom_slowdown = 0.68 if self.zoom_fov_override is not None else 1.0
        self.speed = base_spd * self.weapon_mobility * zoom_slowdown

        # Пружина приземления и высота камеры
        self._land_dip = lerp(self._land_dip, 0.0, min(1.0, dt * 11.0))
        self.height = lerp(self.height, target_height, min(1.0, dt * 14.0))

        # 2. Базовое обновление FirstPersonController + импульс подката
        prev_pos = Vec3(self.position)
        super().update()

        if self.is_sliding and self._slide_dir.length() > 0.1:
            slide_hit = raycast(
                self.world_position + Vec3(0.0, 0.45, 0.0),
                self._slide_dir,
                distance=0.85,
                ignore=self.ignore_list,
            )
            if not slide_hit.hit:
                self.position += self._slide_dir * (self.speed * 0.42 * dt)
            else:
                self.is_sliding = False

        # 3. Выглядывание из-за угла (Q / E), крен стрейфа и тряска от взрывов
        target_lean = self._compute_safe_lean_target()
        self.lean_amount = lerp(self.lean_amount, target_lean, min(1.0, dt * 12.0))

        strafe_input = float(held_keys["d"] - held_keys["a"])
        strafe_roll = -strafe_input * 1.45
        slide_roll = -5.5 if self.is_sliding else 0.0
        lean_roll = -self.lean_amount * 9.5

        shake_x = 0.0
        shake_y = 0.0
        shake_roll = 0.0
        if self._shake_trauma > 0.001:
            self._shake_trauma = max(0.0, self._shake_trauma - dt * 1.85)
            mag = self._shake_trauma * self._shake_trauma
            shake_x = random.uniform(-0.08, 0.08) * mag
            shake_y = random.uniform(-0.08, 0.08) * mag
            shake_roll = random.uniform(-4.5, 4.5) * mag

        self.camera_pivot.x = self.lean_amount * 0.36 + shake_x
        self.camera_pivot.y = max(0.45, self.height - self._land_dip + shake_y)
        camera.rotation_z = lerp(camera.rotation_z, strafe_roll + slide_roll + lean_roll + shake_roll, min(1.0, dt * 14.0))

        # 4. Плавная интерполяция FOV (зум прицела / спринт / подкат)
        if self.zoom_fov_override is not None:
            desired_fov = self.zoom_fov_override
            zoom_sens = clamp(self.zoom_fov_override / max(self.settings.fov, 60.0), 0.22, 1.0)
            self.apply_sensitivity(self.settings.mouse_sensitivity, zoom_scale=zoom_sens)
        else:
            sprint_boost = 6.5 if (self.is_sprinting and self.is_moving_horizontally) else (8.5 if self.is_sliding else 0.0)
            desired_fov = float(self.settings.fov) + sprint_boost
            self.apply_sensitivity(self.settings.mouse_sensitivity, zoom_scale=1.0)
        camera.fov = lerp(camera.fov, desired_fov, min(1.0, dt * 14.0))

        # 5. Компенсация отдачи
        if self._recoil_pitch_accum > 0.001 and not mouse.left:
            recover = min(self._recoil_pitch_accum, dt * 14.0)
            self._recoil_pitch_accum -= recover
            self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x + recover, -89.0, 89.0)

        if abs(self._flinch_pitch) > 0.01:
            self._flinch_pitch = lerp(self._flinch_pitch, 0.0, min(1.0, dt * 12.0))

        # 6. Горизонтальная скорость и звуки шагов
        horiz_delta = Vec3(self.x - prev_pos.x, 0.0, self.z - prev_pos.z)
        inst_speed = horiz_delta.length() / max(dt, 1e-4)
        self.is_moving_horizontally = inst_speed > 0.45
        self.horizontal_speed_ratio = clamp(inst_speed / self.SPRINT_SPEED, 0.0, 1.35)

        if self.grounded and self.is_moving_horizontally and not self.is_crouching and not self.is_sliding:
            self._footstep_timer -= dt
            if self._footstep_timer <= 0.0:
                self._footstep_timer = 0.30 if self.is_sprinting else 0.43
                self.sound_mgr.play_sfx(
                    "footstep",
                    volume=0.58 if self.is_sprinting else 0.36,
                    pitch=random.uniform(0.92, 1.08),
                )
        else:
            self._footstep_timer = min(self._footstep_timer, 0.12)

    def apply_recoil(self, pitch_kick: float, yaw_kick: float) -> None:
        self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x - pitch_kick, -89.0, 89.0)
        self.rotation_y += yaw_kick
        self._recoil_pitch_accum = min(17.0, self._recoil_pitch_accum + pitch_kick * 0.72)

    def get_movement_spread_penalty(self) -> float:
        if not self.grounded:
            return 0.075
        if self.is_sliding:
            return 0.022
        if self.is_sprinting and self.is_moving_horizontally:
            return 0.038
        if self.is_moving_horizontally:
            return 0.018 if not self.is_crouching else 0.005
        if self.holding_breath:
            return -0.006
        if self.is_crouching:
            return -0.0035
        return 0.0

    def take_damage(self, raw_damage: int, is_headshot: bool = False) -> int:
        """Наносит урон с учётом бронежилета Kevlar и защитного шлема (Helmet)."""
        if not self.is_alive:
            return 0

        dmg = max(1, int(raw_damage))
        if is_headshot and self.has_helmet and self.armor > 0:
            dmg = int(dmg * 0.62)
            self.sound_mgr.play_sfx("headshot", volume=0.65, pitch=1.12)

        if self.armor > 0:
            absorbed = int(dmg * 0.46)
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

        self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x - 1.1, -89.0, 89.0)
        self._flinch_pitch = 1.1

        if self.on_hurt_callback is not None:
            self.on_hurt_callback()

        if self.hp <= 0:
            self.is_alive = False
            self.zoom_fov_override = None
            if self.on_death_callback is not None:
                self.on_death_callback()

        return self.hp

    def respawn(self, spawn_pos: Vec3 | tuple[float, float, float], yaw: float = 0.0) -> None:
        self.hp = self.max_hp
        self.armor = max(self.armor, 100)
        self.has_helmet = True
        self.stimshots = max(self.stimshots, 1)
        self.stamina = 100.0
        self.is_alive = True
        self.is_crouching = False
        self.is_sprinting = False
        self.is_sliding = False
        self.holding_breath = False
        self.zoom_fov_override = None
        self.lean_amount = 0.0
        self.height = self.STAND_HEIGHT
        self.camera_pivot.position = Vec3(0.0, self.STAND_HEIGHT, 0.0)
        self.position = Vec3(*spawn_pos)
        self.rotation = Vec3(0.0, yaw, 0.0)
        self.camera_pivot.rotation = Vec3(0.0, 0.0, 0.0)
        camera.rotation_z = 0.0
        self._recoil_pitch_accum = 0.0
        self._flinch_pitch = 0.0
        self._land_dip = 0.0
        self._shake_trauma = 0.0
        self.air_time = 0.0
        self.grounded = True
