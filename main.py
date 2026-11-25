"""
Точка входа игры Counter-Strike 2 — 3D Tactical Realism Edition (Python 3.10–3.14 + Ursina 7.x/8.x).
Запускается СРАЗУ НА ПОЛНЫЙ ЭКРАН (с переключением по F11), включает 4x MSAA сглаживание,
попиксельное 3D-освещение и тени, 10 видов оружия, 4 вида гранат, бомбу C4, радар, экономику ($),
меню закупки (B), таблицу счёта (Tab), наклоны (Q/E), подкаты (Shift+Ctrl) и 4 класса ИИ-ботов.
"""

from __future__ import annotations

import math
import os
import random
import sys
from enum import Enum

from panda3d.core import loadPrcFileData

from src.settings import enable_windows_dpi_awareness

enable_windows_dpi_awareness()

# Конфигурация рендера до старта Ursina: offscreen для автотестов, 4x MSAA для 3D-реализма на ПК
if os.environ.get("CS2_HEADLESS") == "1" or "--self-test" in sys.argv:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null")
else:
    loadPrcFileData("", "framebuffer-multisample 1\nmultisamples 4")

from ursina import Ursina, Vec3, camera, clamp, held_keys, mouse, raycast, scene, time, window

from src.enemy import BOT_CALLSIGNS, EnemyBot, collect_bot_ignore_list
from src.fx import FXManager
from src.hud import CS2HUD
from src.map import ArenaMap
from src.menu import MenuManager
from src.player import CS2Player
from src.settings import (
    ASSETS_DIR,
    BUY_ITEMS,
    CROSSHAIR_PALETTE,
    WEAPON_SPECS,
    GameSettings,
    SoundManager,
    apply_fullscreen_mode,
    configure_ursina_asset_folder,
)
from src.weapon import WeaponManager


class GameState(str, Enum):
    MENU = "MENU"
    PLAYING = "PLAYING"
    ROUND_OVER = "ROUND_OVER"
    PAUSED = "PAUSED"


class CS2GameController:
    """Главный координатор 3D-мира, раундов, экономики ($), C4, спецэффектов, ботов и интерфейса."""

    def __init__(self) -> None:
        self.settings = GameSettings.load()
        self.sound_mgr = SoundManager(master_volume=self.settings.master_volume)

        # 1. Реалистичная 3D-арена с тенями, туманом, техникой и разрушаемыми объектами
        self.arena = ArenaMap(
            shadows_enabled=self.settings.shadows_enabled,
            time_of_day=self.settings.time_of_day,
        )

        # 2. Движок 3D-спецэффектов, гильз, гранат, дымов, огня, бомбы C4 и трофеев
        self.fx_mgr = FXManager(sound_mgr=self.sound_mgr)
        self.fx_mgr.on_explosion_damage = self._handle_explosion_damage
        self.fx_mgr.on_flashbang_pop = self._handle_flashbang_pop
        self.fx_mgr.on_fire_tick = self._handle_fire_tick
        self.fx_mgr.on_c4_exploded = self._handle_c4_exploded
        self.fx_mgr.on_c4_defused = self._handle_c4_defused

        # 3. Тактический игрок от первого лица (подкаты, наклоны Q/E, фонарь T, стимулятор X)
        self.player = CS2Player(
            settings=self.settings,
            sound_mgr=self.sound_mgr,
            on_death_callback=self._on_player_died,
            on_hurt_callback=self._on_player_hurt,
            position=tuple(self.arena.ct_spawn_pos),
        )
        self.player.enabled = False

        # 4. Арсенал из 10 видов оружия + 3D-перчатки + гранаты
        self.weapon_mgr = WeaponManager(
            player=self.player,
            sound_mgr=self.sound_mgr,
            fx_mgr=self.fx_mgr,
            on_hit_enemy=self._on_weapon_hit_enemy,
            on_loud_gunshot=self._on_player_loud_gunshot,
            on_mode_notice=lambda msg: self.hud.show_notice(msg),
        )
        self.weapon_mgr.set_visible(False)

        # 5. Расширенный боевой HUD (радар, прицел AWP, меню закупки B, таблица счёта Tab)
        self.hud = CS2HUD(on_buy_item=self.buy_item_by_id)
        self.hud.apply_crosshair_color(self.settings.crosshair_color_idx)
        self.hud.set_visible(False)

        # 6. Экраны Главного меню, Паузы и Настроек 3D
        self.menu = MenuManager(
            settings=self.settings,
            sound_mgr=self.sound_mgr,
            on_start_play=self.start_new_match,
            on_resume_play=self.resume_from_pause,
            on_restart_match=self.start_new_match,
            on_return_main_menu=self.return_to_main_menu,
            on_settings_applied=self._apply_live_settings,
        )

        # Состояние матча, экономики CS2 и статистики игрока
        self.state: GameState = GameState.MENU
        self._state_before_pause: GameState = GameState.PLAYING
        self.bots: list[EnemyBot] = []

        self.ct_score: int = 0
        self.t_score: int = 0
        self.round_number: int = 1
        self.round_time_left: float = float(self.settings.round_time_seconds)
        self._next_round_countdown: float = 0.0
        self._match_finished: bool = False
        self._menu_cam_angle: float = 0.0
        self._slowmo_timer: float = 0.0

        self.player_cash: int = 1600
        self.player_kills: int = 0
        self.player_deaths: int = 0
        self.player_headshots: int = 0
        self.kills_this_round: int = 0
        self._first_blood_done: bool = False

        self.return_to_main_menu()

    def _apply_live_settings(self) -> None:
        self.player.apply_sensitivity(self.settings.mouse_sensitivity)
        if self.player.zoom_fov_override is None and self.state != GameState.MENU:
            camera.fov = self.settings.fov
        self.arena.apply_atmosphere(self.settings.time_of_day, self.settings.shadows_enabled)
        self.hud.apply_crosshair_color(self.settings.crosshair_color_idx)
        for bot in self.bots:
            bot.difficulty = self.settings.bot_difficulty

    def _clear_bots(self) -> None:
        for bot in self.bots:
            bot.cleanup()
        self.bots.clear()

    def _spawn_bots_for_round(self) -> None:
        self._clear_bots()
        count = max(1, min(len(self.arena.t_spawn_points), int(self.settings.bot_count)))
        spawns = random.sample(self.arena.t_spawn_points, k=count)
        roles_cycle = ("RIFLE", "RUSHER", "SNIPER", "HEAVY", "RIFLE", "RUSHER", "RIFLE", "HEAVY", "SNIPER", "RIFLE")

        for idx, sp_pos in enumerate(spawns):
            callsign = BOT_CALLSIGNS[idx % len(BOT_CALLSIGNS)]
            role = roles_cycle[idx % len(roles_cycle)]
            bot = EnemyBot(
                bot_name=callsign,
                spawn_pos=sp_pos,
                waypoints=self.arena.patrol_waypoints,
                sound_mgr=self.sound_mgr,
                role=role,
                difficulty=self.settings.bot_difficulty,
                carries_c4=(idx == 0),
            )
            self.bots.append(bot)

    def _activate_fps_camera(self) -> None:
        self.player.enabled = True
        camera.parent = self.player.camera_pivot
        camera.position = Vec3(0.0, 0.0, 0.0)
        camera.rotation = Vec3(0.0, 0.0, 0.0)
        camera.fov = self.settings.fov
        mouse.locked = True
        mouse.visible = False

    def start_new_match(self) -> None:
        self.ct_score = 0
        self.t_score = 0
        self.round_number = 1
        self.player_cash = 1600
        self.player_kills = 0
        self.player_deaths = 0
        self.player_headshots = 0
        self.weapon_mgr.shots_fired = 0
        self.weapon_mgr.shots_hit = 0
        self.weapon_mgr.total_damage_dealt = 0
        self._match_finished = False
        self.hud.clear_killfeed()
        self.start_round()

    def start_round(self) -> None:
        self.weapon_mgr.clear_decals()
        self.fx_mgr.reset_round_fx()
        self.arena.reset_destructibles()

        self.player.respawn(self.arena.ct_spawn_pos, yaw=self.arena.ct_spawn_yaw)
        self.weapon_mgr.reset_all_ammo()
        self._spawn_bots_for_round()

        self.kills_this_round = 0
        self._first_blood_done = False
        self._slowmo_timer = 0.0
        self.round_time_left = float(self.settings.round_time_seconds)

        self.hud.buy_panel.enabled = False
        self.hud.hide_round_banner()
        self.hud.set_visible(True)
        self.weapon_mgr.set_visible(True)
        self._activate_fps_camera()
        self.state = GameState.PLAYING
        self.hud.show_notice(f"ROUND {self.round_number} START!  [B] BUY MENU   [G] GRENADES   [F] INSPECT", duration=3.0)

    def _end_round(self, ct_won: bool, reason: str) -> None:
        if self.state != GameState.PLAYING:
            return

        self.state = GameState.ROUND_OVER
        self.hud.buy_panel.enabled = False
        if self.player.enabled:
            mouse.locked = True
            mouse.visible = False

        if ct_won:
            self.ct_score += 1
            self.player_cash = min(16000, self.player_cash + 3250)
            self.sound_mgr.play_sfx("round_win", volume=0.88)
            headline = "COUNTER-TERRORISTS WIN"
        else:
            self.t_score += 1
            self.player_cash = min(16000, self.player_cash + 1900)
            self.sound_mgr.play_sfx("round_lose", volume=0.88)
            headline = "TERRORISTS WIN"

        target_wins = int(self.settings.rounds_to_win)
        if self.ct_score >= target_wins or self.t_score >= target_wins:
            self._match_finished = True
            champ = "ПОБЕДА СПЕЦНАЗА (CT)!" if self.ct_score > self.t_score else "ПОБЕДА ТЕРРОРИСТОВ (T)!"
            sub = f"{champ}  Счёт {self.ct_score} : {self.t_score}. Новый матч через 4 сек..."
            self._next_round_countdown = 4.2
        else:
            sub = f"{reason}   |   Следующий раунд через 3 сек..."
            self._next_round_countdown = 3.2

        self.hud.show_round_banner(headline, sub, ct_won=ct_won)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ЭКОНОМИКА И МЕНЮ ЗАКУПКИ СНАРЯЖЕНИЯ CS2 (КЛАВИША B)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def toggle_buy_menu(self) -> None:
        if self.state not in (GameState.PLAYING, GameState.ROUND_OVER) or not self.player.is_alive:
            return
        opening = not self.hud.buy_panel.enabled
        self.hud.buy_panel.enabled = opening
        if opening:
            self.weapon_mgr.clear_zoom()
            self.player.enabled = False
            mouse.locked = False
            mouse.visible = True
            self.sound_mgr.play_sfx("empty_click", volume=0.50, pitch=1.2)
        else:
            self._activate_fps_camera()

    def buy_item_by_id(self, item_id: str) -> bool:
        entry = next((it for it in BUY_ITEMS if it["id"] == item_id), None)
        if entry is None:
            return False
        price = int(entry["price"])
        if self.player_cash < price:
            self.sound_mgr.play_sfx("empty_click", volume=0.65, pitch=0.75)
            self.hud.show_notice(f"НЕДОСТАТОЧНО СРЕДСТВ! НУЖНО ${price}", duration=1.8)
            return False

        kind = entry["kind"]
        if kind == "weapon":
            self.player_cash -= price
            self.weapon_mgr.grant_weapon(item_id)
        elif item_id == "kevlar_helmet":
            if self.player.armor >= 100 and self.player.has_helmet:
                self.hud.show_notice("БРОНЯ И ШЛЕМ УЖЕ ПОЛНЫЕ (100%)", duration=1.6)
                return False
            self.player_cash -= price
            self.player.armor = 100
            self.player.has_helmet = True
        elif item_id == "defuse_stim":
            self.player_cash -= price
            self.player.has_defuse_kit = True
            self.player.stimshots += 1
        elif item_id == "smoke":
            self.player_cash -= price
            self.weapon_mgr.grant_grenade("smoke", 1)
            self.weapon_mgr.grant_grenade("molotov", 1)
        elif kind == "grenade":
            if not self.weapon_mgr.grant_grenade(item_id, 1):
                self.hud.show_notice("МАКСИМУМ ГРАНАТ ЭТОГО ТИПА", duration=1.6)
                return False
            self.player_cash -= price

        self.sound_mgr.play_sfx("buy_item", volume=0.82)
        self.hud.show_notice(f"КУПЛЕНО: {entry['label']} (-${price})", duration=1.8)
        return True

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ОБРАБОТЧИКИ БОЕВЫХ СОБЫТИЙ, ГРАНАТ, ВЗРЫВОВ И БОМБЫ C4
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _on_player_loud_gunshot(self, shooter_pos: Vec3) -> None:
        for bot in self.bots:
            bot.alert_by_gunshot(shooter_pos, radius=34.0)

    def _on_weapon_hit_enemy(
        self,
        is_headshot: bool,
        killed: bool,
        weapon_name: str,
        victim_name: str,
        kill_reward: int,
    ) -> None:
        self.hud.show_hitmarker(is_headshot=is_headshot)
        if not killed:
            return

        self.player_kills += 1
        self.kills_this_round += 1
        if is_headshot:
            self.player_headshots += 1

        bonus = kill_reward + (150 if is_headshot else 0)
        self.player_cash = min(16000, self.player_cash + bonus)
        self.hud.push_killfeed(weapon_name, victim_name, is_headshot)

        # Анонсер серий убийств CS2!
        streak_titles = {
            1: "FIRST BLOOD!" if not self._first_blood_done else "",
            2: "DOUBLE KILL!",
            3: "TRIPLE KILL!",
            4: "ULTRA KILL!",
            5: "ACE! TEAM WIPE!",
        }
        self._first_blood_done = True
        banner_txt = streak_titles.get(min(5, self.kills_this_round), "RAMPAGE!")
        if banner_txt:
            self.hud.show_killstreak_banner(f"★ {banner_txt} (+${bonus}) ★")
            self.sound_mgr.play_sfx("killstreak", volume=0.78)

        # Кинематографичное замедление времени на финальном фраге раунда!
        if all(b.state == "DEAD" for b in self.bots):
            self._slowmo_timer = 0.75

    def _handle_explosion_damage(
        self,
        center: Vec3,
        radius: float,
        max_damage: float,
        source_label: str,
    ) -> None:
        # Тряска экрана и радиальный урон по игроку
        plr_dist = (self.player.world_position + Vec3(0, 0.9, 0) - center).length()
        if plr_dist < radius * 1.65:
            shake = clamp(1.0 - plr_dist / (radius * 1.65), 0.12, 0.95)
            self.player.add_screen_shake(shake)
        if plr_dist <= radius and self.player.is_alive:
            falloff = max(0.0, 1.0 - plr_dist / radius) ** 1.35
            dmg = int(round(max_damage * 0.65 * falloff))
            if dmg >= 2:
                self.player.take_damage(dmg)

        # Радиальный урон по живым ботам
        for bot in self.bots:
            if bot.state == "DEAD":
                continue
            b_dist = (bot.world_position + Vec3(0, 0.9, 0) - center).length()
            if b_dist <= radius:
                falloff = max(0.0, 1.0 - b_dist / radius) ** 1.2
                dmg = max(5, int(round(max_damage * falloff)))
                killed = bot.take_damage(dmg, is_headshot=False)
                self.weapon_mgr.total_damage_dealt += dmg
                if self.settings.show_damage_numbers:
                    self.fx_mgr.spawn_damage_popup(bot.world_position + Vec3(0, 1.6, 0), dmg)
                if killed:
                    self._on_weapon_hit_enemy(False, True, source_label, bot.bot_name, 300)

        # Цепная детонация соседних бочек и разрушение деревянных ящиков!
        for prop in self.arena.destructibles:
            if not prop.alive:
                continue
            p_dist = (prop.pos - center).length()
            if 0.25 < p_dist <= radius * 0.78:
                prop.take_damage(
                    90,
                    on_barrel_explode=lambda p: self.fx_mgr.trigger_explosion_vfx(p, radius=9.0, source_label="CHAIN BARREL"),
                    on_wood_shatter=lambda p: self.fx_mgr.spawn_surface_impact(p, Vec3(0, 1, 0), "wood"),
                )

    def _handle_flashbang_pop(self, flash_pos: Vec3) -> None:
        ignore_bots = [self.player, *collect_bot_ignore_list(self.bots)]

        # 1. Расчёт ослепления игрока с учётом угла взгляда (отвернулся на 180° — почти не ослепило!)
        cam_pos = camera.world_position
        to_flash = flash_pos - cam_pos
        dist = to_flash.length()
        if dist <= 26.0:
            wall_check = raycast(cam_pos, to_flash.normalized(), distance=max(0.2, dist - 0.3), ignore=ignore_bots)
            if not wall_check.hit:
                look_dot = camera.forward.dot(to_flash.normalized())  # +1 смотрим прямо, -1 спиной
                angle_factor = 0.16 if look_dot < -0.15 else (0.48 if look_dot < 0.35 else 1.0)
                dist_factor = clamp(1.15 - dist / 26.0, 0.2, 1.0)
                self.hud.trigger_flashbang(angle_factor * dist_factor)

        # 2. Ослепление ботов поблизости
        for bot in self.bots:
            if bot.state == "DEAD":
                continue
            eye = bot.world_position + Vec3(0, 1.6, 0)
            b_vec = flash_pos - eye
            b_dist = b_vec.length()
            if b_dist <= 19.0:
                occ = raycast(eye, b_vec.normalized(), distance=max(0.2, b_dist - 0.3), ignore=ignore_bots)
                if not occ.hit:
                    bot.apply_flash_blindness(3.8 * clamp(1.1 - b_dist / 20.0, 0.35, 1.0))

    def _handle_fire_tick(self, fire_center: Vec3, radius: float) -> None:
        if self.player.is_alive:
            p_flat = Vec3(self.player.x - fire_center.x, 0.0, self.player.z - fire_center.z)
            if p_flat.length() <= radius and abs(self.player.y - fire_center.y) < 1.6:
                self.player.take_damage(7)

        for bot in self.bots:
            if bot.state == "DEAD":
                continue
            b_flat = Vec3(bot.x - fire_center.x, 0.0, bot.z - fire_center.z)
            if b_flat.length() <= radius and abs(bot.y - fire_center.y) < 1.6:
                killed = bot.take_damage(12, is_headshot=False)
                self.weapon_mgr.total_damage_dealt += 12
                if killed:
                    self._on_weapon_hit_enemy(False, True, "MOLOTOV", bot.bot_name, 300)

    def _try_bot_plant_c4(self, bot_pos: Vec3) -> bool:
        if self.fx_mgr.c4_planted or self.state != GameState.PLAYING:
            return False
        site = self.arena.get_nearest_bomb_site(bot_pos)
        if site is None:
            return False
        site_center = self.arena.site_a_center if site == "A" else self.arena.site_b_center
        self.fx_mgr.plant_c4(site_center, site_name=site)
        self.hud.show_notice(f"⚠ ТЕРРОРИСТЫ ЗАЛОЖИЛИ БОМБУ НА ТОЧКЕ {site}!", duration=3.5)
        return True

    def _handle_c4_exploded(self) -> None:
        if self.state == GameState.PLAYING:
            self._end_round(ct_won=False, reason=f"БОМБА C4 ВЗОРВАЛАСЬ НА ТОЧКЕ {self.fx_mgr.c4_site_name}!")

    def _handle_c4_defused(self) -> None:
        self.player_cash = min(16000, self.player_cash + 800)
        if self.state == GameState.PLAYING:
            self._end_round(ct_won=True, reason="БОМБА C4 УСПЕШНО ОБЕЗВРЕЖЕНА (+$800)!")

    def _check_loot_pickups(self) -> None:
        if not self.player.is_alive or not self.fx_mgr.loot_drops:
            return
        kept = []
        for ld in self.fx_mgr.loot_drops:
            if (ld.pos - self.player.world_position).length() <= 1.65:
                if ld.kind == "medkit":
                    self.player.hp = min(self.player.max_hp, self.player.hp + 28)
                    self.hud.flash_heal()
                    self.hud.show_notice("ПОДОБРАНА АПТЕЧКА (+28 HP)", duration=1.5)
                elif ld.kind == "armor":
                    self.player.armor = min(self.player.max_armor, self.player.armor + 30)
                    self.hud.show_notice("ПОДОБРАНА БРОНЕПЛАСТИНА (+30 ARMOR)", duration=1.5)
                elif ld.kind == "ammo":
                    wid = self.weapon_mgr.current_weapon_id
                    spec = WEAPON_SPECS[wid]
                    if not spec["is_melee"]:
                        self.weapon_mgr.ammo_reserve[wid] = min(
                            int(spec["reserve_max"]) * 2,
                            self.weapon_mgr.ammo_reserve[wid] + int(spec["mag_size"]),
                        )
                    self.hud.show_notice("ПОДОБРАН БОЕКОМПЛЕКТ (+ПАТРОНЫ)", duration=1.5)
                else:
                    self.player_cash = min(16000, self.player_cash + 250)
                    self.hud.show_notice("ПОДОБРАНА НАГРАДА (+$250)", duration=1.5)
                self.sound_mgr.play_sfx("buy_item", volume=0.65, pitch=1.22)
                from ursina import destroy

                destroy(ld.entity)
            else:
                kept.append(ld)
        self.fx_mgr.loot_drops = kept

    def pause_game(self) -> None:
        if self.state not in (GameState.PLAYING, GameState.ROUND_OVER):
            return
        self.hud.buy_panel.enabled = False
        self.weapon_mgr.clear_zoom()
        self._state_before_pause = self.state
        self.state = GameState.PAUSED
        self.player.enabled = False
        self.weapon_mgr.set_visible(False)
        self.hud.set_visible(False)
        self.menu.show_pause_menu()

    def resume_from_pause(self) -> None:
        if self.state != GameState.PAUSED:
            return
        self.menu.hide_all()
        self.hud.set_visible(True)
        self.weapon_mgr.set_visible(True)
        self._activate_fps_camera()
        self.state = self._state_before_pause

    def return_to_main_menu(self) -> None:
        self._clear_bots()
        self.weapon_mgr.clear_decals()
        self.fx_mgr.reset_round_fx()
        self.player.enabled = False
        self.weapon_mgr.set_visible(False)
        self.hud.hide_round_banner()
        self.hud.set_visible(False)

        camera.parent = scene
        camera.rotation_z = 0.0
        camera.fov = 78.0
        self.state = GameState.MENU
        self.menu.show_main_menu()

    def _on_player_hurt(self) -> None:
        self.hud.flash_damage()

    def _on_player_died(self) -> None:
        self.player_deaths += 1
        if self.state == GameState.PLAYING:
            self._end_round(ct_won=False, reason="ВЫ ПАЛИ В ПЕРЕСТРЕЛКЕ")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ГОРЯЧИЕ КЛАВИШИ (F11 FULLSCREEN, F6 SKY, F7 CROSSHAIR, B BUY, T, X, Z, 5)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def handle_input(self, key: str) -> None:
        # F11 — мгновенное переключение Полноэкранного режима в любой момент!
        if key == "f11":
            self.settings.fullscreen = not self.settings.fullscreen
            apply_fullscreen_mode(self.settings.fullscreen)
            self.menu.refresh_toggle_labels()
            self.settings.save()
            if self.hud.root.enabled:
                mode_s = "ON" if self.settings.fullscreen else "OFF"
                self.hud.show_notice(f"FULLSCREEN MODE: {mode_s}")
            return

        # F6 — смена времени суток и освещения на лету (DAY / SUNSET / NIGHT)
        if key == "f6":
            new_tod = self.arena.cycle_time_of_day()
            self.settings.time_of_day = new_tod
            self.menu.refresh_toggle_labels()
            self.settings.save()
            if self.hud.root.enabled:
                self.hud.show_notice(f"3D ATMOSPHERE: {new_tod}")
            return

        # F7 — смена цвета динамического прицела CS2
        if key == "f7":
            self.settings.crosshair_color_idx = (self.settings.crosshair_color_idx + 1) % len(CROSSHAIR_PALETTE)
            cname = self.hud.apply_crosshair_color(self.settings.crosshair_color_idx)
            self.settings.save()
            if self.hud.root.enabled:
                self.hud.show_notice(f"CROSSHAIR COLOR: {cname}")
            return

        if key == "escape":
            if self.hud.buy_panel.enabled:
                self.toggle_buy_menu()
                return
            if self.state in (GameState.PLAYING, GameState.ROUND_OVER):
                self.pause_game()
            elif self.state == GameState.PAUSED:
                if self.menu.settings_panel.enabled:
                    self.menu.close_settings()
                else:
                    self.resume_from_pause()
            elif self.state == GameState.MENU and self.menu.settings_panel.enabled:
                self.menu.close_settings()
            return

        if self.state not in (GameState.PLAYING, GameState.ROUND_OVER):
            return

        if key == "b":
            self.toggle_buy_menu()
            return

        if self.hud.buy_panel.enabled:
            return

        if key == "t":
            state_on = self.player.toggle_flashlight()
            self.hud.show_notice(f"3D FLASHLIGHT: {'ON' if state_on else 'OFF'}", duration=1.4)
            return

        if key == "x":
            if self.player.use_stimshot():
                self.hud.flash_heal()
                self.hud.show_notice("COMBAT STIMSHOT USED (+35 HP & STAMINA)!", duration=1.8)
            else:
                self.hud.show_notice("STIMSHOT UNAVAILABLE (FULL HP OR 0 LEFT)", duration=1.5)
            return

        if key in ("z", "middle mouse down"):
            ignore_all = [self.player, self.weapon_mgr.pivot, *collect_bot_ignore_list(self.bots)]
            self.fx_mgr.place_tactical_ping(camera.world_position, camera.forward, ignore_all)
            return

        # Клавиша 5: тренировочная установка C4 на точке A/B, если бомба ещё не заложена
        if key == "5" and not self.fx_mgr.c4_planted and self.state == GameState.PLAYING:
            site = self.arena.get_nearest_bomb_site(self.player.world_position)
            if site is not None:
                self.fx_mgr.plant_c4(self.player.world_position, site_name=site)
                self.hud.show_notice(f"C4 PLANTED AT SITE {site}! HOLD [E] TO PRACTICE DEFUSE!", duration=3.0)
            else:
                self.hud.show_notice("ДОЙДИТЕ ДО ЗОНЫ [SITE A] ИЛИ [SITE B] ДЛЯ ЗАКЛАДКИ C4", duration=2.0)
            return

        self.weapon_mgr.handle_input(key)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ГЛАВНЫЙ ИГРОВОЙ ЦИКЛ UPDATE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def update(self) -> None:
        raw_dt = min(float(time.dt), 0.05)
        self.arena.update_environment(raw_dt)

        # Живой панорамный 3D-облёт арены в Главном меню
        if self.state == GameState.MENU:
            self._menu_cam_angle += raw_dt * 0.14
            radius = 25.0
            camera.position = Vec3(
                math.sin(self._menu_cam_angle) * radius,
                12.5,
                math.cos(self._menu_cam_angle) * radius,
            )
            camera.look_at(Vec3(0.0, 1.8, 0.0))
            return

        if self.state == GameState.PAUSED:
            return

        if self._slowmo_timer > 0.0:
            self._slowmo_timer = max(0.0, self._slowmo_timer - raw_dt)
            dt = raw_dt * 0.35
        else:
            dt = raw_dt

        ignore_bots = [self.player, *collect_bot_ignore_list(self.bots)]
        self.weapon_mgr.update(dt)
        self.fx_mgr.update(dt, ignore_bots)
        self.hud.update(raw_dt)
        self._check_loot_pickups()

        # Таблица счёта при удержании Tab
        self.hud.scoreboard_panel.enabled = bool(held_keys["tab"]) and not self.hud.buy_panel.enabled
        if self.hud.scoreboard_panel.enabled:
            self.hud.update_scoreboard(
                ct_score=self.ct_score,
                t_score=self.t_score,
                player_kills=self.player_kills,
                player_deaths=self.player_deaths,
                player_hs=self.player_headshots,
                shots_fired=self.weapon_mgr.shots_fired,
                shots_hit=self.weapon_mgr.shots_hit,
                total_dmg=self.weapon_mgr.total_damage_dealt,
                cash=self.player_cash,
                bots=self.bots,
            )

        # Обновление ИИ живых ботов (с учётом дымовых завес и закладки C4!)
        alive_bots_count = 0
        for bot in self.bots:
            if bot.state != "DEAD":
                alive_bots_count += 1
                if self.state == GameState.PLAYING:
                    bot.update_ai(
                        dt,
                        self.player,
                        ignore_bots,
                        smoke_blocker_fn=self.fx_mgr.is_segment_blocked_by_smoke,
                        on_try_plant_c4=self._try_bot_plant_c4,
                    )

        # Прогресс обезвреживания C4 по удержанию клавиши E рядом с бомбой
        defuse_prog = 0.0
        if self.state == GameState.PLAYING and self.fx_mgr.c4_planted and self.player.is_alive:
            defuse_prog = self.fx_mgr.step_defuse(
                dt=raw_dt,
                player_pos=self.player.world_position,
                has_defuse_kit=self.player.has_defuse_kit,
                holding_use=bool(held_keys["e"]),
            )

        # Условия победы / поражения в раунде
        if self.state == GameState.PLAYING:
            if not self.fx_mgr.c4_planted:
                self.round_time_left -= dt
                if alive_bots_count == 0:
                    self._end_round(ct_won=True, reason="ВСЕ ВРАГИ ЛИКВИДИРОВАНЫ")
                elif self.round_time_left <= 0.0:
                    self.round_time_left = 0.0
                    self._end_round(ct_won=True, reason="ВРЕМЯ РАУНДА ВЫШЛО — ТОЧКИ A И B ЗАЩИЩЕНЫ")

        elif self.state == GameState.ROUND_OVER:
            self._next_round_countdown -= raw_dt
            if self._next_round_countdown <= 0.0:
                if self._match_finished:
                    self.start_new_match()
                else:
                    self.round_number += 1
                    self.start_round()

        # Обновление 2D радара и всех индикаторов HUD
        self.hud.update_radar(
            player_pos=self.player.world_position,
            player_yaw=self.player.rotation_y,
            site_a=self.arena.site_a_center,
            site_b=self.arena.site_b_center,
            bots=self.bots,
            c4_planted=self.fx_mgr.c4_planted,
            c4_pos=self.fx_mgr.c4_pos,
            ping_pos=self.fx_mgr.ping_pos,
        )

        wid = self.weapon_mgr.current_weapon_id
        self.hud.sync_stats(
            hp=self.player.hp,
            armor=self.player.armor,
            weapon_id=wid,
            weapon_display_name=self.weapon_mgr.active_spec["display_name"],
            ammo_mag=self.weapon_mgr.ammo_in_mag[wid],
            ammo_reserve=self.weapon_mgr.ammo_reserve[wid],
            is_reloading=self.weapon_mgr.is_reloading,
            ct_score=self.ct_score,
            t_score=self.t_score,
            round_num=self.round_number,
            time_left=self.round_time_left,
            alive_bots=alive_bots_count,
            spread=self.weapon_mgr.get_total_spread(),
            cash=self.player_cash,
            grenades=self.weapon_mgr.grenades,
            selected_grenade=self.weapon_mgr.selected_grenade,
            stimshots=self.player.stimshots,
            flashlight_on=self.player.flashlight_on,
            is_scoped=self.weapon_mgr.is_sniper_scoped,
            burst_active=self.weapon_mgr.burst_mode.get(wid, False),
            c4_planted=self.fx_mgr.c4_planted,
            c4_site=self.fx_mgr.c4_site_name,
            c4_timer=self.fx_mgr.c4_timer,
            defuse_progress=defuse_prog,
        )


_GAME: CS2GameController | None = None


def update() -> None:
    if _GAME is not None:
        _GAME.update()


def input(key: str) -> None:
    if _GAME is not None:
        _GAME.handle_input(key)


def bootstrap_assets_if_needed() -> None:
    models_dir = ASSETS_DIR / "models"
    required = ("ak47.glb", "awp.glb", "mp9.glb", "shotgun.glb", "c4.glb", "barrel.glb")
    if not models_dir.is_dir() or any(not (models_dir / name).is_file() for name in required):
        try:
            from generate_assets import ensure_all_starter_assets

            ensure_all_starter_assets()
        except Exception:
            pass


def main(headless: bool = False) -> tuple[Ursina, CS2GameController]:
    global _GAME

    configure_ursina_asset_folder()
    bootstrap_assets_if_needed()

    initial_settings = GameSettings.load()

    if headless or os.environ.get("CS2_HEADLESS") == "1":
        app = Ursina(window_type="none")
    else:
        app = Ursina(
            title="Counter-Strike 2 — 3D Realism Edition",
            borderless=bool(initial_settings.fullscreen),
            fullscreen=bool(initial_settings.fullscreen),
            vsync=True,
            development_mode=False,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True
        apply_fullscreen_mode(bool(initial_settings.fullscreen))

    _GAME = CS2GameController()
    return app, _GAME


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        os.environ["CS2_HEADLESS"] = "1"
        test_app, test_ctrl = main(headless=True)
        test_ctrl.start_new_match()
        time.dt = 0.016
        for _ in range(8):
            test_ctrl.update()
        print("SELF-TEST PASSED! Frozen:", getattr(sys, "frozen", False))
        sys.exit(0)

    ursina_app, _ = main(headless=False)
    ursina_app.run()
