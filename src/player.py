"""
Контроллер игрока CS2 с ПОЛНОЦЕННОЙ 3D-МОДЕЛЬЮ СПЕЦНАЗОВЦА ИГРОКА:
1) Вид на собственные 3D-ноги, разгрузку, наколенники и ботинки при взгляде вниз и в подкате (как в CS2)!
2) Переключение в режим 3-го лица через плечо по клавише F5 (полная 3D-модель CT SAS Operator с коллизией камеры)!
3) 3D-оперативник на подиуме в Главном меню с оружием и выбранным скином!
4) Тактическое движение: Подкаты (Shift+Ctrl), Наклоны из-за угла (Q/E), Стамина, Задержка дыхания,
   3D-фонарь SpotLight (T), Боевой стимулятор +35 HP (X), расчёт направления входящего урона!
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from panda3d.core import PerspectiveLens
from panda3d.core import Spotlight as PandaSpotLight
from ursina import Entity, Vec2, Vec3, camera, clamp, held_keys, lerp, raycast, scene, time
from ursina.prefabs.first_person_controller import FirstPersonController

from src.settings import (
    WEAPON_SKINS,
    GameSettings,
    SoundManager,
    apply_pbr_material,
    load_safe_model,
    rgb32,
)


class MenuOperatorShowcase:
    """Живая 3D-модель оперативника спецназа CT на подиуме в Главном меню с оружием и скином."""

    def __init__(self, podium_pos: Vec3) -> None:
        self.root = Entity(parent=scene, position=podium_pos, rotation_y=198.0, add_to_scene_entities=False)
        self._anim_t: float = 0.0

        op_glb = load_safe_model("assets/models/player_operator.glb", normalize_to=1.82)
        if op_glb is not None:
            self.body = Entity(parent=self.root, model=op_glb, add_to_scene_entities=False)
            apply_pbr_material(self.body, shininess=38.0, specular_strength=0.42)
        else:
            self.body = Entity(parent=self.root, add_to_scene_entities=False)
            Entity(parent=self.body, model="cube", position=(0, 1.0, 0), scale=(0.48, 0.90, 0.28), color=rgb32(36, 56, 88), add_to_scene_entities=False)
            Entity(parent=self.body, model="sphere", position=(0, 1.65, 0), scale=0.30, color=rgb32(42, 64, 98), add_to_scene_entities=False)

        # Оружие в руках оперативника на подиуме
        self.gun_holder = Entity(
            parent=self.root,
            position=Vec3(0.14, 1.15, -0.30),
            rotation=Vec3(12.0, 18.0, -8.0),
            scale=0.88,
            add_to_scene_entities=False,
        )
        self._weapon_entities: dict[str, Entity] = {}
        for wid in ("ak47", "m4a1", "awp", "p90", "deagle"):
            m = load_safe_model(f"assets/models/{wid}.glb", normalize_to=0.72)
            if m is not None:
                ent = Entity(parent=self.gun_holder, model=m, enabled=(wid == "ak47"), add_to_scene_entities=False)
            else:
                ent = Entity(parent=self.gun_holder, model="cube", scale=(0.06, 0.10, 0.52), color=rgb32(48, 52, 60), enabled=(wid == "ak47"), add_to_scene_entities=False)
            apply_pbr_material(ent, shininess=56.0, specular_strength=0.65, metallic=0.60)
            self._weapon_entities[wid] = ent

    def set_visible(self, visible: bool) -> None:
        self.root.enabled = visible

    def set_showcase_loadout(self, weapon_id: str, skin_idx: int) -> None:
        target = weapon_id if weapon_id in self._weapon_entities else "ak47"
        skin = WEAPON_SKINS[skin_idx % len(WEAPON_SKINS)]
        tint = skin["tint"]
        col = rgb32(*tint) if tint is not None else rgb32(255, 255, 255)
        for wid, ent in self._weapon_entities.items():
            ent.enabled = wid == target
            ent.color = col
            apply_pbr_material(ent, shininess=float(skin["shininess"]), specular_strength=0.72, metallic=float(skin["metal"]))

    def update(self, dt: float) -> None:
        if not self.root.enabled:
            return
        self._anim_t += dt
        self.body.y = math.sin(self._anim_t * 1.9) * 0.018
        self.root.rotation_y = 198.0 + math.sin(self._anim_t * 0.65) * 14.0


class CS2Player(FirstPersonController):
    """Игрок от 1-го и 3-го лица (F5) с 3D-ногами, бронёй, подкатами, наклонами Q/E и фонарём T."""

    BASE_SPEED = 6.8
    SPRINT_MULTIPLIER = 1.34
    CROUCH_MULTIPLIER = 0.52
    SLIDE_SPEED = 11.4
    STANDING_EYE_Y = 1.72
    CROUCH_EYE_Y = 1.06
    SLIDE_EYE_Y = 0.78

    def __init__(
        self,
        settings: GameSettings,
        sound_mgr: SoundManager,
        on_death_callback: Callable[[], None] | None = None,
        on_hurt_callback: Callable[[float | None], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            speed=self.BASE_SPEED,
            jump_height=1.68,
            jump_duration=0.40,
            gravity=1.0,
            **kwargs,
        )
        if hasattr(self, "cursor") and self.cursor is not None:
            self.cursor.enabled = False

        self.settings = settings
        self.sound_mgr = sound_mgr
        self.on_death_callback = on_death_callback
        self.on_hurt_callback = on_hurt_callback

        self.max_hp: int = 100
        self.hp: int = 100
        self.max_armor: int = 100
        self.armor: int = 100
        self.has_helmet: bool = True
        self.has_defuse_kit: bool = True
        self.stimshots: int = 1
        self.is_alive: bool = True

        self.stamina: float = 100.0
        self.is_crouching: bool = False
        self.is_sprinting: bool = False
        self.is_sliding: bool = False
        self.holding_breath: bool = False
        self._slide_timer: float = 0.0
        self._slide_cooldown: float = 0.0
        self._slide_dir: Vec3 = Vec3(0.0, 0.0, 0.0)

        self.lean_amount: float = 0.0
        self.weapon_mobility: float = 1.0
        self.zoom_fov_override: float | None = None
        self.third_person_mode: bool = False

        self._base_eye_y: float = self.STANDING_EYE_Y
        self._footstep_timer: float = 0.0
        self._walk_phase: float = 0.0
        self._was_grounded: bool = True
        self._landing_dip: float = 0.0
        self._shake_trauma: float = 0.0
        self._cam_roll: float = 0.0

        self.camera_pivot.y = self.STANDING_EYE_Y

        # ── 1. СОБСТВЕННЫЕ 3D-НОГИ И РАЗГРУЗКА ОТ ПЕРВОГО ЛИЦА (ВИДНЫ ПРИ ВЗГЛЯДЕ ВНИЗ И В ПОДКАТЕ!) ──
        self.fp_legs_rig = Entity(parent=self, position=(0.0, 0.0, -0.14), add_to_scene_entities=False)
        navy_col = rgb32(34, 52, 82)
        vest_col = rgb32(24, 30, 40)
        boot_col = rgb32(20, 22, 26)
        # Тактический пояс и кобура на правом бедре
        Entity(parent=self.fp_legs_rig, model="cube", position=(0.0, 0.88, 0.02), scale=(0.40, 0.10, 0.24), color=vest_col, add_to_scene_entities=False)
        self.fp_left_leg = Entity(parent=self.fp_legs_rig, position=(-0.13, 0.84, 0.04), add_to_scene_entities=False)
        self.fp_right_leg = Entity(parent=self.fp_legs_rig, position=(0.13, 0.84, 0.04), add_to_scene_entities=False)
        for idx_l, leg_piv in enumerate((self.fp_left_leg, self.fp_right_leg)):
            Entity(parent=leg_piv, model="cube", position=(0.0, -0.36, 0.0), scale=(0.155, 0.72, 0.165), color=navy_col, add_to_scene_entities=False)
            Entity(parent=leg_piv, model="sphere", position=(0.0, -0.38, 0.085), scale=(0.13, 0.13, 0.06), color=vest_col, add_to_scene_entities=False)
            Entity(parent=leg_piv, model="cube", position=(0.0, -0.76, 0.05), scale=(0.16, 0.14, 0.28), color=boot_col, add_to_scene_entities=False)
            if idx_l == 1:
                Entity(parent=leg_piv, model="cube", position=(0.095, -0.18, 0.02), scale=(0.05, 0.18, 0.12), color=vest_col, add_to_scene_entities=False)

        # ── 2. ПОЛНАЯ 3D-МОДЕЛЬ СПЕЦНАЗОВЦА CT SAS ДЛЯ ВИДА ОТ 3-ГО ЛИЦА (F5) ──
        self.tp_rig = Entity(parent=self, position=(0.0, 0.0, 0.0), enabled=False, add_to_scene_entities=False)
        op_glb = load_safe_model("assets/models/player_operator.glb", normalize_to=1.80)
        if op_glb is not None:
            self.tp_body = Entity(parent=self.tp_rig, model=op_glb, rotation_y=180.0, add_to_scene_entities=False)
            apply_pbr_material(self.tp_body, shininess=38.0, specular_strength=0.45)
        else:
            self.tp_body = Entity(parent=self.tp_rig, add_to_scene_entities=False)
            Entity(parent=self.tp_body, model="cube", position=(0, 1.15, 0), scale=(0.46, 0.62, 0.28), color=navy_col, add_to_scene_entities=False)
            Entity(parent=self.tp_body, model="sphere", position=(0, 1.65, 0), scale=0.30, color=navy_col, add_to_scene_entities=False)

        self.tp_left_leg = Entity(parent=self.tp_rig, position=(-0.13, 0.78, 0.0), add_to_scene_entities=False)
        self.tp_right_leg = Entity(parent=self.tp_rig, position=(0.13, 0.78, 0.0), add_to_scene_entities=False)
        for l_p in (self.tp_left_leg, self.tp_right_leg):
            Entity(parent=l_p, model="cube", position=(0, -0.38, 0), scale=(0.15, 0.74, 0.16), color=navy_col, add_to_scene_entities=False)

        # ── 3. ПОДСТВОЛЬНЫЙ 3D-ФОНАРЬ SPOTLIGHT (T) ──
        self.flashlight_on: bool = False
        self._spot_light = PandaSpotLight("player_tactical_flashlight")
        self._spot_light.setColor((0.0, 0.0, 0.0, 1.0))
        lens = PerspectiveLens()
        lens.setFov(40.0)
        lens.setNearFar(0.25, 44.0)
        self._spot_light.setLens(lens)
        self._spot_light.setAttenuation((1.0, 0.032, 0.007))
        self._spot_np = self.camera_pivot.attachNewNode(self._spot_light)
        scene.setLight(self._spot_np)

        self.apply_sensitivity(settings.mouse_sensitivity)

    def apply_sensitivity(self, sens_value: float) -> None:
        zoom_mult = self.settings.zoom_sensitivity if self.zoom_fov_override is not None else 1.0
        s = sens_value * zoom_mult
        self.mouse_sensitivity = Vec2(s, s)

    def toggle_third_person(self) -> bool:
        """Переключает камеру между 1-м лицом и тактическим видом от 3-го лица через плечо (F5)."""
        self.third_person_mode = not self.third_person_mode
        self.tp_rig.enabled = self.third_person_mode
        self.fp_legs_rig.enabled = not self.third_person_mode
        if not self.third_person_mode:
            camera.position = Vec3(0.0, 0.0, 0.0)
            camera.rotation = Vec3(0.0, 0.0, 0.0)
        return self.third_person_mode

    def toggle_flashlight(self) -> bool:
        self.flashlight_on = not self.flashlight_on
        if self.flashlight_on:
            self._spot_light.setColor((1.35, 1.32, 1.18, 1.0))
        else:
            self._spot_light.setColor((0.0, 0.0, 0.0, 1.0))
        self.sound_mgr.play_sfx("empty_click", volume=0.55, pitch=1.35)
        return self.flashlight_on

    def use_stimshot(self) -> bool:
        if not self.is_alive or self.stimshots <= 0 or self.hp >= self.max_hp:
            return False
        self.stimshots -= 1
        self.hp = min(self.max_hp, self.hp + 35)
        self.stamina = min(100.0, self.stamina + 45.0)
        self.sound_mgr.play_sfx("c4_defuse", volume=0.70, pitch=1.40)
        return True

    def add_screen_shake(self, amount: float) -> None:
        self._shake_trauma = min(1.0, self._shake_trauma + amount)

    @property
    def is_moving_horizontally(self) -> bool:
        return bool(held_keys["w"] or held_keys["a"] or held_keys["s"] or held_keys["d"]) or self.is_sliding

    @property
    def current_velocity_approx(self) -> Vec3:
        if self.is_sliding:
            return self._slide_dir * self.SLIDE_SPEED
        move = self.forward * (held_keys["w"] - held_keys["s"]) + self.right * (held_keys["d"] - held_keys["a"])
        return move.normalized() * self.speed if move.length() > 0.01 else Vec3(0, 0, 0)

    def respawn(self, spawn_pos: Vec3, yaw: float = 0.0) -> None:
        self.position = Vec3(spawn_pos.x, spawn_pos.y + 0.05, spawn_pos.z)
        self.rotation_y = yaw
        self.camera_pivot.rotation_x = 0.0
        self.camera_pivot.rotation_z = 0.0
        self.camera_pivot.position = Vec3(0.0, self.STANDING_EYE_Y, 0.0)
        self._base_eye_y = self.STANDING_EYE_Y
        self.air_time = 0.0

        self.hp = self.max_hp
        self.armor = self.max_armor
        self.has_helmet = True
        self.has_defuse_kit = True
        self.stimshots = max(1, self.stimshots)
        self.stamina = 100.0
        self.is_alive = True
        self.is_Sliding = False
        self.is_sliding = False
        self.lean_amount = 0.0
        self._shake_trauma = 0.0
        self.zoom_fov_override = None

    def take_damage(
        self,
        raw_amount: int,
        is_headshot: bool = False,
        attacker_pos: Vec3 | None = None,
    ) -> None:
        if not self.is_alive or raw_amount <= 0:
            return

        dmg = float(raw_amount)
        if is_headshot and self.has_helmet and self.armor > 0:
            dmg *= 0.52
            self.armor = max(0, self.armor - 18)
            self.sound_mgr.play_sfx("shell_clink", volume=0.75, pitch=0.85)

        if self.armor > 0:
            absorbed = int(dmg * 0.42)
            armor_damage = min(self.armor, max(1, absorbed))
            self.armor -= armor_damage
            hp_damage = max(1, int(dmg) - armor_damage)
        else:
            hp_damage = int(dmg)

        self.hp = max(0, self.hp - hp_damage)
        self.add_screen_shake(clamp(hp_damage / 65.0, 0.12, 0.55))
        self.sound_mgr.play_sfx("player_hurt", volume=0.72)

        # Вычисляем угол направления на стрелявшего врага (-180..+180) для дуги урона в HUD!
        rel_angle: float | None = None
        if attacker_pos is not None:
            to_att = Vec3(attacker_pos.x - self.x, 0.0, attacker_pos.z - self.z)
            if to_att.length() > 0.2:
                to_att_n = to_att.normalized()
                fwd = Vec3(self.forward.x, 0.0, self.forward.z).normalized()
                rgt = Vec3(self.right.x, 0.0, self.right.z).normalized()
                rel_angle = math.degrees(math.atan2(to_att_n.dot(rgt), to_att_n.dot(fwd)))

        if self.on_hurt_callback is not None:
            self.on_hurt_callback(rel_angle)

        if self.hp <= 0:
            self.is_alive = False
            if self.on_death_callback is not None:
                self.on_death_callback()

    def update(self) -> None:
        if not self.enabled or not self.is_alive:
            return

        dt = min(float(time.dt), 0.05)

        if self.y < -12.0:
            self.position = Vec3(0.0, 1.5, -24.0)
            self.air_time = 0.0

        self._slide_cooldown = max(0.0, self._slide_cooldown - dt)
        want_crouch = bool(held_keys["left control"] or held_keys["c"])
        want_sprint = bool(held_keys["left shift"]) and self.is_moving_horizontally and self.stamina > 8.0

        # 1. Спринт-подкат (Shift + Ctrl)
        if want_crouch and want_sprint and not self.is_sliding and self._slide_cooldown <= 0.0 and self.grounded:
            move_vec = self.forward * (held_keys["w"] - held_keys["s"]) + self.right * (held_keys["d"] - held_keys["a"])
            if move_vec.length() > 0.1:
                self.is_sliding = True
                self._slide_timer = 0.62
                self._slide_cooldown = 1.15
                self._slide_dir = move_vec.normalized()
                self.stamina = max(0.0, self.stamina - 22.0)
                self.sound_mgr.play_sfx("footstep", volume=0.68, pitch=0.72)

        if self.is_sliding:
            self._slide_timer -= dt
            hit = raycast(self.position + Vec3(0, 0.5, 0), self._slide_dir, distance=0.85, ignore=[self])
            if self._slide_timer <= 0.0 or hit.hit:
                self.is_sliding = False
            else:
                slide_spd = self.SLIDE_SPEED * clamp(self._slide_timer / 0.62 + 0.35, 0.4, 1.0)
                self.position += self._slide_dir * (slide_spd * dt)

        self.is_crouching = want_crouch or self.is_sliding
        self.is_sprinting = want_sprint and not self.is_crouching and self.zoom_fov_override is None

        # 2. Стамина и задержка дыхания
        self.holding_breath = bool(held_keys["left shift"]) and self.zoom_fov_override is not None and self.stamina > 5.0
        if self.is_sprinting or self.holding_breath:
            self.stamina = max(0.0, self.stamina - dt * 24.0)
        else:
            self.stamina = min(100.0, self.stamina + dt * 20.0)

        mult = 1.0
        if self.is_crouching:
            mult = self.CROUCH_MULTIPLIER
        elif self.is_sprinting:
            mult = self.SPRINT_MULTIPLIER
        if self.zoom_fov_override is not None:
            mult *= 0.68
        self.speed = 0.5 if self.is_sliding else self.BASE_SPEED * mult * self.weapon_mobility

        # 3. Высота глаз и пружина приземления
        target_eye_y = (
            self.SLIDE_EYE_Y if self.is_sliding else (self.CROUCH_EYE_Y if self.is_crouching else self.STANDING_EYE_Y)
        )
        self._base_eye_y = lerp(self._base_eye_y, target_eye_y, min(1.0, dt * 13.0))

        super().update()

        if not self._was_grounded and self.grounded:
            self._landing_dip = 0.16
            self.sound_mgr.play_sfx("footstep", volume=0.60, pitch=0.82)
        self._was_grounded = bool(self.grounded)
        self._landing_dip = lerp(self._landing_dip, 0.0, min(1.0, dt * 11.0))

        # 4. Тактический наклон Q / E с защитой от прохождения сквозь стены
        lean_input = float(held_keys["e"]) - float(held_keys["q"])
        target_lean = lean_input if not self.is_sprinting else 0.0
        if abs(target_lean) > 0.05:
            check_dir = self.right * (1.0 if target_lean > 0 else -1.0)
            wall_hit = raycast(self.position + Vec3(0, self._base_eye_y, 0), check_dir, distance=0.62, ignore=[self])
            if wall_hit.hit:
                target_lean = 0.0
        self.lean_amount = lerp(self.lean_amount, target_lean, min(1.0, dt * 11.0))

        # 5. Наклон камеры, тряска и шаги + анимация 3D-ног игрока!
        strafe_dir = float(held_keys["d"]) - float(held_keys["a"])
        slide_tilt = -6.5 if self.is_sliding else 0.0
        target_roll = -strafe_dir * 1.65 - self.lean_amount * 10.5 + slide_tilt
        self._cam_roll = lerp(self._cam_roll, target_roll, min(1.0, dt * 10.0))

        shake_x = 0.0
        shake_y = 0.0
        if self._shake_trauma > 0.001:
            self._shake_trauma = max(0.0, self._shake_trauma - dt * 2.4)
            mag = self._shake_trauma * self._shake_trauma
            shake_x = random.uniform(-0.045, 0.045) * mag
            shake_y = random.uniform(-0.045, 0.045) * mag

        self.camera_pivot.x = self.lean_amount * 0.36 + shake_x
        self.camera_pivot.y = self._base_eye_y - self._landing_dip + shake_y
        self.camera_pivot.rotation_z = self._cam_roll

        # Анимация 3D-ног от 1-го и 3-го лица
        if self.is_sliding:
            self.fp_legs_rig.position = Vec3(0.0, -0.22, 0.34)
            self.fp_left_leg.rotation_x = -62.0
            self.fp_right_leg.rotation_x = -46.0
            self.tp_rig.y = -0.35
        else:
            crouch_off = -0.32 if self.is_crouching else 0.0
            self.fp_legs_rig.position = Vec3(0.0, crouch_off, -0.14)
            self.tp_rig.y = crouch_off * 0.65
            if self.grounded and self.is_moving_horizontally:
                self._walk_phase += dt * (12.5 if self.is_sprinting else 8.8)
                sw = math.sin(self._walk_phase) * 28.0
                self.fp_left_leg.rotation_x = sw
                self.fp_right_leg.rotation_x = -sw
                self.tp_left_leg.rotation_x = sw
                self.tp_right_leg.rotation_x = -sw
            else:
                self.fp_left_leg.rotation_x = lerp(self.fp_left_leg.rotation_x, 0.0, min(1.0, dt * 10.0))
                self.fp_right_leg.rotation_x = lerp(self.fp_right_leg.rotation_x, 0.0, min(1.0, dt * 10.0))
                self.tp_left_leg.rotation_x = self.fp_left_leg.rotation_x
                self.tp_right_leg.rotation_x = self.fp_right_leg.rotation_x

        self.tp_body.rotation_z = -self.lean_amount * 12.0

        # Камера от 3-го лица через правое плечо с защитой от стен!
        if self.third_person_mode and self.zoom_fov_override is None:
            cam_back = (-self.camera_pivot.forward * 2.55 + self.camera_pivot.right * 0.52 + Vec3(0, 0.28, 0))
            dist = cam_back.length()
            origin_w = self.camera_pivot.world_position
            wall_c = raycast(origin_w, cam_back.normalized(), distance=dist, ignore=[self])
            safe_dist = (wall_c.distance - 0.25) if wall_c.hit else dist
            safe_dist = max(0.45, safe_dist)
            camera.position = Vec3(0.52 * (safe_dist / dist), 0.24, -safe_dist)

        # Плавный динамический FOV
        if self.zoom_fov_override is not None:
            target_fov = self.zoom_fov_override
        elif self.is_sliding:
            target_fov = self.settings.fov + 8.5
        elif self.is_sprinting:
            target_fov = self.settings.fov + 5.5
        else:
            target_fov = self.settings.fov
        camera.fov = lerp(camera.fov, target_fov, min(1.0, dt * 12.0))
        self.apply_sensitivity(self.settings.mouse_sensitivity)

        if self.grounded and self.is_moving_horizontally and not self.is_sliding:
            step_interval = 0.29 if self.is_sprinting else (0.52 if self.is_crouching else 0.40)
            self._footstep_timer -= dt
            if self._footstep_timer <= 0.0:
                self._footstep_timer = step_interval
                vol = 0.45 if self.is_sprinting else (0.14 if self.is_crouching else 0.28)
                self.sound_mgr.play_sfx("footstep", volume=vol, pitch=random.uniform(0.92, 1.08))
        else:
            self._footstep_timer = min(self._footstep_timer, 0.08)
