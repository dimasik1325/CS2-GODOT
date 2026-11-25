"""
Продвинутая 3D-система вооружения от первого лица (10 видов оружия + 3D-перчатки + гранаты):
- Первичное оружие: AK-47, M4A1-S (глушитель), AWP (2-кратный снайперский прицел ПКМ),
  MP9 SMG, XM1014 (дробовик на 8 картечин), FAMAS (переключение AUTO / 3-ROUND BURST на ПКМ)
- Пистолеты: USP-S (глушитель), Desert Eagle, Glock-18 (SEMI / 3-ROUND BURST на ПКМ)
- Ближний бой: Karambit Knife (быстрый порез ЛКМ 55 ур. / силовой удар ПКМ 90 ур. / 180 ур. в спину!)
- 3D тактические перчатки и рукава спецназа на всех моделях от первого лица
- Осмотр оружия в руках по клавише F (CS2 Weapon Inspect + вращение керамбита!)
- Вылет 3D латунных гильз, трассеры пуль, динамический свет дульной вспышки и прострел дерева (Wallbang)
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
     invoke,
    lerp,
    mouse,
    raycast,
)

from src.fx import FXManager
from src.player import CS2Player
from src.settings import (
    GRENADE_ORDER,
    GRENADE_SPECS,
    WEAPON_SPECS,
    SoundManager,
    apply_pbr_material,
    load_safe_model,
    load_safe_texture,
    resource_path,
    rgb32,
    rgba32,
)


class WeaponViewModel(Entity):
    """3D-модель оружия в руках игрока с тактическими 3D-перчатками, затвором и вспышкой."""

    def __init__(self, weapon_id: str, spec: dict[str, Any], parent_pivot: Entity) -> None:
        super().__init__(
            parent=parent_pivot,
            position=Vec3(*spec["view_pos"]),
        )
        self.weapon_id = weapon_id
        self.spec = spec
        self.base_pos = Vec3(*spec["view_pos"])

        self.actor: Actor | None = None
        self.animator: Animator | None = None

        self.mesh_holder = Entity(
            parent=self,
            rotation=Vec3(*spec["view_rot"]),
            scale=float(spec["view_scale"]),
        )

        self.loaded_from_glb: bool = self._try_load_glb_or_actor(spec["model_path"])
        if not self.loaded_from_glb:
            self.mesh_holder.rotation = Vec3(0.0, 0.0, 0.0)
            self._build_primitive_fallback(weapon_id)

        # Подвижная деталь затвора (дёргается назад при каждом выстреле!)
        self.bolt_piece: Entity | None = None
        if not spec["is_melee"]:
            self.bolt_piece = Entity(
                parent=self,
                model="cube",
                position=Vec3(0.024, 0.032, 0.04),
                scale=(0.016, 0.016, 0.075),
                color=rgb32(185, 192, 204),
            )
            apply_pbr_material(self.bolt_piece, "chrome")

        # 3D Тактические перчатки и рукава спецназа CT
        self._build_first_person_gloves(weapon_id, bool(spec["is_melee"]))

        # Дульная вспышка (Muzzle Flash)
        self.muzzle_flash: Entity | None = None
        if not spec["is_melee"]:
            muzzle_z = 0.56 if weapon_id == "awp" else (0.48 if spec["category"] == "primary" else 0.26)
            mf_tex = load_safe_texture("assets/textures/muzzle_flash.png")
            self.muzzle_flash = Entity(
                parent=self,
                position=Vec3(0.0, 0.032, muzzle_z),
                enabled=False,
            )
            flash_scale = 0.13 if spec.get("silenced") else 0.23
            if mf_tex is not None:
                Entity(
                    parent=self.muzzle_flash,
                    model="quad",
                    texture=mf_tex,
                    scale=flash_scale,
                    color=color.white,
                    unlit=True,
                    double_sided=True,
                )
            else:
                Entity(
                    parent=self.muzzle_flash,
                    model="cube",
                    scale=(flash_scale * 0.7, 0.035, 0.035),
                    color=rgb32(255, 222, 95),
                    unlit=True,
                )
                Entity(
                    parent=self.muzzle_flash,
                    model="cube",
                    scale=(0.035, flash_scale * 0.7, 0.035),
                    color=rgb32(255, 185, 55),
                    unlit=True,
                )

    def _build_first_person_gloves(self, weapon_id: str, is_melee: bool) -> None:
        """Добавляет объёмные 3D-руки в тёмно-синих рукавах спецназа и карбоновых перчатках."""
        sleeve_col = rgb32(34, 48, 68)
        glove_col = rgb32(26, 28, 32)
        knuckle_col = rgb32(72, 78, 88)

        # Правая рука на пистолетной рукояти
        r_arm = Entity(
            parent=self,
            model="cube",
            position=(0.055, -0.145, -0.18),
            rotation=(-22.0, -10.0, 8.0),
            scale=(0.068, 0.068, 0.28),
            color=sleeve_col,
        )
        r_glove = Entity(
            parent=self,
            model="cube",
            position=(0.012, -0.075, -0.03),
            rotation=(-15.0, 0.0, 0.0),
            scale=(0.062, 0.065, 0.095),
            color=glove_col,
        )
        Entity(parent=r_glove, model="cube", position=(0, 0.45, 0.1), scale=(0.88, 0.25, 0.45), color=knuckle_col)
        apply_pbr_material(r_arm, "fabric")
        apply_pbr_material(r_glove, "polymer")

        # Левая рука на цевье (для винтовок/дробовиков/ПП) или в стойке ножа
        if not is_melee and self.spec["category"] == "primary":
            l_arm = Entity(
                parent=self,
                model="cube",
                position=(-0.115, -0.125, -0.02),
                rotation=(-16.0, 26.0, -12.0),
                scale=(0.066, 0.066, 0.34),
                color=sleeve_col,
            )
            l_glove = Entity(
                parent=self,
                model="cube",
                position=(-0.018, -0.042, 0.16),
                scale=(0.064, 0.058, 0.105),
                color=glove_col,
            )
            apply_pbr_material(l_arm, "fabric")
            apply_pbr_material(l_glove, "polymer")

    def _try_load_glb_or_actor(self, rel_model_path: str) -> bool:
        model_np = load_safe_model(rel_model_path, target_max_extent=0.95)
        if model_np is None:
            return False

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

        ent = Entity(parent=self.mesh_holder, model=model_np, unlit=False)
        apply_pbr_material(ent, "steel")
        return True

    def play_embedded_anim(self, anim_name: str, loop: bool = False) -> None:
        if self.actor is None:
            return
        available = self.actor.getAnimNames()
        if anim_name in available:
            if loop:
                self.actor.loop(anim_name)
            else:
                self.actor.play(anim_name)

    def _build_primitive_fallback(self, weapon_id: str) -> None:
        """Полный fallback всех 10 видов оружия из 3D-примитивов, если папка assets/models удалена."""
        steel = rgb32(44, 47, 52)
        gunmetal = rgb32(68, 72, 78)
        wood = rgb32(128, 72, 32)
        bakelite = rgb32(178, 78, 28)
        chrome = rgb32(198, 204, 214)
        olive = rgb32(62, 86, 54)
        crimson = rgb32(198, 36, 42)

        if weapon_id == "ak47":
            Entity(parent=self.mesh_holder, model="cube", scale=(0.055, 0.075, 0.34), position=(0, 0, 0.04), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.058, 0.068, 0.20), position=(0, 0.005, 0.28), color=wood)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.020, 0.020, 0.32), position=(0, 0.015, 0.50), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.048, 0.085, 0.24), position=(0, -0.045, -0.22), rotation_x=-8, color=wood)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.042, 0.21, 0.075), position=(0, -0.135, 0.12), rotation_x=-22, color=bakelite)
        elif weapon_id == "awp":
            Entity(parent=self.mesh_holder, model="cube", scale=(0.058, 0.082, 0.44), position=(0, 0, 0.05), color=olive)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.036, 0.036, 0.30), position=(0, 0.09, 0.05), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.022, 0.022, 0.52), position=(0, 0.02, 0.50), color=steel)
        elif weapon_id in ("m4a1", "famas", "mp9", "shotgun"):
            col_main = gunmetal if weapon_id != "mp9" else steel
            Entity(parent=self.mesh_holder, model="cube", scale=(0.054, 0.078, 0.32), position=(0, 0, 0.04), color=col_main)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.030, 0.030, 0.28), position=(0, 0.012, 0.34), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.040, 0.17, 0.065), position=(0, -0.12, 0.08), color=gunmetal)
        elif weapon_id in ("deagle", "usp", "glock"):
            slide_c = chrome if weapon_id == "deagle" else (olive if weapon_id == "glock" else gunmetal)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.044, 0.058, 0.24), position=(0, 0.02, 0.06), color=slide_c)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.038, 0.14, 0.058), position=(0, -0.09, -0.02), rotation_x=14, color=steel)
        else:
            Entity(parent=self.mesh_holder, model="cube", scale=(0.032, 0.042, 0.14), position=(0, -0.03, -0.04), color=steel)
            Entity(parent=self.mesh_holder, model="cube", scale=(0.010, 0.046, 0.25), position=(0, 0.01, 0.16), color=crimson)

    def flash_muzzle(self) -> None:
        if self.muzzle_flash is None:
            return
        self.muzzle_flash.enabled = True
        self.muzzle_flash.rotation_z = random.uniform(0.0, 360.0)
        sc = random.uniform(0.85, 1.22)
        self.muzzle_flash.scale = Vec3(sc, sc, sc)
        invoke(setattr, self.muzzle_flash, "enabled", False, delay=0.042)


class WeaponManager:
    """
    Управляет всеми 10 образцами оружия, гранатами (HE, Flash, Smoke, Molotov),
    прицеливанием AWP, режимом отсечки по 3 патрона (Burst), осмотром оружия (F),
    прострелом тонких преград (Wallbang) и подсчётом точности стрельбы для таблицы счёта.
    """

    ALL_WEAPONS: tuple[str, ...] = (
        "ak47",
        "m4a1",
        "awp",
        "mp9",
        "shotgun",
        "famas",
        "usp",
        "deagle",
        "glock",
        "knife",
    )

    def __init__(
        self,
        player: CS2Player,
        sound_mgr: SoundManager,
        fx_mgr: FXManager | None = None,
        on_hit_enemy: Callable[[bool, bool, str, str, int], None] | None = None,
        on_loud_gunshot: Callable[[Vec3], None] | None = None,
        on_mode_notice: Callable[[str], None] | None = None,
    ) -> None:
        self.player = player
        self.sound_mgr = sound_mgr
        self.fx_mgr = fx_mgr
        self.on_hit_enemy = on_hit_enemy
        self.on_loud_gunshot = on_loud_gunshot
        self.on_mode_notice = on_mode_notice

        self.pivot = Entity(parent=player.camera_pivot, position=(0.0, 0.0, 0.0))

        self.models: dict[str, WeaponViewModel] = {}
        self.ammo_in_mag: dict[str, int] = {}
        self.ammo_reserve: dict[str, int] = {}
        self.burst_mode: dict[str, bool] = {}

        for wid in self.ALL_WEAPONS:
            spec = WEAPON_SPECS[wid]
            vm = WeaponViewModel(wid, spec, self.pivot)
            vm.enabled = False
            self.models[wid] = vm
            self.ammo_in_mag[wid] = int(spec["mag_size"])
            self.ammo_reserve[wid] = int(spec["reserve_max"])
            self.burst_mode[wid] = False

        # Экипированные слоты игрока + полный список купленного оружия
        self.owned_primaries: list[str] = ["ak47", "m4a1"]
        self.owned_secondaries: list[str] = ["deagle", "usp"]
        self.primary_id: str = "ak47"
        self.secondary_id: str = "deagle"
        self.current_weapon_id: str = "ak47"

        # Гранаты игрока
        self.grenades: dict[str, int] = {"he": 1, "flash": 1, "smoke": 1, "molotov": 1}
        self.selected_grenade: str = "he"
        self._grenade_throw_cooldown: float = 0.0

        # Таймеры стрельбы, отсечки Burst, перезарядки, зума и осмотра оружия (F)
        self.is_reloading: bool = False
        self._reload_timer: float = 0.0
        self._fire_cooldown: float = 0.0
        self._equip_cooldown: float = 0.0
        self._burst_queue: int = 0
        self._burst_shot_timer: float = 0.0
        self.scope_stage: int = 0            # 0 = без зума, 1 = 1x зум, 2 = 2x снайперский зум
        self._inspect_timer: float = 0.0

        # Статистика стрельбы игрока
        self.shots_fired: int = 0
        self.shots_hit: int = 0
        self.total_damage_dealt: int = 0

        # Анимационные переменные рук
        self.current_spread: float = WEAPON_SPECS["ak47"]["base_spread"]
        self._shots_in_burst: int = 0
        self._bob_phase: float = 0.0
        self._kick_back: float = 0.0
        self._kick_rot_x: float = 0.0
        self._slash_anim: float = 0.0
        self._bolt_offset: float = 0.0
        self._decal_pool: deque[Entity] = deque(maxlen=44)

        self.equip("ak47", play_sound=False)

    @property
    def active_spec(self) -> dict[str, Any]:
        return WEAPON_SPECS[self.current_weapon_id]

    @property
    def active_model(self) -> WeaponViewModel:
        return self.models[self.current_weapon_id]

    @property
    def is_sniper_scoped(self) -> bool:
        return self.scope_stage > 0 and self.current_weapon_id == "awp"

    def set_visible(self, visible: bool) -> None:
        self.pivot.enabled = visible and not self.is_sniper_scoped

    def clear_zoom(self) -> None:
        self.scope_stage = 0
        self.player.zoom_fov_override = None
        if self.player.enabled and self.player.is_alive:
            self.pivot.enabled = True

    def grant_weapon(self, weapon_id: str) -> None:
        """Выдаёт купленное в меню закупки B оружие, пополняет его патроны и берёт в руки."""
        if weapon_id not in WEAPON_SPECS:
            return
        spec = WEAPON_SPECS[weapon_id]
        self.ammo_in_mag[weapon_id] = int(spec["mag_size"])
        self.ammo_reserve[weapon_id] = int(spec["reserve_max"])
        if spec["category"] == "primary":
            if weapon_id not in self.owned_primaries:
                self.owned_primaries.append(weapon_id)
            self.primary_id = weapon_id
        elif spec["category"] == "secondary":
            if weapon_id not in self.owned_secondaries:
                self.owned_secondaries.append(weapon_id)
            self.secondary_id = weapon_id
        self.equip(weapon_id, play_sound=True)

    def grant_grenade(self, g_type: str, amount: int = 1) -> bool:
        if g_type not in GRENADE_SPECS:
            return False
        max_c = int(GRENADE_SPECS[g_type]["max_carry"])
        if self.grenades.get(g_type, 0) >= max_c:
            return False
        self.grenades[g_type] = min(max_c, self.grenades.get(g_type, 0) + amount)
        self.selected_grenade = g_type
        return True

    def reset_all_ammo(self) -> None:
        """Пополняет боезапас и базовый пояс гранат в начале раунда."""
        self.is_reloading = False
        self._reload_timer = 0.0
        self._burst_queue = 0
        self._shots_in_burst = 0
        self.clear_zoom()
        for wid in self.ALL_WEAPONS:
            spec = WEAPON_SPECS[wid]
            self.ammo_in_mag[wid] = int(spec["mag_size"])
            self.ammo_reserve[wid] = int(spec["reserve_max"])
        for g_id in GRENADE_ORDER:
            self.grenades[g_id] = max(self.grenades.get(g_id, 0), 1)
        target = self.primary_id if self.current_weapon_id == "knife" else self.current_weapon_id
        self.equip(target, play_sound=False)

    def equip(self, weapon_id: str, play_sound: bool = True) -> None:
        if weapon_id not in self.models:
            return

        self.clear_zoom()
        self.is_reloading = False
        self._reload_timer = 0.0
        self._burst_queue = 0
        self._shots_in_burst = 0
        self._inspect_timer = 0.0

        for wid, vm in self.models.items():
            vm.enabled = wid == weapon_id
            vm.rotation = Vec3(0.0, 0.0, 0.0)
            vm.position = Vec3(vm.base_pos)

        self.current_weapon_id = weapon_id
        spec = self.active_spec
        if spec["category"] == "primary":
            self.primary_id = weapon_id
        elif spec["category"] == "secondary":
            self.secondary_id = weapon_id

        self.player.weapon_mobility = float(spec["mobility"])
        self.current_spread = float(spec["base_spread"])
        self._fire_cooldown = 0.0
        self._equip_cooldown = float(spec.get("equip_time", 0.22))

        self._kick_back = 0.08
        self._kick_rot_x = 18.0
        self.active_model.play_embedded_anim("idle", loop=True)

        if play_sound:
            self.sound_mgr.play_sfx("empty_click", volume=0.45, pitch=1.18)

    def cycle_slot(self, delta: int) -> None:
        slot_chain = [self.primary_id, self.secondary_id, "knife"]
        # Если в owned_primaries больше 1 винтовки (например AK-47 и M4A1-S), включаем обе в колесо!
        ordered: list[str] = []
        for wid in (*self.owned_primaries, *self.owned_secondaries, "knife"):
            if wid not in ordered:
                ordered.append(wid)
        if not ordered:
            ordered = slot_chain
        cur_idx = ordered.index(self.current_weapon_id) if self.current_weapon_id in ordered else 0
        self.equip(ordered[(cur_idx + delta) % len(ordered)])

    def start_inspect(self) -> None:
        """Запускает 3D-анимацию осмотра оружия в руках (клавиша F, как в CS2!)."""
        if self.is_reloading or self.is_sniper_scoped:
            return
        self._inspect_timer = 2.15
        self.sound_mgr.play_sfx("empty_click", volume=0.35, pitch=1.42)

    def start_reload(self) -> None:
        spec = self.active_spec
        wid = self.current_weapon_id
        if spec["is_melee"] or self.is_reloading:
            return
        mag_cap = int(spec["mag_size"])
        if self.ammo_in_mag[wid] >= mag_cap or self.ammo_reserve[wid] <= 0:
            return

        self.clear_zoom()
        self._inspect_timer = 0.0
        self._burst_queue = 0
        self.is_reloading = True
        self._reload_timer = float(spec["reload_time"])
        self._shots_in_burst = 0
        self.sound_mgr.play_sfx("reload", volume=0.82, pitch=1.0)
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

    def handle_secondary_action(self) -> None:
        """
        Правая кнопка мыши (ПКМ):
        - Для AWP и M4A1-S: ступенчатый оптический / тактический прицел
        - Для FAMAS и Glock-18: переключение режима стрельбы AUTO/SEMI <-> 3-ROUND BURST
        - Для Karambit Knife: мощный силовой удар (180 урона со спины!)
        """
        spec = self.active_spec
        wid = self.current_weapon_id
        if spec["is_melee"]:
            self.try_shoot(heavy_melee=True)
            return

        scopes = spec.get("scope_levels", ())
        if scopes:
            self.scope_stage = (self.scope_stage + 1) % (len(scopes) + 1)
            if self.scope_stage == 0:
                self.clear_zoom()
            else:
                self.player.zoom_fov_override = float(scopes[self.scope_stage - 1])
                if wid == "awp":
                    self.pivot.enabled = False
            self.sound_mgr.play_sfx("empty_click", volume=0.58, pitch=1.28)
            return

        if spec.get("burst_capable"):
            self.burst_mode[wid] = not self.burst_mode[wid]
            mode_txt = "3-ROUND BURST" if self.burst_mode[wid] else ("AUTO" if spec["automatic"] else "SEMI-AUTO")
            self.sound_mgr.play_sfx("empty_click", volume=0.58, pitch=1.35)
            if self.on_mode_notice is not None:
                self.on_mode_notice(f"{spec['display_name']}: {mode_txt}")

    def cycle_selected_grenade(self) -> None:
        available = [g for g in GRENADE_ORDER if self.grenades.get(g, 0) > 0]
        if not available:
            return
        if self.selected_grenade not in available:
            self.selected_grenade = available[0]
        else:
            idx = (available.index(self.selected_grenade) + 1) % len(available)
            self.selected_grenade = available[idx]
        self.sound_mgr.play_sfx("empty_click", volume=0.45, pitch=1.3)
        if self.on_mode_notice is not None:
            g_name = GRENADE_SPECS[self.selected_grenade]["display_name"]
            self.on_mode_notice(f"SELECTED: {g_name} (Press G to Throw)")

    def try_throw_grenade(self) -> bool:
        """Бросает выбранную тактическую гранату по клавише G."""
        if self.fx_mgr is None or self._grenade_throw_cooldown > 0.0 or not self.player.is_alive:
            return False

        if self.grenades.get(self.selected_grenade, 0) <= 0:
            avail = [g for g in GRENADE_ORDER if self.grenades.get(g, 0) > 0]
            if not avail:
                self.sound_mgr.play_sfx("empty_click", volume=0.50)
                return False
            self.selected_grenade = avail[0]

        g_type = self.selected_grenade
        self.grenades[g_type] -= 1
        self._grenade_throw_cooldown = 0.65
        self._kick_rot_x = -12.0
        self.fx_mgr.throw_grenade(
            grenade_type=g_type,
            origin=camera.world_position,
            forward=camera.forward,
            up=camera.up,
        )
        return True

    def get_total_spread(self) -> float:
        spec = self.active_spec
        if spec["is_melee"]:
            return 0.004
        base = float(spec["base_spread"])
        if self.scope_stage > 0:
            base = 0.0012 if self.current_weapon_id == "awp" else base * 0.45
        spread_val = min(float(spec["max_spread"]), max(base, self.current_spread if self.scope_stage == 0 else base + self._shots_in_burst * 0.006))
        penalty = self.player.get_movement_spread_penalty()
        return clamp(spread_val + penalty, 0.001, float(spec["max_spread"]) + 0.085)

    def handle_input(self, key: str) -> None:
        if not self.player.is_alive or not self.player.enabled:
            return

        if key == "1":
            if self.current_weapon_id in self.owned_primaries and len(self.owned_primaries) > 1:
                idx = (self.owned_primaries.index(self.current_weapon_id) + 1) % len(self.owned_primaries)
                self.equip(self.owned_primaries[idx])
            else:
                self.equip(self.primary_id)
        elif key == "2":
            if self.current_weapon_id in self.owned_secondaries and len(self.owned_secondaries) > 1:
                idx = (self.owned_secondaries.index(self.current_weapon_id) + 1) % len(self.owned_secondaries)
                self.equip(self.owned_secondaries[idx])
            else:
                self.equip(self.secondary_id)
        elif key == "3":
            if self.current_weapon_id != "knife":
                self.equip("knife")
        elif key == "4":
            if self.current_weapon_id != "m4a1":
                self.grant_weapon("m4a1")
            else:
                self.cycle_selected_grenade()
        elif key == "6":
            self.grant_weapon("awp")
        elif key == "7":
            self.grant_weapon("mp9")
        elif key == "8":
            self.grant_weapon("shotgun")
        elif key == "9":
            self.grant_weapon("famas")
        elif key == "0":
            nxt_p = "usp" if self.current_weapon_id != "usp" else "glock"
            self.grant_weapon(nxt_p)
        elif key == "g":
            self.try_throw_grenade()
        elif key == "v":
            self.cycle_selected_grenade()
        elif key == "f":
            self.start_inspect()
        elif key == "scroll up":
            self.cycle_slot(-1)
        elif key == "scroll down":
            self.cycle_slot(1)
        elif key == "r":
            self.start_reload()
        elif key == "left mouse down":
            wid = self.current_weapon_id
            if self.burst_mode.get(wid, False) and self._fire_cooldown <= 0.0 and not self.is_reloading:
                if self.try_shoot():
                    self._burst_queue = 2
                    self._burst_shot_timer = 0.065
            else:
                self.try_shoot()
        elif key == "right mouse down":
            self.handle_secondary_action()

    def try_shoot(self, heavy_melee: bool = False) -> bool:
        if not self.player.is_alive or self.is_reloading:
            return False
        if self._fire_cooldown > 0.0 or self._equip_cooldown > 0.0:
            return False

        wid = self.current_weapon_id
        spec = self.active_spec
        self._inspect_timer = 0.0

        if not spec["is_melee"]:
            if self.ammo_in_mag[wid] <= 0:
                self.sound_mgr.play_sfx("empty_click", volume=0.70)
                self._fire_cooldown = 0.22
                self._burst_queue = 0
                if self.ammo_reserve[wid] > 0:
                    self.start_reload()
                return False
            self.ammo_in_mag[wid] -= 1

        self._fire_cooldown = float(spec.get("heavy_rate", 0.78) if heavy_melee else spec["fire_rate"])
        self._shots_in_burst += 1
        self.shots_fired += 1

        self.sound_mgr.play_sfx(
            spec["shoot_sound"],
            volume=0.90,
            pitch=0.84 if heavy_melee else random.uniform(0.97, 1.03),
        )
        vm = self.active_model
        vm.play_embedded_anim("shoot", loop=False)
        vm.flash_muzzle()

        if spec["is_melee"]:
            self._slash_anim = 1.25 if heavy_melee else 1.0
        else:
            self._kick_back = min(0.10, self._kick_back + (0.075 if wid == "awp" else 0.042))
            self._kick_rot_x = min(13.0, self._kick_rot_x + (7.5 if wid == "awp" else 4.2))
            self._bolt_offset = -0.055

            # Выброс 3D-гильзы и динамический свет выстрела на стенах!
            if self.fx_mgr is not None:
                shell_pos = camera.world_position + camera.right * 0.24 - camera.up * 0.14 + camera.forward * 0.42
                self.fx_mgr.spawn_shell_casing(shell_pos, camera.right, camera.up, is_shotgun=(wid == "shotgun"))
                if not spec.get("silenced", False):
                    self.fx_mgr.pulse_dynamic_light(
                        camera.world_position + camera.forward * 0.9,
                        (255, 196, 92),
                        duration=0.048,
                    )

            # Оповещение ботов по слуху, если оружие без глушителя!
            if not spec.get("silenced", False) and self.on_loud_gunshot is not None:
                self.on_loud_gunshot(self.player.world_position)

        total_spread = self.get_total_spread()
        pellets = int(spec.get("pellets", 1))
        hit_any = False
        for pellet_idx in range(pellets):
            if self._perform_shot_raycast(spec, total_spread, heavy_melee=heavy_melee, spawn_tracer=(pellet_idx == 0)):
                hit_any = True
        if hit_any:
            self.shots_hit += 1

        # Для AWP после выстрела кратковременно передёргиваем продольно-скользящий затвор
        if wid == "awp" and self.scope_stage > 0:
            self.clear_zoom()

        if not spec["is_melee"]:
            self.current_spread = min(
                float(spec["max_spread"]),
                self.current_spread + float(spec["spread_per_shot"]),
            )
            pitch_kick = float(spec["recoil_pitch"]) * (1.0 + min(self._shots_in_burst, 8) * 0.06)
            if self._shots_in_burst <= 4:
                yaw_sign = random.uniform(-0.35, 0.35)
            else:
                yaw_sign = math.sin(self._shots_in_burst * 0.75) + random.uniform(-0.25, 0.25)
            yaw_kick = float(spec["recoil_yaw"]) * yaw_sign
            self.player.apply_recoil(pitch_kick, yaw_kick)

        return True

    def _perform_shot_raycast(
        self,
        spec: dict[str, Any],
        spread: float,
        heavy_melee: bool = False,
        spawn_tracer: bool = True,
    ) -> bool:
        """Выполняет баллистический луч с поддержкой дроби, удара в спину ножом, бочек и прострела дерева."""
        origin = camera.world_position
        spread_x = random.gauss(0.0, spread * 0.55)
        spread_y = random.gauss(0.0, spread * 0.55)
        shot_dir = (camera.forward + camera.right * spread_x + camera.up * spread_y).normalized()
        max_range = float(spec["range"])

        hit_info = raycast(
            origin,
            shot_dir,
            distance=max_range,
            ignore=[self.player, self.pivot],
        )
        if not hit_info.hit or hit_info.entity is None:
            if spawn_tracer and not spec["is_melee"] and self.fx_mgr is not None:
                self.fx_mgr.spawn_tracer(origin + camera.right * 0.16 - camera.up * 0.12 + shot_dir * 0.6, origin + shot_dir * 38.0)
            return False

        if spawn_tracer and not spec["is_melee"] and self.fx_mgr is not None:
            self.fx_mgr.spawn_tracer(
                origin + camera.right * 0.16 - camera.up * 0.12 + shot_dir * 0.55,
                hit_info.world_point,
            )

        hit_ent = hit_info.entity
        enemy = getattr(hit_ent, "enemy_ref", None)
        if enemy is not None and enemy.state != "DEAD":
            return self._apply_bullet_to_enemy(
                enemy=enemy,
                hit_ent=hit_ent,
                hit_pt=hit_info.world_point,
                hit_normal=hit_info.world_normal,
                dist=float(hit_info.distance),
                shot_dir=shot_dir,
                spec=spec,
                heavy_melee=heavy_melee,
                dmg_scale=1.0,
            )

        # Проверка попадания в разрушаемую бочку с горючим или деревянный ящик!
        destructible = getattr(hit_ent, "destructible_ref", None)
        if destructible is not None and destructible.alive:
            destructible.take_damage(
                int(spec["damage"]),
                on_barrel_explode=(lambda p: self.fx_mgr.trigger_explosion_vfx(p, radius=9.2, source_label="FUEL BARREL")) if self.fx_mgr else None,
                on_wood_shatter=(lambda p: self.fx_mgr.spawn_surface_impact(p, Vec3(0, 1, 0), "wood")) if self.fx_mgr else None,
            )

        mat_kind = getattr(hit_ent, "surface_material", "stone")
        if self.fx_mgr is not None:
            self.fx_mgr.spawn_surface_impact(hit_info.world_point, hit_info.world_normal, mat_kind)
        else:
            self._spawn_impact_spark(hit_info.world_point, rgb32(255, 205, 95))

        if not spec["is_melee"]:
            self._spawn_bullet_decal(hit_info.world_point, hit_info.world_normal)

        # Прострел тонких деревянных дверей и ящиков (CS2 Wallbang!)
        wb_mult = float(spec.get("wallbang_mult", 0.0))
        if not spec["is_melee"] and wb_mult > 0.0 and getattr(hit_ent, "penetrable_wood", False):
            pierce_origin = hit_info.world_point + shot_dir * 0.35
            rem_dist = max(1.0, max_range - float(hit_info.distance) - 0.35)
            wb_hit = raycast(
                pierce_origin,
                shot_dir,
                distance=rem_dist,
                ignore=[self.player, self.pivot, hit_ent],
            )
            if wb_hit.hit and wb_hit.entity is not None:
                wb_enemy = getattr(wb_hit.entity, "enemy_ref", None)
                if wb_enemy is not None and wb_enemy.state != "DEAD":
                    return self._apply_bullet_to_enemy(
                        enemy=wb_enemy,
                        hit_ent=wb_hit.entity,
                        hit_pt=wb_hit.world_point,
                        hit_normal=wb_hit.world_normal,
                        dist=float(hit_info.distance + wb_hit.distance),
                        shot_dir=shot_dir,
                        spec=spec,
                        heavy_melee=False,
                        dmg_scale=wb_mult,
                    )

        return False

    def _apply_bullet_to_enemy(
        self,
        enemy: Any,
        hit_ent: Entity,
        hit_pt: Vec3,
        hit_normal: Vec3,
        dist: float,
        shot_dir: Vec3,
        spec: dict[str, Any],
        heavy_melee: bool,
        dmg_scale: float,
    ) -> bool:
        is_headshot = bool(getattr(hit_ent, "is_head", False))

        if spec["is_melee"]:
            # Проверка удара ножом в спину (Backstab = 180 HP мгновенной ликвидации!)
            enemy_fwd = Vec3(enemy.forward.x, 0.0, enemy.forward.z).normalized()
            atk_flat = Vec3(shot_dir.x, 0.0, shot_dir.z).normalized()
            is_backstab = enemy_fwd.dot(atk_flat) > 0.35
            if is_backstab and heavy_melee:
                raw_dmg = float(spec.get("backstab_damage", 180))
                is_headshot = True
            elif heavy_melee:
                raw_dmg = float(spec.get("heavy_damage", 90))
            else:
                raw_dmg = float(spec["damage"])
        else:
            dist_factor = float(spec["falloff"]) ** (dist / 20.0)
            raw_dmg = float(spec["damage"]) * dist_factor * dmg_scale
            if is_headshot:
                raw_dmg *= float(spec["headshot_mult"])

        final_dmg = max(1, int(round(raw_dmg)))
        self.total_damage_dealt += final_dmg
        killed = enemy.take_damage(final_dmg, is_headshot=is_headshot)

        if is_headshot:
            self.sound_mgr.play_sfx("headshot", volume=0.90)
        else:
            self.sound_mgr.play_sfx("hitmarker", volume=0.75)

        if self.fx_mgr is not None:
            self.fx_mgr.spawn_surface_impact(hit_pt, hit_normal, "blood")
            if self.player.settings.show_damage_numbers:
                self.fx_mgr.spawn_damage_popup(hit_pt, final_dmg, is_headshot=is_headshot)
            if killed:
                self.fx_mgr.spawn_loot_drop(enemy.world_position)
        else:
            self._spawn_impact_spark(hit_pt, rgb32(230, 45, 40))

        if self.on_hit_enemy is not None:
            kill_reward = int(spec.get("kill_reward", 300))
            self.on_hit_enemy(is_headshot, killed, spec["display_name"], enemy.bot_name, kill_reward)
        return True

    def _spawn_impact_spark(self, world_pt: Vec3, spark_col: Any) -> None:
        spark = Entity(model="sphere", position=world_pt, scale=0.075, color=spark_col, unlit=True)
        spark.animate_scale(0.005, duration=0.12)
        destroy(spark, delay=0.14)

    def _spawn_bullet_decal(self, world_pt: Vec3, world_normal: Vec3) -> None:
        if len(self._decal_pool) >= (self._decal_pool.maxlen or 44):
            oldest = self._decal_pool.popleft()
            if oldest is not None:
                destroy(oldest)

        decal = Entity(
            model="cube",
            position=world_pt + world_normal * 0.012,
            scale=(0.055, 0.055, 0.012),
            color=rgba32(26, 24, 22, 220),
            unlit=True,
        )
        decal.look_at(decal.position + world_normal)
        self._decal_pool.append(decal)
        destroy(decal, delay=8.5)

    def clear_decals(self) -> None:
        while self._decal_pool:
            ent = self._decal_pool.popleft()
            if ent is not None:
                destroy(ent)

    def update(self, dt: float) -> None:
        if self._fire_cooldown > 0.0:
            self._fire_cooldown = max(0.0, self._fire_cooldown - dt)
        if self._equip_cooldown > 0.0:
            self._equip_cooldown = max(0.0, self._equip_cooldown - dt)
        if self._grenade_throw_cooldown > 0.0:
            self._grenade_throw_cooldown = max(0.0, self._grenade_throw_cooldown - dt)
        if self._inspect_timer > 0.0:
            self._inspect_timer = max(0.0, self._inspect_timer - dt)

        # Очередь из 3 выстрелов (FAMAS / Glock-18 Burst Mode)
        if self._burst_queue > 0 and not self.is_reloading and self.player.is_alive:
            self._burst_shot_timer -= dt
            if self._burst_shot_timer <= 0.0:
                self._fire_cooldown = 0.0
                if self.try_shoot():
                    self._burst_queue -= 1
                    self._burst_shot_timer = 0.068
                else:
                    self._burst_queue = 0

        if self.is_reloading:
            self._reload_timer -= dt
            if self._reload_timer <= 0.0:
                self._finish_reload()

        spec = self.active_spec
        wid = self.current_weapon_id

        # Автоогонь при зажатой ЛКМ (если не включён режим 3-Round Burst)
        if (
            spec["automatic"]
            and not self.burst_mode.get(wid, False)
            and mouse.left
            and self.player.enabled
            and self.player.is_alive
            and not self.is_reloading
        ):
            self.try_shoot()

        if not mouse.left or self.is_reloading:
            if self._fire_cooldown <= 0.0:
                self._shots_in_burst = max(0, self._shots_in_burst - 1)
            self.current_spread = lerp(
                self.current_spread,
                float(spec["base_spread"]),
                min(1.0, dt * 9.5),
            )

        # Возврат подвижного затвора оружия
        vm = self.active_model
        self._bolt_offset = lerp(self._bolt_offset, 0.0, min(1.0, dt * 22.0))
        if vm.bolt_piece is not None:
            vm.bolt_piece.z = 0.04 + self._bolt_offset

        self._kick_back = lerp(self._kick_back, 0.0, min(1.0, dt * 16.0))
        self._kick_rot_x = lerp(self._kick_rot_x, 0.0, min(1.0, dt * 15.0))
        self._slash_anim = lerp(self._slash_anim, 0.0, min(1.0, dt * 10.0))

        # Покачивание оружия при беге/ходьбе/дыхании
        if self.player.grounded and self.player.is_moving_horizontally:
            bob_freq = 12.6 if self.player.is_sprinting else (6.5 if self.player.is_crouching else 9.2)
            self._bob_phase += dt * bob_freq
            bob_amp = 0.014 * self.player.horizontal_speed_ratio
            bob_x = math.cos(self._bob_phase) * bob_amp
            bob_y = abs(math.sin(self._bob_phase)) * (-bob_amp * 0.9)
        else:
            breath_spd = 0.45 if self.player.holding_breath else 1.8
            self._bob_phase += dt * breath_spd
            bob_x = math.cos(self._bob_phase) * 0.002
            bob_y = math.sin(self._bob_phase * 2.0) * 0.002

        sway_x = clamp(-mouse.velocity[0] * 0.12, -0.026, 0.026)
        sway_y = clamp(-mouse.velocity[1] * 0.12, -0.026, 0.026)

        reload_drop_y = -0.11 if self.is_reloading else 0.0
        reload_tilt_z = 28.0 if self.is_reloading else 0.0
        reload_tilt_x = 18.0 if self.is_reloading else 0.0

        # Анимация осмотра оружия F (CS2 Inspect + вращение керамбита на 360°!)
        inspect_x = 0.0
        inspect_y = 0.0
        inspect_rot_y = 0.0
        inspect_rot_z = 0.0
        if self._inspect_timer > 0.0:
            p = 1.0 - (self._inspect_timer / 2.15)
            envelope = math.sin(p * math.pi)
            if wid == "knife":
                inspect_rot_z = p * 360.0
                inspect_y = 0.04 * envelope
            else:
                inspect_x = -0.07 * envelope
                inspect_y = 0.045 * envelope
                inspect_rot_y = -32.0 * envelope
                inspect_rot_z = 26.0 * math.sin(p * math.pi * 2.0) * envelope

        # Смещение оружия к центру экрана при прицеливании M4A1-S
        ads_shift_x = -0.12 if (self.scope_stage > 0 and wid != "awp") else 0.0
        ads_shift_y = 0.035 if (self.scope_stage > 0 and wid != "awp") else 0.0

        slash_z = math.sin(min(1.0, self._slash_anim) * math.pi) * 0.17
        slash_yaw = math.sin(min(1.0, self._slash_anim) * math.pi) * -34.0

        target_pos = Vec3(
            vm.base_pos.x + bob_x + sway_x + inspect_x + ads_shift_x,
            vm.base_pos.y + bob_y + sway_y + reload_drop_y + inspect_y + ads_shift_y,
            vm.base_pos.z - self._kick_back + slash_z,
        )
        target_rot = Vec3(
            -self._kick_rot_x + reload_tilt_x,
            slash_yaw + inspect_rot_y,
            reload_tilt_z + inspect_rot_z,
        )

        vm.position = lerp(vm.position, target_pos, min(1.0, dt * 18.0))
        vm.rotation = lerp(vm.rotation, target_rot, min(1.0, dt * 16.0))
