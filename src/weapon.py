"""
Высокооптимизированный арсенал CS2 из 12 видов оружия + Скины (F8) + Кольцевой пул декалей:
- AK-47, M4A1-S, AWP, FN P90 (50 патронов!), MP9, XM1014 Shotgun (8 картечин), FAMAS,
  USP-S, Desert Eagle, Glock-18, Электрошокер Zeus x27 (3D-молния!) и Нож Керамбит!
- 6 переключаемых 3D PBR-скинов оружия на клавишу F8 (включая «УСАТЫЙ ЗОЛОТОЙ» и «ASIIMOV CYBER»)!
- Кольцевой пул пулевых декалей (0 аллокаций в перестрелке), прострел дерева, зум AWP/P90/M4A1-S,
  3-патронный Burst, 3D-перчатки спецназа, осмотр оружия F и поддержка режима HEADSHOT ONLY!
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from direct.actor.Actor import Actor
from ursina import Animator, Entity, Vec3, camera, clamp, color, held_keys, lerp, raycast, scene

from src.fx import FXManager
from src.player import CS2Player
from src.settings import (
    GRENADE_ORDER,
    GRENADE_SPECS,
    WEAPON_SKINS,
    WEAPON_SPECS,
    GameSettings,
    SoundManager,
    apply_pbr_material,
    asset_path,
    load_safe_model,
    load_safe_texture,
    rgb32,
)


class WeaponViewModel(Entity):
    """3D-модель оружия от первого лица со скинами, подвижным затвором и 3D-перчатками спецназа CT."""

    def __init__(self, weapon_id: str, spec: dict[str, Any], parent_pivot: Entity) -> None:
        super().__init__(
            parent=parent_pivot,
            position=Vec3(*spec["view_pos"]),
            add_to_scene_entities=False,
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
            add_to_scene_entities=False,
        )
        self.skin_targets: list[Entity] = []

        self.loaded_from_glb: bool = self._try_load_glb_or_actor(spec["model_path"])
        if not self.loaded_from_glb:
            self.mesh_holder.rotation = Vec3(0.0, 0.0, 0.0)
            self._build_primitive_fallback(weapon_id)

        self.bolt_piece: Entity | None = None
        if not spec["is_melee"] and not spec.get("is_zeus", False):
            self.bolt_piece = Entity(
                parent=self,
                model="cube",
                position=Vec3(0.024, 0.032, 0.04),
                scale=(0.016, 0.016, 0.075),
                color=rgb32(185, 192, 204),
                add_to_scene_entities=False,
            )
            apply_pbr_material(self.bolt_piece, shininess=75.0, specular_strength=0.82, metallic=0.85)

        self._build_tactical_gloves(weapon_id, bool(spec["is_melee"]))

        flash_tex = load_safe_texture("assets/textures/muzzle_flash.png", repeat=False)
        mz_z = 0.62 if weapon_id == "awp" else (0.32 if spec["slot"] == 2 else 0.48)
        self.muzzle_flash = Entity(
            parent=self,
            model="quad",
            texture=flash_tex,
            position=Vec3(0.0, 0.04, mz_z),
            scale=0.22 if flash_tex is not None else 0.12,
            color=color.white if flash_tex is not None else rgb32(255, 220, 95),
            unlit=True,
            enabled=False,
            add_to_scene_entities=False,
        )

    def _try_load_glb_or_actor(self, rel_path: str) -> bool:
        full = asset_path(rel_path)
        if not full.is_file():
            return False
        static_mesh = load_safe_model(rel_path, normalize_to=0.68)
        if static_mesh is not None:
            ge = Entity(parent=self.mesh_holder, model=static_mesh, add_to_scene_entities=False)
            apply_pbr_material(ge, shininess=56.0, specular_strength=0.68, metallic=0.65)
            self.skin_targets.append(ge)
            return True
        return False

    def _build_tactical_gloves(self, weapon_id: str, is_melee: bool) -> None:
        sleeve_col = rgb32(34, 52, 78)
        glove_col = rgb32(26, 30, 36)
        knuckle_col = rgb32(58, 66, 78)
        arms_root = Entity(parent=self, add_to_scene_entities=False)

        r_arm = Entity(parent=arms_root, position=Vec3(0.03, -0.13, -0.18), rotation=Vec3(-16.0, -6.0, 8.0), add_to_scene_entities=False)
        Entity(parent=r_arm, model="cube", position=(0, 0, -0.10), scale=(0.072, 0.072, 0.24), color=sleeve_col, add_to_scene_entities=False)
        Entity(parent=r_arm, model="sphere", position=(0, 0.01, 0.04), scale=(0.076, 0.068, 0.095), color=glove_col, add_to_scene_entities=False)
        Entity(parent=r_arm, model="cube", position=(0, 0.035, 0.05), scale=(0.064, 0.018, 0.036), color=knuckle_col, add_to_scene_entities=False)

        l_pos = Vec3(-0.08, -0.12, 0.02) if (is_melee or self.spec["slot"] == 2 or weapon_id == "zeus") else Vec3(-0.05, -0.09, 0.16)
        l_rot = Vec3(-22.0, 24.0, -14.0)
        l_arm = Entity(parent=arms_root, position=l_pos, rotation=l_rot, add_to_scene_entities=False)
        Entity(parent=l_arm, model="cube", position=(0, 0, -0.12), scale=(0.070, 0.070, 0.26), color=sleeve_col, add_to_scene_entities=False)
        Entity(parent=l_arm, model="sphere", position=(0, 0.01, 0.04), scale=(0.074, 0.066, 0.092), color=glove_col, add_to_scene_entities=False)
        Entity(parent=l_arm, model="cube", position=(0, 0.034, 0.05), scale=(0.062, 0.018, 0.035), color=knuckle_col, add_to_scene_entities=False)

    def _build_primitive_fallback(self, weapon_id: str) -> None:
        dark = rgb32(42, 46, 54)
        steel = rgb32(138, 146, 158)
        wood = rgb32(138, 76, 36)
        olive = rgb32(66, 92, 56)

        if weapon_id == "knife":
            b1 = Entity(parent=self.mesh_holder, model="cube", position=(0, -0.02, -0.04), scale=(0.024, 0.034, 0.13), color=dark, add_to_scene_entities=False)
            b2 = Entity(parent=self.mesh_holder, model="cube", position=(0, 0.01, 0.10), scale=(0.008, 0.032, 0.18), rotation_x=16.0, color=rgb32(225, 36, 52), add_to_scene_entities=False)
            self.skin_targets.extend([b1, b2])
        elif weapon_id == "zeus":
            b1 = Entity(parent=self.mesh_holder, model="cube", position=(0, 0.02, 0.05), scale=(0.052, 0.060, 0.20), color=rgb32(238, 192, 34), add_to_scene_entities=False)
            Entity(parent=self.mesh_holder, model="cube", position=(0, -0.07, -0.04), scale=(0.038, 0.12, 0.05), rotation_x=15.0, color=dark, add_to_scene_entities=False)
            self.skin_targets.append(b1)
        elif weapon_id in ("deagle", "usp", "glock"):
            slide_col = steel if weapon_id == "deagle" else dark
            b1 = Entity(parent=self.mesh_holder, model="cube", position=(0, 0.03, 0.08), scale=(0.045, 0.055, 0.25), color=slide_col, add_to_scene_entities=False)
            Entity(parent=self.mesh_holder, model="cube", position=(0, -0.06, -0.02), scale=(0.038, 0.13, 0.055), rotation_x=14.0, color=dark, add_to_scene_entities=False)
            if weapon_id == "usp":
                Entity(parent=self.mesh_holder, model="cube", position=(0, 0.03, 0.28), scale=(0.030, 0.030, 0.18), color=rgb32(30, 34, 40), add_to_scene_entities=False)
            self.skin_targets.append(b1)
        elif weapon_id == "awp":
            b1 = Entity(parent=self.mesh_holder, model="cube", position=(0, 0.0, 0.08), scale=(0.056, 0.08, 0.48), color=olive, add_to_scene_entities=False)
            Entity(parent=self.mesh_holder, model="cube", position=(0, 0.03, 0.50), scale=(0.024, 0.024, 0.52), color=dark, add_to_scene_entities=False)
            Entity(parent=self.mesh_holder, model="cube", position=(0, 0.095, 0.08), scale=(0.038, 0.038, 0.28), color=dark, add_to_scene_entities=False)
            self.skin_targets.append(b1)
        else:
            b1 = Entity(parent=self.mesh_holder, model="cube", position=(0, 0.0, 0.06), scale=(0.054, 0.078, 0.36), color=dark, add_to_scene_entities=False)
            Entity(parent=self.mesh_holder, model="cube", position=(0, 0.015, 0.36), scale=(0.024, 0.024, 0.34), color=dark, add_to_scene_entities=False)
            accent = wood if weapon_id == "ak47" else steel
            b2 = Entity(parent=self.mesh_holder, model="cube", position=(0, -0.02, -0.20), scale=(0.046, 0.085, 0.22), color=accent, add_to_scene_entities=False)
            self.skin_targets.extend([b1, b2])

    def apply_skin(self, skin_idx: int) -> None:
        skin = WEAPON_SKINS[skin_idx % len(WEAPON_SKINS)]
        tint = skin["tint"]
        col = rgb32(*tint) if tint is not None else color.white
        for t_ent in self.skin_targets:
            t_ent.color = col
            apply_pbr_material(
                t_ent,
                shininess=float(skin["shininess"]),
                specular_strength=0.74,
                metallic=float(skin["metal"]),
            )

    def play_embedded_anim(self, clip_keyword: str, loop: bool = False) -> bool:
        return False


class WeaponManager:
    """Управляет 12 пушками, 6 скинами (F8), гранатами, пулом декалей и баллистикой."""

    ALL_WEAPONS = (
        "ak47",
        "m4a1",
        "awp",
        "p90",
        "mp9",
        "shotgun",
        "famas",
        "usp",
        "deagle",
        "glock",
        "zeus",
        "knife",
    )
    MAX_DECAL_POOL = 80

    def __init__(
        self,
        player: CS2Player,
        sound_mgr: SoundManager,
        settings: GameSettings | None = None,
        fx_mgr: FXManager | None = None,
        on_hit_enemy: Callable[[bool, bool, str, str, int], None] | None = None,
        on_loud_gunshot: Callable[[Vec3], None] | None = None,
        on_mode_notice: Callable[[str], None] | None = None,
    ) -> None:
        self.player = player
        self.sound_mgr = sound_mgr
        self.settings = settings
        self.fx_mgr = fx_mgr
        self.on_hit_enemy = on_hit_enemy
        self.on_loud_gunshot = on_loud_gunshot
        self.on_mode_notice = on_mode_notice

        self.pivot = Entity(parent=player.camera_pivot, position=(0.0, 0.0, 0.0), add_to_scene_entities=False)

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

        self.owned_primaries: list[str] = ["ak47", "m4a1", "p90"]
        self.owned_secondaries: list[str] = ["deagle", "usp"]
        self.primary_id: str = "ak47"
        self.secondary_id: str = "deagle"
        self.current_weapon_id: str = "ak47"
        self.skin_idx: int = settings.weapon_skin_idx if settings is not None else 0
        self.apply_skin_to_all(self.skin_idx)

        self.grenades: dict[str, int] = {"he": 1, "flash": 1, "smoke": 1, "molotov": 1}
        self.selected_grenade: str = "he"
        self._grenade_throw_cooldown: float = 0.0

        self.scope_stage: int = 0
        self.is_reloading: bool = False
        self._reload_timer: float = 0.0
        self._fire_cooldown: float = 0.0
        self._equip_cooldown: float = 0.0
        self._flash_timer: float = 0.0

        self._burst_queue: int = 0
        self._burst_timer: float = 0.0
        self._shots_in_burst: int = 0
        self.current_spread: float = 0.01

        self._sway_time: float = 0.0
        self._kick_back: float = 0.0
        self._kick_rot_x: float = 0.0
        self._bolt_offset: float = 0.0
        self._inspect_timer: float = 0.0
        self._inspect_duration: float = 2.4

        # Кольцевой пул пулевых отверстий (без лагов при стрельбе очередями!)
        self._decal_pool: list[Entity] = [
            Entity(
                parent=scene,
                model="quad",
                scale=0.075,
                color=rgb32(22, 20, 18),
                unlit=True,
                enabled=False,
                add_to_scene_entities=False,
            )
            for _ in range(self.MAX_DECAL_POOL)
        ]
        self._decal_cursor: int = 0
        self._cached_bot_ignore: list[Any] = []

        self.shots_fired: int = 0
        self.shots_hit: int = 0
        self.total_damage_dealt: int = 0

        self.equip("ak47", play_sound=False)

    def set_cached_bot_ignore(self, nodes: list[Any]) -> None:
        self._cached_bot_ignore = nodes

    def apply_skin_to_all(self, skin_idx: int) -> str:
        self.skin_idx = skin_idx % len(WEAPON_SKINS)
        for vm in self.models.values():
            vm.apply_skin(self.skin_idx)
        return str(WEAPON_SKINS[self.skin_idx]["name"])

    def cycle_weapon_skin(self) -> str:
        new_name = self.apply_skin_to_all(self.skin_idx + 1)
        self.sound_mgr.play_sfx("buy_item", volume=0.55, pitch=1.18)
        return new_name

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
        self.pivot.enabled = visible and not self.is_sniper_scoped and not self.player.third_person_mode

    def clear_zoom(self) -> None:
        self.scope_stage = 0
        self.player.zoom_fov_override = None
        if self.player.enabled and self.player.is_alive and not self.player.third_person_mode:
            self.pivot.enabled = True

    def grant_weapon(self, weapon_id: str) -> None:
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
        self.set_visible(self.player.enabled and self.player.is_alive)

        if play_sound:
            self.sound_mgr.play_sfx("empty_click", volume=0.45, pitch=1.18)

    def cycle_slot(self, delta: int) -> None:
        ordered: list[str] = []
        for wid in (*self.owned_primaries, *self.owned_secondaries, "zeus", "knife"):
            if wid not in ordered:
                ordered.append(wid)
        cur_idx = ordered.index(self.current_weapon_id) if self.current_weapon_id in ordered else 0
        self.equip(ordered[(cur_idx + delta) % len(ordered)])

    def start_inspect(self) -> None:
        if self.is_reloading or self.is_sniper_scoped:
            return
        self._inspect_timer = self._inspect_duration
        self.sound_mgr.play_sfx("empty_click", volume=0.32, pitch=1.35)

    def handle_alt_fire(self) -> None:
        if not self.player.enabled or not self.player.is_alive or self.is_reloading:
            return
        spec = self.active_spec

        if spec["is_melee"]:
            self.try_shoot(heavy_melee=True)
            return

        fovs = spec.get("scope_fovs", [])
        if fovs:
            self.scope_stage = (self.scope_stage + 1) % (len(fovs) + 1)
            if self.scope_stage == 0:
                self.clear_zoom()
            else:
                self.player.zoom_fov_override = float(fovs[self.scope_stage - 1])
                if self.current_weapon_id == "awp":
                    self.pivot.enabled = False
            self.sound_mgr.play_sfx("empty_click", volume=0.55, pitch=1.12)
            return

        if spec.get("supports_burst", False):
            wid = self.current_weapon_id
            self.burst_mode[wid] = not self.burst_mode[wid]
            mode_str = "3-ROUND BURST" if self.burst_mode[wid] else ("AUTO" if spec["automatic"] else "SEMI-AUTO")
            self.sound_mgr.play_sfx("empty_click", volume=0.55, pitch=1.28)
            if self.on_mode_notice is not None:
                self.on_mode_notice(f"{spec['display_name']}: {mode_str}")

    def cycle_grenade_type(self) -> None:
        idx = GRENADE_ORDER.index(self.selected_grenade)
        for step in range(1, len(GRENADE_ORDER) + 1):
            cand = GRENADE_ORDER[(idx + step) % len(GRENADE_ORDER)]
            if self.grenades.get(cand, 0) > 0:
                self.selected_grenade = cand
                self.sound_mgr.play_sfx("empty_click", volume=0.42, pitch=1.3)
                if self.on_mode_notice is not None:
                    self.on_mode_notice(f"GRENADE: {GRENADE_SPECS[cand]['name']}")
                return

    def try_throw_grenade(self) -> bool:
        if self.fx_mgr is None or self._grenade_throw_cooldown > 0.0:
            return False
        if self.grenades.get(self.selected_grenade, 0) <= 0:
            self.cycle_grenade_type()
            if self.grenades.get(self.selected_grenade, 0) <= 0:
                self.sound_mgr.play_sfx("empty_click", volume=0.5)
                return False

        g_type = self.selected_grenade
        self.grenades[g_type] -= 1
        self._grenade_throw_cooldown = 0.65
        origin = camera.world_position + camera.forward * 0.65 + Vec3(0.0, -0.08, 0.0)
        self.fx_mgr.throw_grenade(g_type, origin, camera.forward, self.player.current_velocity_approx)
        if self.grenades[g_type] <= 0:
            self.cycle_grenade_type()
        return True

    def start_reload(self) -> None:
        spec = self.active_spec
        if spec["is_melee"] or self.is_reloading:
            return
        wid = self.current_weapon_id
        mag_max = int(spec["mag_size"])
        if self.ammo_in_mag[wid] >= mag_max or self.ammo_reserve[wid] <= 0:
            return
        self.clear_zoom()
        self.is_reloading = True
        self._inspect_timer = 0.0
        self._reload_timer = float(spec["reload_time"])
        self.sound_mgr.play_sfx("reload", volume=0.72)

    def _finish_reload(self) -> None:
        wid = self.current_weapon_id
        spec = self.active_spec
        needed = int(spec["mag_size"]) - self.ammo_in_mag[wid]
        taken = min(needed, self.ammo_reserve[wid])
        self.ammo_in_mag[wid] += taken
        self.ammo_reserve[wid] -= taken
        self.is_reloading = False

    def get_total_spread(self) -> float:
        spec = self.active_spec
        if spec["is_melee"]:
            return 0.004
        base = float(spec.get("scoped_spread", spec["base_spread"])) if self.scope_stage > 0 else float(spec["base_spread"])
        spread = max(base, self.current_spread)
        if not self.player.grounded:
            spread += float(spec["jump_spread"])
        elif self.player.is_moving_horizontally:
            mult = 1.35 if self.player.is_sprinting else (0.55 if self.player.is_crouching else 1.0)
            spread += float(spec["move_spread"]) * mult
        elif self.player.is_crouching:
            spread *= 0.62
        if self.player.holding_breath:
            spread *= 0.35
        return clamp(spread, 0.0005, 0.22)

    def clear_decals(self) -> None:
        for dec in self._decal_pool:
            dec.enabled = False

    def _spawn_decal(self, point: Vec3, normal: Vec3) -> None:
        limit = int(self.settings.decal_shell_limit) if self.settings is not None else 48
        if limit <= 0:
            return
        cap = min(limit, self.MAX_DECAL_POOL)
        decal = self._decal_pool[self._decal_cursor % cap]
        self._decal_cursor = (self._decal_cursor + 1) % cap
        decal.position = point + normal * 0.015
        decal.look_at(point + normal * 2.0)
        decal.enabled = True

    def try_shoot(self, heavy_melee: bool = False) -> bool:
        if not self.player.enabled or not self.player.is_alive:
            return False
        if self.is_reloading or self._fire_cooldown > 0.0 or self._equip_cooldown > 0.0:
            return False

        wid = self.current_weapon_id
        spec = self.active_spec

        if not spec["is_melee"]:
            if self.ammo_in_mag[wid] <= 0:
                self.sound_mgr.play_sfx("empty_click", volume=0.65)
                self._fire_cooldown = 0.22
                self._burst_queue = 0
                if self.ammo_reserve[wid] > 0:
                    self.start_reload()
                return False
            self.ammo_in_mag[wid] -= 1

        self._inspect_timer = 0.0
        self._fire_cooldown = 0.72 if heavy_melee else float(spec["fire_interval"])
        self._shots_in_burst += 1
        if not spec["is_melee"]:
            self.shots_fired += 1

        self.sound_mgr.play_sfx(spec["shoot_sound"], volume=0.84, pitch=0.88 if heavy_melee else 1.0)
        if not spec.get("silenced", False) and self.on_loud_gunshot is not None:
            self.on_loud_gunshot(Vec3(self.player.world_position))

        is_zeus = bool(spec.get("is_zeus", False))
        if not spec["is_melee"] and not is_zeus:
            vm = self.active_model
            vm.muzzle_flash.enabled = True
            vm.muzzle_flash.rotation_z = random.uniform(0.0, 360.0)
            self._flash_timer = 0.048
            self._kick_back = 0.095 if wid != "awp" else 0.16
            self._kick_rot_x = -8.5 if wid != "awp" else -14.0
            self._bolt_offset = -0.055

            if self.fx_mgr is not None:
                mz_world = camera.world_position + camera.forward * 0.75 + camera.right * 0.22 - camera.up * 0.14
                self.fx_mgr.flash_world_light(mz_world, rgb=(1.0, 0.78, 0.36), intensity=2.2, duration=0.055)
                self.fx_mgr.spawn_shell_casing(mz_world, camera.right, camera.up, is_shotgun=(wid == "shotgun"))
        else:
            self._kick_back = -0.14 if heavy_melee else -0.10
            self._kick_rot_x = 24.0 if heavy_melee else 16.0

        pellets = int(spec.get("pellets", 1))
        spread = self.get_total_spread()
        max_dist = float(spec["range"])
        base_ignore = [self.player, self.pivot]
        hs_only_mode = self.settings is not None and self.settings.game_mode == "HEADSHOT_ONLY"

        any_enemy_hit = False
        best_hs = False
        killed_any = False
        victim_label = ""
        total_hit_dmg = 0
        hit_enemy_pos: Vec3 | None = None

        for pel_i in range(pellets):
            aim_dir = (
                camera.forward
                + camera.right * random.uniform(-spread, spread)
                + camera.up * random.uniform(-spread, spread)
            ).normalized()

            hit = raycast(camera.world_position, aim_dir, distance=max_dist, ignore=base_ignore)
            end_pt = camera.world_position + aim_dir * min(max_dist, 42.0)

            if hit.hit and hit.entity is not None:
                end_pt = Vec3(hit.world_point)
                hit_ent = hit.entity
                pen_mult = 1.0

                if getattr(hit_ent, "penetrable_wood", False) and float(spec["penetration"]) > 0.0:
                    if self.fx_mgr is not None:
                        self.fx_mgr.spawn_surface_impact(end_pt, Vec3(hit.world_normal), "wood")
                    self._spawn_decal(end_pt, Vec3(hit.world_normal))
                    prop_w = getattr(hit_ent, "destructible_ref", None)
                    if prop_w is not None and self.fx_mgr is not None:
                        prop_w.take_damage(int(spec["damage"]), on_wood_shatter=lambda p: self.fx_mgr.spawn_surface_impact(p, Vec3(0, 1, 0), "wood"))
                    hit2 = raycast(
                        end_pt + aim_dir * 0.28,
                        aim_dir,
                        distance=max(1.0, max_dist - hit.distance),
                        ignore=[*base_ignore, hit_ent],
                    )
                    if hit2.hit and hit2.entity is not None:
                        hit = hit2
                        hit_ent = hit2.entity
                        end_pt = Vec3(hit2.world_point)
                        pen_mult = float(spec["penetration"])
                    else:
                        hit_ent = None

                if hit_ent is not None:
                    enemy = getattr(hit_ent, "enemy_ref", None)
                    destructible = getattr(hit_ent, "destructible_ref", None)

                    if enemy is not None:
                        is_hs = bool(getattr(hit_ent, "is_headshot", False))
                        if hs_only_mode and not is_hs and not spec["is_melee"] and not is_zeus:
                            # В режиме ТОЛЬКО ХЕДШОТЫ попадание в корпус высекает искры на броне!
                            if self.fx_mgr is not None:
                                self.fx_mgr.spawn_surface_impact(end_pt, Vec3(hit.world_normal), "metal")
                        else:
                            if spec["is_melee"]:
                                if heavy_melee:
                                    behind = enemy.forward.dot(camera.forward) > 0.35
                                    dmg = int(spec["backstab_damage"] if behind else spec["heavy_damage"])
                                    is_hs = behind or is_hs
                                else:
                                    dmg = int(spec["damage"])
                            else:
                                dist_m = max(1.0, float(hit.distance))
                                fall = float(spec["falloff"]) ** (dist_m / 8.0)
                                raw = float(spec["damage"]) * (float(spec["headshot_mult"]) if is_hs else 1.0)
                                dmg = max(1, int(round(raw * fall * pen_mult)))

                            killed = enemy.take_damage(
                                dmg,
                                is_headshot=is_hs,
                                on_helmet_popped=(self.fx_mgr.spawn_flying_helmet if self.fx_mgr is not None else None),
                            )
                            any_enemy_hit = True
                            best_hs = best_hs or is_hs
                            killed_any = killed_any or killed
                            victim_label = enemy.bot_name
                            total_hit_dmg += dmg
                            hit_enemy_pos = Vec3(enemy.world_position)
                            if self.fx_mgr is not None:
                                self.fx_mgr.spawn_surface_impact(end_pt, Vec3(hit.world_normal), "electric" if is_zeus else "blood")
                            if killed and self.fx_mgr is not None and random.random() < (1.0 if enemy.role == "BOSS" else 0.65):
                                self.fx_mgr.spawn_loot_drop(enemy.world_position)
                    elif destructible is not None:
                        surf = getattr(hit_ent, "surface_type", "metal")
                        if self.fx_mgr is not None:
                            self.fx_mgr.spawn_surface_impact(end_pt, Vec3(hit.world_normal), surf)
                            destructible.take_damage(
                                int(spec["damage"]),
                                on_barrel_explode=lambda p: self.fx_mgr.trigger_explosion_vfx(p, radius=9.2, max_damage=112.0, source_label="BARREL"),
                                on_wood_shatter=lambda p: self.fx_mgr.spawn_surface_impact(p, Vec3(0, 1, 0), "wood"),
                            )
                    else:
                        surf = getattr(hit_ent, "surface_type", "stone")
                        if not spec["is_melee"]:
                            self._spawn_decal(end_pt, Vec3(hit.world_normal))
                        if self.fx_mgr is not None:
                            self.fx_mgr.spawn_surface_impact(end_pt, Vec3(hit.world_normal), "electric" if is_zeus else surf)

            if self.fx_mgr is not None and not spec["is_melee"]:
                mz_start = camera.world_position + camera.right * 0.18 - camera.up * 0.10 + camera.forward * 0.65
                if is_zeus:
                    self.fx_mgr.spawn_zeus_arc(mz_start, end_pt)
                elif pel_i % 2 == 0:
                    self.fx_mgr.spawn_tracer(mz_start, end_pt, is_sniper=(wid == "awp"))

        if any_enemy_hit:
            self.shots_hit += 1
            self.total_damage_dealt += total_hit_dmg
            self.sound_mgr.play_sfx("headshot" if best_hs else "hitmarker", volume=0.78)
            if self.fx_mgr is not None and hit_enemy_pos is not None:
                if self.settings is None or self.settings.show_damage_numbers:
                    self.fx_mgr.spawn_damage_popup(hit_enemy_pos + Vec3(0, 1.75, 0), total_hit_dmg, best_hs)
            if self.on_hit_enemy is not None:
                reward = 1000 if victim_label == "Усатый Эльдар" else int(spec["kill_reward"])
                self.on_hit_enemy(best_hs, killed_any, spec["display_name"], victim_label, reward)

        if not spec["is_melee"]:
            pitch_kick = float(spec["recoil_pitch"]) * min(1.85, 1.0 + self._shots_in_burst * 0.08)
            yaw_kick = random.uniform(-1.0, 1.0) * float(spec["recoil_yaw"])
            self.player.camera_pivot.rotation_x = clamp(self.player.camera_pivot.rotation_x - pitch_kick, -89.0, 89.0)
            self.player.rotation_y += yaw_kick
            self.current_spread = min(0.16, self.current_spread + 0.011)

            if wid == "awp" and self.scope_stage > 0:
                self.clear_zoom()

        return True

    def handle_input(self, key: str) -> None:
        if not self.player.enabled or not self.player.is_alive:
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
            self.equip("zeus" if self.current_weapon_id == "knife" else "knife")
        elif key == "4":
            self.equip("m4a1")
        elif key == "6":
            self.equip("awp")
        elif key == "7":
            self.equip("p90")
        elif key == "8":
            self.equip("shotgun")
        elif key == "9":
            self.equip("famas")
        elif key == "0":
            self.equip("usp")
        elif key == "scroll up":
            self.cycle_slot(-1)
        elif key == "scroll down":
            self.cycle_slot(1)
        elif key == "r":
            self.start_reload()
        elif key == "f":
            self.start_inspect()
        elif key == "g":
            self.try_throw_grenade()
        elif key == "v":
            self.cycle_grenade_type()
        elif key == "right mouse down":
            self.handle_alt_fire()
        elif key == "left mouse down":
            wid = self.current_weapon_id
            if self.burst_mode.get(wid, False):
                if self._burst_queue <= 0 and self._fire_cooldown <= 0.0:
                    self._burst_queue = 3
                    self._burst_timer = 0.0
            elif not self.active_spec["automatic"]:
                self.try_shoot()

    def update(self, dt: float) -> None:
        if not self.player.enabled or not self.player.is_alive:
            return

        self._fire_cooldown = max(0.0, self._fire_cooldown - dt)
        self._equip_cooldown = max(0.0, self._equip_cooldown - dt)
        self._grenade_throw_cooldown = max(0.0, self._grenade_throw_cooldown - dt)

        if self._flash_timer > 0.0:
            self._flash_timer -= dt
            if self._flash_timer <= 0.0:
                self.active_model.muzzle_flash.enabled = False

        if self.is_reloading:
            self._reload_timer -= dt
            if self._reload_timer <= 0.0:
                self._finish_reload()

        if self._burst_queue > 0:
            self._burst_timer -= dt
            if self._burst_timer <= 0.0 and self._fire_cooldown <= 0.0:
                if self.try_shoot():
                    self._burst_queue -= 1
                    self._burst_timer = 0.068
                else:
                    self._burst_queue = 0

        wid = self.current_weapon_id
        if self.active_spec["automatic"] and not self.burst_mode.get(wid, False) and held_keys["left mouse"]:
            self.try_shoot()
        elif not held_keys["left mouse"] and self._burst_queue <= 0:
            self._shots_in_burst = 0

        base_sp = float(self.active_spec["base_spread"])
        self.current_spread = lerp(self.current_spread, base_sp, min(1.0, dt * 8.5))

        vm = self.active_model
        base_pos = vm.base_pos
        self._kick_back = lerp(self._kick_back, 0.0, min(1.0, dt * 15.0))
        self._kick_rot_x = lerp(self._kick_rot_x, 0.0, min(1.0, dt * 14.0))
        self._bolt_offset = lerp(self._bolt_offset, 0.0, min(1.0, dt * 18.0))
        if vm.bolt_piece is not None:
            vm.bolt_piece.z = 0.04 + self._bolt_offset

        if self.player.grounded and self.player.is_moving_horizontally:
            freq = 12.5 if self.player.is_sprinting else 8.5
            amp = 0.015 if self.player.is_sprinting else 0.008
            self._sway_time += dt * freq
            bob_x = math.cos(self._sway_time * 0.5) * amp
            bob_y = abs(math.sin(self._sway_time)) * amp
        else:
            self._sway_time += dt * 1.9
            bob_x = math.cos(self._sway_time) * 0.0022
            bob_y = math.sin(self._sway_time * 2.0) * 0.0022

        reload_dip = -0.14 * math.sin(clamp(self._reload_timer / max(0.1, float(self.active_spec["reload_time"])), 0.0, 1.0) * math.pi) if self.is_reloading else 0.0
        reload_roll = 26.0 if self.is_reloading else 0.0

        insp_rot_y = 0.0
        insp_rot_z = 0.0
        insp_lift = 0.0
        if self._inspect_timer > 0.0:
            self._inspect_timer = max(0.0, self._inspect_timer - dt)
            p = 1.0 - (self._inspect_timer / self._inspect_duration)
            envelope = math.sin(p * math.pi)
            insp_lift = 0.045 * envelope
            if wid == "knife":
                insp_rot_x_bonus = p * 360.0
                insp_rot_z = 22.0 * envelope
                self._kick_rot_x = insp_rot_x_bonus
            else:
                insp_rot_y = -34.0 * math.sin(p * math.pi * 2.0) * envelope
                insp_rot_z = 24.0 * envelope

        vm.position = Vec3(
            base_pos.x + bob_x,
            base_pos.y - bob_y + reload_dip + insp_lift,
            base_pos.z - self._kick_back,
        )
        vm.rotation_x = self._kick_rot_x
        vm.rotation_y = insp_rot_y
        vm.rotation_z = reload_roll + insp_rot_z
