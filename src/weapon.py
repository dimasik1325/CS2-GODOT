"""
Система оружия от первого лица (ViewModel .glb + fallback на составные примитивы),
стрельба через Raycast, разброс, паттерн отдачи CS2, перезарядка, вспышки выстрелов,
следы от пуль на стенах и переключение слотов (1/2/3/4 + колесо мыши).
"""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Any, Callable

from direct.actor.Actor import Actor
from ursina import (
    Animator,
    Entity,
    Vec3,
    camera,
    clamp,
    color,
    destroy,
    lerp,
    mouse,
    raycast,
    time,
)

from src.player import CS2Player
from src.settings import (
    WEAPON_SPECS,
    SoundManager,
    load_safe_model,
    load_safe_texture,
    resource_path,
    rgb32,
    rgba32,
)


class WeaponViewModel(Entity):
    """
    3D-модель одного образца оружия в руках игрока.
    Поддерживает:
      1) Загрузку .glb/.gltf (включая встроенные скелетные анимации idle/shoot/reload/walk).
      2) Автоматический fallback на детализированную модель из примитивов Ursina, если .glb не найден.
    """

    def __init__(self, weapon_id: str, spec: dict[str, Any], parent_pivot: Entity) -> None:
        super().__init__(
            parent=parent_pivot,
            position=Vec3(*spec["view_pos"]),
        )
        self.weapon_id = weapon_id
        self.spec = spec
        self.base_pos = Vec3(*spec["view_pos"])
        self.base_rot = Vec3(0.0, 0.0, 0.0)

        self.actor: Actor | None = None
        self.animator: Animator | None = None

        # Контейнер под сам меш (с поворотом 180° по Y для стандарта glTF +Z -> Ursina +Z)
        self.mesh_holder = Entity(
            parent=self,
            rotation=Vec3(*spec["view_rot"]),
            scale=float(spec["view_scale"]),
        )

        loaded_ok = self._try_load_glb_or_actor(spec["model_path"])
        if not loaded_ok:
            # Fallback: собираем узнаваемую составную модель из кубов Ursina
            self.mesh_holder.rotation = Vec3(0.0, 0.0, 0.0)
            self._build_primitive_fallback(weapon_id)

        # Дульная вспышка (Muzzle Flash) у среза ствола
        self.muzzle_flash: Entity | None = None
        if not spec["is_melee"]:
            muzzle_z = 0.48 if weapon_id in ("ak47", "m4a1") else 0.25
            mf_tex = load_safe_texture("assets/textures/muzzle_flash.png")
            self.muzzle_flash = Entity(
                parent=self,
                position=Vec3(0.0, 0.035, muzzle_z),
                enabled=False,
            )
            if mf_tex is not None:
                Entity(
                    parent=self.muzzle_flash,
                    model="quad",
                    texture=mf_tex,
                    scale=0.22,
                    color=color.white,
                    unlit=True,
                    double_sided=True,
                )
            else:
                # Fallback вспышки, если muzzle_flash.png отсутствует
                Entity(
                    parent=self.muzzle_flash,
                    model="cube",
                    scale=(0.16, 0.04, 0.04),
                    color=rgb32(255, 220, 95),
                    unlit=True,
                )
                Entity(
                    parent=self.muzzle_flash,
                    model="cube",
                    scale=(0.04, 0.16, 0.04),
                    color=rgb32(255, 185, 55),
                    unlit=True,
                )

    def _try_load_glb_or_actor(self, rel_model_path: str) -> bool:
        """Пробует загрузить .glb (со скелетными анимациями Actor при наличии рига, иначе как меш)."""
        model_np = load_safe_model(rel_model_path, target_max_extent=0.95)
        if model_np is None:
            return False

        # Если .glb содержит скелетный риг (+Character), подключаем Panda3D Actor + Ursina Animator
        full_file = resource_path(rel_model_path)
        if not model_np.find("**/+Character").isEmpty() and full_file.is_file():
            try:
                candidate_actor = Actor(str(full_file))
                anim_names = candidate_actor.getAnimNames()
                if anim_names:
                    candidate_actor.reparentTo(self.mesh_holder)
                    self.actor = candidate_actor
                    self.animator = Animator(
                        animations={name: None for name in anim_names},
                        start_state=anim_names[0],
                    )
                    if "idle" in anim_names:
                        self.actor.loop("idle")
                    return True
                candidate_actor.cleanup()
            except Exception:
                pass

        Entity(parent=self.mesh_holder, model=model_np, unlit=False)
        return True

    def play_embedded_anim(self, anim_name: str, loop: bool = False) -> None:
        """Проигрывает встроенную анимацию .glb (idle/shoot/reload/walk), если она есть в модели."""
        if self.actor is None:
            return
        available = self.actor.getAnimNames()
        if anim_name in available:
            if loop:
                self.actor.loop(anim_name)
            else:
                self.actor.play(anim_name)

    def _build_primitive_fallback(self, weapon_id: str) -> None:
        """Строит детализированное оружие из примитивов Ursina, если .glb файл удалён или не найден."""
        steel = rgb32(44, 47, 52)
        gunmetal = rgb32(68, 72, 78)
        wood = rgb32(128, 72, 32)
        bakelite = rgb32(178, 78, 28)
        chrome = rgb32(198, 204, 214)

        if weapon_id == "ak47":
            Entity(parent=self.mesh_holder, model="cube", scale=(0.055, 0.075, 0.34), position=(0, 0, 0.04), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.058, 0.068, 0.20), position=(0, 0.005, 0.28), color=wood)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.020, 0.020, 0.32), position=(0, 0.015, 0.50), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.048, 0.085, 0.24), position=(0, -0.045, -0.22), rotation_x=-8, color=wood)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.042, 0.21, 0.075), position=(0, -0.135, 0.12), rotation_x=-22, color=bakelite)
        elif weapon_id == "m4a1":
            Entity(parent=self.mesh_holder, model="cube", scale=(0.054, 0.078, 0.30), position=(0, 0, 0.04), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.056, 0.064, 0.22), position=(0, 0.008, 0.27), color=gunmetal)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.036, 0.036, 0.26), position=(0, 0.012, 0.58), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.046, 0.090, 0.22), position=(0, -0.015, -0.22), color=gunmetal)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.040, 0.18, 0.068), position=(0, -0.125, 0.10), rotation_x=-8, color=gunmetal)
        elif weapon_id == "deagle":
            Entity(parent=self.mesh_holder, model="cube", scale=(0.048, 0.065, 0.27), position=(0, 0.02, 0.08), color=chrome)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.040, 0.145, 0.062), position=(0, -0.095, -0.02), rotation_x=14, color=steel)
        else:  # knife
            Entity(parent=self.mesh_holder, model="cube", scale=(0.032, 0.042, 0.15), position=(0, -0.03, -0.04), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.055, 0.075, 0.018), position=(0, -0.01, 0.04), color=gunmetal)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.010, 0.046, 0.26), position=(0, 0.01, 0.18), color=chrome)

    def flash_muzzle(self) -> None:
        """Кратковременная вспышка пламени на дульном срезе."""
        if self.muzzle_flash is None:
            return
        self.muzzle_flash.enabled = True
        self.muzzle_flash.rotation_z = random.uniform(0.0, 360.0)
        scale_jitter = random.uniform(0.85, 1.22)
        self.muzzle_flash.scale = Vec3(scale_jitter, scale_jitter, scale_jitter)

        def _hide() -> None:
            if self.muzzle_flash is not None:
                self.muzzle_flash.enabled = False

        from ursina import invoke

        invoke(_hide, delay=0.045)


class WeaponManager:
    """
    Управляет арсеналом игрока, боезапасом, перезарядкой, отдачей, разбросом,
    трассировкой попаданий (Raycast по хитбоксам врагов) и следами от пуль.
    """

    SLOT_ORDER: tuple[str, ...] = ("ak47", "deagle", "knife", "m4a1")

    def __init__(
        self,
        player: CS2Player,
        sound_mgr: SoundManager,
        on_hit_enemy: Callable[[bool, bool, str, str], None] | None = None,
    ) -> None:
        """
        on_hit_enemy(is_headshot, killed, weapon_display_name, victim_name) — колбэк для HUD и киллфида.
        """
        self.player = player
        self.sound_mgr = sound_mgr
        self.on_hit_enemy = on_hit_enemy

        # Корневой узел оружия внутри camera_pivot игрока
        self.pivot = Entity(parent=player.camera_pivot, position=(0.0, 0.0, 0.0))

        self.models: dict[str, WeaponViewModel] = {}
        self.ammo_in_mag: dict[str, int] = {}
        self.ammo_reserve: dict[str, int] = {}

        for wid in self.SLOT_ORDER:
            spec = WEAPON_SPECS[wid]
            vm = WeaponViewModel(wid, spec, self.pivot)
            vm.enabled = False
            self.models[wid] = vm
            self.ammo_in_mag[wid] = int(spec["mag_size"])
            self.ammo_reserve[wid] = int(spec["reserve_max"])

        self.current_weapon_id: str = "ak47"
        self.is_reloading: bool = False
        self._reload_timer: float = 0.0
        self._fire_cooldown: float = 0.0
        self._equip_cooldown: float = 0.0

        # Параметры очереди, разброса и процедурной анимации рук
        self.current_spread: float = WEAPON_SPECS["ak47"]["base_spread"]
        self._shots_in_burst: int = 0
        self._bob_phase: float = 0.0
        self._kick_back: float = 0.0
        self._kick_rot_x: float = 0.0
        self._slash_anim: float = 0.0
        self._decal_pool: deque[Entity] = deque(maxlen=36)

        self.equip("ak47", play_sound=False)

    @property
    def active_spec(self) -> dict[str, Any]:
        return WEAPON_SPECS[self.current_weapon_id]

    @property
    def active_model(self) -> WeaponViewModel:
        return self.models[self.current_weapon_id]

    def set_visible(self, visible: bool) -> None:
        self.pivot.enabled = visible

    def reset_all_ammo(self) -> None:
        """Пополняет все магазины и запас патронов в начале нового раунда."""
        self.is_reloading = False
        self._reload_timer = 0.0
        self._shots_in_burst = 0
        for wid in self.SLOT_ORDER:
            spec = WEAPON_SPECS[wid]
            self.ammo_in_mag[wid] = int(spec["mag_size"])
            self.ammo_reserve[wid] = int(spec["reserve_max"])
        self.equip(self.current_weapon_id if self.current_weapon_id != "knife" else "ak47", play_sound=False)

    def equip(self, weapon_id: str, play_sound: bool = True) -> None:
        """Переключает активное оружие с прерыванием перезарядки (как quick-switch в CS2)."""
        if weapon_id not in self.models:
            return

        self.is_reloading = False
        self._reload_timer = 0.0
        self._shots_in_burst = 0

        for wid, vm in self.models.items():
            vm.enabled = wid == weapon_id
            vm.rotation = Vec3(0.0, 0.0, 0.0)
            vm.position = Vec3(vm.base_pos)

        self.current_weapon_id = weapon_id
        spec = self.active_spec
        self.player.weapon_mobility = float(spec["mobility"])
        self.current_spread = float(spec["base_spread"])
        self._equip_cooldown = 0.22

        # Анимация доставания оружия снизу
        self._kick_back = 0.08
        self._kick_rot_x = 18.0
        self.active_model.play_embedded_anim("idle", loop=True)

        if play_sound:
            self.sound_mgr.play_sfx("empty_click", volume=0.45, pitch=1.18)

    def cycle_slot(self, delta: int) -> None:
        idx = self.SLOT_ORDER.index(self.current_weapon_id)
        next_idx = (idx + delta) % len(self.SLOT_ORDER)
        self.equip(self.SLOT_ORDER[next_idx])

    def start_reload(self) -> None:
        """Запускает перезарядку текущего огнестрельного оружия по клавише R."""
        spec = self.active_spec
        wid = self.current_weapon_id
        if spec["is_melee"] or self.is_reloading:
            return
        mag_cap = int(spec["mag_size"])
        if self.ammo_in_mag[wid] >= mag_cap or self.ammo_reserve[wid] <= 0:
            return

        self.is_reloading = True
        self._reload_timer = float(spec["reload_time"])
        self._shots_in_burst = 0
        self.sound_mgr.play_sfx("reload", volume=0.80, pitch=1.0)
        self.active_model.play_embedded_anim("reload", loop=False)

    def _finish_reload(self) -> None:
        wid = self.current_weapon_id
        spec = self.active_spec
        mag_cap = int(spec["mag_size"])
        needed = mag_cap - self.ammo_in_mag[wid]
        loaded = min(needed, self.ammo_reserve[wid])
        self.ammo_in_mag[wid] += loaded
        self.ammo_reserve[wid] -= loaded
        self.is_reloading = False
        self._reload_timer = 0.0
        self.active_model.play_embedded_anim("idle", loop=True)

    def get_total_spread(self) -> float:
        """Итоговый динамический разброс (оружие + очередь + движение/прыжок/присед)."""
        spec = self.active_spec
        if spec["is_melee"]:
            return 0.004
        penalty = self.player.get_movement_spread_penalty()
        return clamp(self.current_spread + penalty, 0.002, float(spec["max_spread"]) + 0.08)

    def handle_input(self, key: str) -> None:
        """Обрабатывает нажатия клавиш смены оружия, перезарядки и одиночного выстрела."""
        if not self.player.is_alive or not self.player.enabled:
            return

        if key == "1":
            # Повторное нажатие '1' удобно переключает основную винтовку AK-47 <-> M4A1-S
            target = "m4a1" if self.current_weapon_id == "ak47" else "ak47"
            self.equip(target)
        elif key == "2":
            if self.current_weapon_id != "deagle":
                self.equip("deagle")
        elif key == "3":
            if self.current_weapon_id != "knife":
                self.equip("knife")
        elif key == "4":
            if self.current_weapon_id != "m4a1":
                self.equip("m4a1")
        elif key == "scroll up":
            self.cycle_slot(-1)
        elif key == "scroll down":
            self.cycle_slot(1)
        elif key == "r":
            self.start_reload()
        elif key == "left mouse down":
            # Одиночный клик всегда пытается произвести выстрел (полуавтомат + первый выстрел автомата)
            self.try_shoot()

    def try_shoot(self) -> bool:
        """Проверяет кулдауны и патроны, затем производит выстрел или удар ножом."""
        if not self.player.is_alive or self.is_reloading:
            return False
        if self._fire_cooldown > 0.0 or self._equip_cooldown > 0.0:
            return False

        wid = self.current_weapon_id
        spec = self.active_spec

        if not spec["is_melee"]:
            if self.ammo_in_mag[wid] <= 0:
                self.sound_mgr.play_sfx("empty_click", volume=0.70)
                self._fire_cooldown = 0.22
                if self.ammo_reserve[wid] > 0:
                    self.start_reload()
                return False
            self.ammo_in_mag[wid] -= 1

        self._fire_cooldown = float(spec["fire_rate"])
        self._shots_in_burst += 1

        # Звук выстрела и анимация
        self.sound_mgr.play_sfx(
            spec["shoot_sound"],
            volume=0.88,
            pitch=random.uniform(0.97, 1.03),
        )
        vm = self.active_model
        vm.play_embedded_anim("shoot", loop=False)
        vm.flash_muzzle()

        if spec["is_melee"]:
            self._slash_anim = 1.0
        else:
            self._kick_back = min(0.09, self._kick_back + 0.042)
            self._kick_rot_x = min(11.0, self._kick_rot_x + 4.2)

        # Выполнение Raycast по сцене
        total_spread = self.get_total_spread()
        self._perform_shot_raycast(spec, total_spread)

        # Наращиваем разброс очереди и отдачу камеры (паттерн T-spray для винтовок)
        if not spec["is_melee"]:
            self.current_spread = min(
                float(spec["max_spread"]),
                self.current_spread + float(spec["spread_per_shot"]),
            )
            pitch_kick = float(spec["recoil_pitch"]) * (1.0 + min(self._shots_in_burst, 8) * 0.06)
            if self._shots_in_burst <= 4:
                yaw_sign = random.uniform(-0.35, 0.35)
            else:
                # Горизонтальный увод очереди в стиле AK-47 после 4-го патрона
                wave_dir = math.sin(self._shots_in_burst * 0.75)
                yaw_sign = wave_dir + random.uniform(-0.25, 0.25)
            yaw_kick = float(spec["recoil_yaw"]) * yaw_sign
            self.player.apply_recoil(pitch_kick, yaw_kick)

        return True

    def _perform_shot_raycast(self, spec: dict[str, Any], spread: float) -> None:
        """Пускает луч из центра камеры с учётом конуса разброса и проверяет попадание."""
        origin = camera.world_position
        spread_x = random.gauss(0.0, spread * 0.55)
        spread_y = random.gauss(0.0, spread * 0.55)

        shot_dir = (
            camera.forward
            + camera.right * spread_x
            + camera.up * spread_y
        ).normalized()

        hit_info = raycast(
            origin,
            shot_dir,
            distance=float(spec["range"]),
            ignore=[self.player, self.pivot],
        )

        if not hit_info.hit or hit_info.entity is None:
            return

        hit_ent = hit_info.entity
        enemy = getattr(hit_ent, "enemy_ref", None)

        if enemy is not None and enemy.state != "DEAD":
            is_headshot = bool(getattr(hit_ent, "is_head", False))
            dist = float(hit_info.distance)
            # Падение урона с дистанцией (каждые 20 метров)
            dist_factor = float(spec["falloff"]) ** (dist / 20.0)
            raw_dmg = float(spec["damage"]) * dist_factor
            if is_headshot:
                raw_dmg *= float(spec["headshot_mult"])

            final_dmg = max(1, int(round(raw_dmg)))
            killed = enemy.take_damage(final_dmg, is_headshot=is_headshot)

            if is_headshot:
                self.sound_mgr.play_sfx("headshot", volume=0.90)
            else:
                self.sound_mgr.play_sfx("hitmarker", volume=0.75)

            if self.on_hit_enemy is not None:
                self.on_hit_enemy(is_headshot, killed, spec["display_name"], enemy.bot_name)

            # Красная искра попадания по цели
            self._spawn_impact_spark(hit_info.world_point, rgb32(230, 45, 40))
        else:
            # Попадание в стену, пол или ящик: искра + след пули
            self._spawn_impact_spark(hit_info.world_point, rgb32(255, 205, 95))
            if not spec["is_melee"]:
                self._spawn_bullet_decal(hit_info.world_point, hit_info.world_normal)

    def _spawn_impact_spark(self, world_pt: Vec3, spark_col: Any) -> None:
        spark = Entity(
            model="sphere",
            position=world_pt,
            scale=0.075,
            color=spark_col,
            unlit=True,
        )
        spark.animate_scale(0.005, duration=0.12)
        destroy(spark, delay=0.14)

    def _spawn_bullet_decal(self, world_pt: Vec3, world_normal: Vec3) -> None:
        if len(self._decal_pool) >= (self._decal_pool.maxlen or 36):
            oldest = self._decal_pool.popleft()
            if oldest is not None:
                destroy(oldest)

        decal = Entity(
            model="cube",
            position=world_pt + world_normal * 0.012,
            scale=(0.055, 0.055, 0.012),
            color=rgba32(28, 26, 24, 215),
            unlit=True,
        )
        decal.look_at(decal.position + world_normal)
        self._decal_pool.append(decal)
        destroy(decal, delay=7.5)

    def clear_decals(self) -> None:
        while self._decal_pool:
            ent = self._decal_pool.popleft()
            if ent is not None:
                destroy(ent)

    def update(self, dt: float) -> None:
        """Обновляет таймеры скорострельности, перезарядки, разброса и анимации оружия в руках."""
        if self._fire_cooldown > 0.0:
            self._fire_cooldown = max(0.0, self._fire_cooldown - dt)
        if self._equip_cooldown > 0.0:
            self._equip_cooldown = max(0.0, self._equip_cooldown - dt)

        # Таймер перезарядки
        if self.is_reloading:
            self._reload_timer -= dt
            if self._reload_timer <= 0.0:
                self._finish_reload()

        spec = self.active_spec

        # Автоогонь при зажатой левой кнопке мыши (AK-47 и M4A1-S)
        if (
            spec["automatic"]
            and mouse.left
            and self.player.enabled
            and self.player.is_alive
            and not self.is_reloading
        ):
            self.try_shoot()

        # Восстановление кучности, когда игрок не стреляет
        if not mouse.left or self.is_reloading:
            self._shots_in_burst = max(0, self._shots_in_burst - 1) if self._fire_cooldown <= 0.0 else self._shots_in_burst
            self.current_spread = lerp(
                self.current_spread,
                float(spec["base_spread"]),
                min(1.0, dt * 9.5),
            )

        # Процедурные анимации оружия в руках (Viewbob, Sway, Recoil, Reload, Knife Slash)
        vm = self.active_model
        self._kick_back = lerp(self._kick_back, 0.0, min(1.0, dt * 16.0))
        self._kick_rot_x = lerp(self._kick_rot_x, 0.0, min(1.0, dt * 15.0))
        self._slash_anim = lerp(self._slash_anim, 0.0, min(1.0, dt * 10.0))

        # Покачивание при ходьбе и беге (восьмёрка)
        if self.player.grounded and self.player.is_moving_horizontally:
            bob_freq = 12.5 if self.player.is_sprinting else (6.5 if self.player.is_crouching else 9.2)
            self._bob_phase += dt * bob_freq
            bob_amp = 0.014 * self.player.horizontal_speed_ratio
            bob_x = math.cos(self._bob_phase) * bob_amp
            bob_y = abs(math.sin(self._bob_phase)) * (-bob_amp * 0.9)
        else:
            # Лёгкое дыхание в покое
            self._bob_phase += dt * 1.8
            bob_x = math.cos(self._bob_phase) * 0.002
            bob_y = math.sin(self._bob_phase * 2.0) * 0.002

        # Инерция оружия от движения мыши (weapon sway)
        sway_x = clamp(-mouse.velocity[0] * 0.12, -0.025, 0.025)
        sway_y = clamp(-mouse.velocity[1] * 0.12, -0.025, 0.025)

        # Наклон при перезарядке
        reload_drop_y = -0.10 if self.is_reloading else 0.0
        reload_tilt_z = 28.0 if self.is_reloading else 0.0
        reload_tilt_x = 18.0 if self.is_reloading else 0.0

        # Выпад ножа вперёд при ударе
        slash_z = math.sin(self._slash_anim * math.pi) * 0.16
        slash_yaw = math.sin(self._slash_anim * math.pi) * -32.0

        target_pos = Vec3(
            vm.base_pos.x + bob_x + sway_x,
            vm.base_pos.y + bob_y + sway_y + reload_drop_y,
            vm.base_pos.z - self._kick_back + slash_z,
        )
        target_rot = Vec3(
            -self._kick_rot_x + reload_tilt_x,
            slash_yaw,
            reload_tilt_z,
        )

        vm.position = lerp(vm.position, target_pos, min(1.0, dt * 18.0))
        vm.rotation = lerp(vm.rotation, target_rot, min(1.0, dt * 16.0))
