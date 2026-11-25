"""
Точка входа игры Counter-Strike 2 — 3D Tactical Realism Edition (Python 3.10–3.14 + Ursina 7.x/8.x).

ПОЛНАЯ ВЕРСИЯ TURN 6:
- Кинематографичная анимированная заставка «Игра сделана уважаемым алкодимасом, для усатого Эльдара»
  (с фанфарой, искрами, неоновым сканлайном и эффектом печатной машинки; повтор по кнопке из меню).
- Живой 3D-оперативник спецназа на подиуме в Главном меню Panorama UI (Меню × Оружие × Скин).
- ВСЕ 15 настроек графики применяются в реальном времени (пресеты LOW/MEDIUM/HIGH/ULTRA, тени 0..4096,
  шейдеры FLAT/LIT/PBR, анизотропия 1..16x, дальность прорисовки, туман, яркость, частицы, декали,
  динамический свет, время суток, детали неба, лимит FPS, VSync, FOV, полный экран).
- 4 игровых режима: CLASSIC (захват точек C4), DEATHMATCH (мясорубка с возрождениями),
  HEADSHOT_ONLY (только хедшоты наносят урон!) и BOSS_ELDAR (рейд-босс «Усатый Эльдар» с золотыми усами).
- Система званий и XP-прогрессии (Silver Elite → Global Elite • Уважаемый) с сохранением в профиль.
- 12 видов оружия, 6 PBR-скинов (F8), 4 вида гранат, бомба C4, экономика ($), радар с дымами,
  телеметрия F3, вид от 3-го лица F5, рация C, и десятки других фич!
"""

from __future__ import annotations

import math
import os
import random
import sys
from enum import Enum
from typing import Any

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
from src.player import CS2Player, MenuOperatorShowcase
from src.settings import (
    ASSETS_DIR,
    BUY_ITEMS,
    CROSSHAIR_PALETTE,
    RADIO_CALLOUTS,
    WEAPON_SKINS,
    WEAPON_SPECS,
    GameSettings,
    SoundManager,
    apply_fps_limit,
    apply_fullscreen_mode,
    configure_ursina_asset_folder,
)
from src.splash import IntroSplashScreen
from src.weapon import WeaponManager


class GameState(str, Enum):
    SPLASH = "SPLASH"
    MENU = "MENU"
    PLAYING = "PLAYING"
    ROUND_OVER = "ROUND_OVER"
    PAUSED = "PAUSED"


DEATHMATCH_RESPAWN_DELAY: float = 3.0
DEATHMATCH_BOT_RESPAWN_DELAY: float = 4.5
DEATHMATCH_KILL_LIMIT: int = 30
DM_RESPAWN_POINTS: tuple[Vec3, ...] = (
    Vec3(0.0, 0.05, -24.5),
    Vec3(-7.5, 0.05, -21.0),
    Vec3(7.5, 0.05, -21.0),
    Vec3(-12.0, 0.05, -12.5),
    Vec3(12.0, 0.05, -12.5),
    Vec3(-14.0, 0.05, 0.0),
    Vec3(14.0, 0.05, 0.0),
)

ROLE_CYCLE: tuple[str, ...] = (
    "RIFLE",
    "RUSHER",
    "SNIPER",
    "HEAVY",
    "RIFLE",
    "RUSHER",
    "RIFLE",
    "HEAVY",
    "SNIPER",
    "RIFLE",
)


class CS2GameController:
    """Главный координатор 3D-мира, заставки, 4 режимов, XP-званий, экономики ($), C4, ботов и Panorama UI."""

    def __init__(self) -> None:
        self.settings = GameSettings.load()
        self.sound_mgr = SoundManager(master_volume=self.settings.master_volume, music_volume=self.settings.music_volume)

        # 1. Реалистичная 3D-арена — все 15 настроек графики применяются конструктором!
        self.arena = ArenaMap(settings=self.settings)

        # 2. Движок 3D-спецэффектов: гильзы, трассеры, гранаты, дымы, огонь, C4 и трофеи
        self.fx_mgr = FXManager(sound_mgr=self.sound_mgr, settings=self.settings)
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
        self.player.fp_legs_rig.enabled = False  # Прячем ноги игрока во время заставки и меню

        # 4. Арсенал из 12 видов оружия + 3D-перчатки + 4 вида гранат (12 уникальных TTX)
        self.weapon_mgr = WeaponManager(
            player=self.player,
            sound_mgr=self.sound_mgr,
            settings=self.settings,
            fx_mgr=self.fx_mgr,
            on_hit_enemy=self._on_weapon_hit_enemy,
            on_loud_gunshot=self._on_player_loud_gunshot,
            on_mode_notice=lambda msg: self.hud.show_notice(msg),
        )
        self.weapon_mgr.set_visible(False)

        # 5. Расширенный Panorama HUD (радар с дымами, прицел AWP, закупка B, таблица Tab, телеметрия F3)
        self.hud = CS2HUD(settings=self.settings, on_buy_item=self.buy_item_by_id)
        self.hud.apply_crosshair_color(self.settings.crosshair_color_idx)
        self.hud.set_visible(False)

        # 6. Живой 3D-оперативник CT на подиуме в Главном меню (с оружием и текущим скином!)
        self.showcase = MenuOperatorShowcase(self.arena.menu_podium_pos)
        self.showcase.set_showcase_loadout("ak47", self.settings.weapon_skin_idx)
        self.showcase.set_visible(False)

        # 7. Экраны Главного меню, Паузы и 3-вкладочных Настроек (15 графических + геймплей)
        self.menu = MenuManager(
            settings=self.settings,
            sound_mgr=self.sound_mgr,
            on_start_play=self.start_new_match,
            on_resume_play=self.resume_from_pause,
            on_restart_match=self.start_new_match,
            on_return_main_menu=self.return_to_main_menu,
            on_settings_applied=self._apply_live_settings,
            on_replay_splash=self._replay_splash,
            on_showcase_changed=self._on_showcase_changed,
        )

        # 8. Кинематографичная анимированная заставка с фанфарой!
        self.splash = IntroSplashScreen(self.sound_mgr, on_finished=self._on_splash_finished)

        # Состояние матча, экономики CS2, XP-прогрессии и статистики игрока
        self.state: GameState = GameState.SPLASH
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
        self._xp_gained_this_match: int = 0
        self._rank_at_match_start: str = self.settings.get_rank_title()

        # Состояния возрождения Deathmatch
        self._dm_bot_respawn_queue: list[tuple[float, EnemyBot]] = []
        self._dm_player_respawn_timer: float = 0.0

        # Телеметрия графики (F3)
        self._telemetry_accum: float = 0.0

        self._enter_splash()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # КИНЕМАТОГРАФИЧНАЯ ЗАСТАВКА (СТАРТ И ПОВТОР ИЗ МЕНЮ)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _enter_splash(self) -> None:
        self.state = GameState.SPLASH
        self.menu.hide_all()
        self.showcase.set_visible(False)
        self.hud.set_visible(False)
        self.weapon_mgr.set_visible(False)
        self.player.enabled = False
        camera.parent = scene
        camera.rotation = Vec3(0.0, 0.0, 0.0)
        camera.fov = 70.0
        self.splash.start()

    def _replay_splash(self) -> None:
        """Повтор заставки по кнопке из Главного меню (доступно всегда!)."""
        if self.state == GameState.SPLASH:
            return
        self.sound_mgr.stop_menu_music()
        self._enter_splash()

    def _on_splash_finished(self) -> None:
        self._enter_main_menu()

    def _enter_main_menu(self) -> None:
        self._clear_bots()
        self.weapon_mgr.clear_decals()
        self.fx_mgr.reset_round_fx()
        self.player.enabled = False
        self.player.fp_legs_rig.enabled = False
        self.weapon_mgr.set_visible(False)
        self.hud.hide_round_banner()
        self.hud.set_visible(False)
        self.showcase.set_visible(True)
        self.showcase.set_showcase_loadout("ak47", self.settings.weapon_skin_idx)

        camera.parent = scene
        camera.rotation_z = 0.0
        camera.fov = 78.0
        self._menu_cam_angle = 0.0
        self.state = GameState.MENU
        self.menu.show_main_menu()

    def _on_showcase_changed(self, weapon_id: str, skin_idx: int) -> None:
        """Синхронизация оружия/скина живого оперативника на подиуме с выбором в меню."""
        self.showcase.set_showcase_loadout(weapon_id, skin_idx)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ЖИВОЕ ПРИМЕНЕНИЕ ВСЕХ 15 ГРАФИЧЕСКИХ НАСТРОЕК
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _apply_live_settings(self) -> None:
        self.arena.apply_graphics_settings(self.settings)  # Все 15 настроек графики!
        apply_fps_limit(self.settings.fps_limit, self.settings.vsync_enabled)
        self.player.apply_sensitivity(self.settings.mouse_sensitivity)
        if self.player.zoom_fov_override is None and self.state not in (GameState.MENU, GameState.SPLASH):
            camera.fov = self.settings.fov
        self.hud.apply_crosshair_color(self.settings.crosshair_color_idx)
        self.sound_mgr.set_volumes(self.settings.master_volume, self.settings.music_volume)
        for bot in self.bots:
            bot.difficulty = self.settings.bot_difficulty

    def _clear_bots(self) -> None:
        for bot in self.bots:
            bot.cleanup()
        self.bots.clear()
        self._dm_bot_respawn_queue.clear()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # СПАВН БОТОВ С УЧЁТОМ 4 ИГРОВЫХ РЕЖИМОВ (+ РЕЙД-БОСС!)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _spawn_bots_for_round(self) -> None:
        self._clear_bots()
        mode = self.settings.game_mode
        count = max(1, min(len(self.arena.t_spawn_points), int(self.settings.bot_count)))
        spawns = random.sample(self.arena.t_spawn_points, k=count)

        if mode == "BOSS_ELDAR":
            # РЕЙД-БОСС «УСАТЫЙ ЭЛЬДАР» + свита из 2 телохранителей!
            boss_spawn = spawns[0]
            boss = EnemyBot(
                bot_name="Усатый Эльдар",
                spawn_pos=boss_spawn,
                waypoints=self.arena.patrol_waypoints,
                sound_mgr=self.sound_mgr,
                role="BOSS",
                difficulty="HARD" if self.settings.bot_difficulty == "EASY" else self.settings.bot_difficulty,
                carries_c4=False,
            )
            self.bots.append(boss)
            guard_roles = ("HEAVY", "RUSHER", "RIFLE")
            for idx, sp_pos in enumerate(spawns[1:4]):
                self.bots.append(
                    EnemyBot(
                        bot_name=f"Охрана-{idx + 1}",
                        spawn_pos=sp_pos,
                        waypoints=self.arena.patrol_waypoints,
                        sound_mgr=self.sound_mgr,
                        role=guard_roles[idx % len(guard_roles)],
                        difficulty=self.settings.bot_difficulty,
                        carries_c4=False,
                    )
                )
        else:
            for idx, sp_pos in enumerate(spawns):
                callsign = BOT_CALLSIGNS[idx % len(BOT_CALLSIGNS)]
                role = ROLE_CYCLE[idx % len(ROLE_CYCLE)]
                bot = EnemyBot(
                    bot_name=callsign,
                    spawn_pos=sp_pos,
                    waypoints=self.arena.patrol_waypoints,
                    sound_mgr=self.sound_mgr,
                    role=role,
                    difficulty=self.settings.bot_difficulty,
                    carries_c4=(idx == 0 and mode != "DEATHMATCH"),
                )
                self.bots.append(bot)

        if mode == "BOSS_ELDAR":
            self.hud.show_notice("⚠ РЕЙД-БОСС «УСАТЫЙ ЭЛЬДАР» НА АРЕНЕ! УБЕЙТЕ ЕГО И СВИТУ!", duration=4.0)
        elif mode == "HEADSHOT_ONLY":
            self.hud.show_notice("РЕЖИМ HEADSHOT ONLY: УРОН ТОЛЬКО В ГОЛОВУ!", duration=3.2)
        elif mode == "DEATHMATCH":
            self.hud.show_notice(f"DEATHMATCH: ПЕРВЫЙ ДО {DEATHMATCH_KILL_LIMIT} ФРАГОВ! ВОЗРОЖДЕНИЯ ВКЛЮЧЕНЫ", duration=3.6)

    def _activate_fps_camera(self) -> None:
        self.player.enabled = True
        self.player.fp_legs_rig.enabled = not self.player.third_person_mode
        camera.parent = self.player.camera_pivot
        camera.position = Vec3(0.0, 0.0, 0.0)
        camera.rotation = Vec3(0.0, 0.0, 0.0)
        camera.fov = self.settings.fov
        mouse.locked = True
        mouse.visible = False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # МАТЧ И РАУНДЫ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def start_new_match(self) -> None:
        self.ct_score = 0
        self.t_score = 0
        self.round_number = 1
        self.player_cash = 1600
        self.player_kills = 0
        self.player_deaths = 0
        self.player_headshots = 0
        self._xp_gained_this_match = 0
        self._rank_at_match_start = self.settings.get_rank_title()
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
        self._dm_player_respawn_timer = 0.0
        self.round_time_left = float(self.settings.round_time_seconds)

        self.hud.buy_panel.enabled = False
        self.hud.hide_round_banner()
        self.hud.set_visible(True)
        self.weapon_mgr.set_visible(True)
        self._activate_fps_camera()
        self.state = GameState.PLAYING
        mode_label = {
            "CLASSIC": "CLASSIC (C4 + ЭКОНОМИКА)",
            "DEATHMATCH": "DEATHMATCH (МЯСОРУБКА)",
            "HEADSHOT_ONLY": "HEADSHOT ONLY",
            "BOSS_ELDAR": "БОСС «УСАТЫЙ ЭЛЬДАР»",
        }.get(self.settings.game_mode, self.settings.game_mode)
        self.hud.show_notice(
            f"ROUND {self.round_number}  •  {mode_label}  |  [B] ЗАКУПКА  [G] ГРАНАТЫ  [F] ОСМОТР  [C] РАЦИЯ",
            duration=3.4,
        )

    def _end_round(self, ct_won: bool, reason: str) -> None:
        if self.state != GameState.PLAYING:
            return

        self.state = GameState.ROUND_OVER
        self.hud.buy_panel.enabled = False
        if self.player.enabled:
            mouse.locked = True
            mouse.visible = False

        xp_for_round = 40 if ct_won else 12
        self._xp_gained_this_match += xp_for_round

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
            self._commit_match_progress(ct_won=self.ct_score > self.t_score)
            sub = f"{champ}  Счёт {self.ct_score} : {self.t_score}. Новый матч через 4 сек..."
            self._next_round_countdown = 4.2
        else:
            sub = f"{reason}   |   Следующий раунд через 3 сек..."
            self._next_round_countdown = 3.2

        self.hud.show_round_banner(headline, sub, ct_won=ct_won)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # XP-ПРОГРЕССИЯ, ЗВАНИЯ И СОХРАНЕНИЕ ПРОФИЛЯ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _add_xp(self, amount: int) -> None:
        before = self.settings.get_rank_title()
        self.settings.player_xp += amount
        self._xp_gained_this_match += amount
        after = self.settings.get_rank_title()
        if after != before:
            self.hud.show_killstreak_banner(f"★ НОВОЕ ЗВАНИЕ: {after}! ★")
            self.sound_mgr.play_sfx("killstreak", volume=0.85, pitch=1.16)
        self.settings.save()

    def _commit_match_progress(self, ct_won: bool) -> None:
        if ct_won:
            self.settings.matches_won += 1
        self.settings.total_career_kills += self.player_kills
        self._add_xp(60 if ct_won else 20)
        self.settings.save()

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
            self.sound_mgr.play_sfx("headshot", volume=0.7, pitch=1.05)

        bonus = kill_reward + (150 if is_headshot else 0)
        self.player_cash = min(16000, self.player_cash + bonus)
        self.hud.push_killfeed(weapon_name, victim_name, is_headshot)
        self._add_xp(25 + (15 if is_headshot else 0))

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

        # Кинематографичное замедление времени на финальном фраге раунда (кроме Deathmatch)!
        if self.settings.game_mode != "DEATHMATCH" and all(b.state == "DEAD" for b in self.bots):
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
                    if bot.role == "BOSS":
                        self._add_xp(60)

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
        if self.settings.game_mode == "DEATHMATCH":
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
        self._add_xp(15)
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
        self._enter_main_menu()

    def _on_player_hurt(self, rel_angle: float | None) -> None:
        self.hud.flash_damage(rel_angle)

    def _on_player_died(self) -> None:
        self.player_deaths += 1
        if self.settings.game_mode == "DEATHMATCH" and self.state == GameState.PLAYING:
            # В МЯСОРУБКЕ игрок возрождается через 3 секунды!
            self._dm_player_respawn_timer = DEATHMATCH_RESPAWN_DELAY
            self.player.enabled = False
            self.weapon_mgr.set_visible(False)
            self.weapon_mgr.clear_zoom()
            self.hud.show_notice("ВЫ УБИТЫ! ВОЗРОЖДЕНИЕ ЧЕРЕЗ 3 СЕКУНДЫ...", duration=2.8)
            return
        if self.state == GameState.PLAYING:
            self._end_round(ct_won=False, reason="ВЫ ПАЛИ В ПЕРЕСТРЕЛКЕ")

    def _respawn_player_dm(self) -> None:
        spawn_pt = random.choice(DM_RESPAWN_POINTS)
        self.player.respawn(spawn_pt, yaw=180.0)
        self.weapon_mgr.reset_all_ammo()
        self.weapon_mgr.set_visible(True)
        self._activate_fps_camera()
        self.hud.show_notice("ВЫ СНОВА В БОЮ!", duration=1.6)

    def _update_dm_respawns(self, dt: float) -> None:
        if self._dm_player_respawn_timer > 0.0:
            self._dm_player_respawn_timer = max(0.0, self._dm_player_respawn_timer - dt)
            if self._dm_player_respawn_timer <= 0.0:
                self._respawn_player_dm()

        if self._dm_bot_respawn_queue:
            kept: list[tuple[float, EnemyBot]] = []
            for ttl, bot in self._dm_bot_respawn_queue:
                ttl -= dt
                if ttl <= 0.0:
                    bot.respawn_at(random.choice(self.arena.t_spawn_points))
                else:
                    kept.append((ttl, bot))
            self._dm_bot_respawn_queue = kept

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ГОРЯЧИЕ КЛАВИШИ (F3 телеметрия, F5 вид, F6 небо, F7 прицел,
    # F8 скин, F11 fullscreen, C рация, B закупка, Z пинг, 5 C4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def handle_input(self, key: str) -> None:
        # Пропуск кинематографичной заставки: [SPACE] / [ENTER] / [ЛКМ]
        if self.state == GameState.SPLASH:
            if key in ("space", "enter", "left mouse down"):
                self.splash.skip()
            return

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

        # F3 — телеметрия FPS/GPU (оверлей разработчика Panorama)
        if key == "f3":
            self.settings.show_fps_telemetry = not self.settings.show_fps_telemetry
            self.settings.save()
            if self.hud.root.enabled:
                state_s = "ON" if self.settings.show_fps_telemetry else "OFF"
                self.hud.show_notice(f"ТЕЛЕМЕТРИЯ F3: {state_s}")
            return

        # F6 — смена времени суток и освещения на лету (DAY / SUNSET / NIGHT / OVERCAST)
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

        # F8 — циклическое переключение 6 PBR-скинов оружия (работает и в бою, и в меню!)
        if key == "f8":
            skin_name = self.weapon_mgr.cycle_weapon_skin()
            self.settings.weapon_skin_idx = self.weapon_mgr.skin_idx
            self.settings.save()
            self.showcase.set_showcase_loadout(self.weapon_mgr.current_weapon_id, self.weapon_mgr.skin_idx)
            if self.hud.root.enabled:
                self.hud.show_notice(f"СКИН ОРУЖИЯ: {skin_name}")
            elif self.menu.main_panel.enabled:
                self.menu.refresh_toggle_labels()
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

        # Ползунки настроек управляются клавиатурой (стрелки), если панель настроек открыта
        if self.state == GameState.MENU or self.state == GameState.PAUSED:
            self.menu.handle_input(key)
            return

        if self.state not in (GameState.PLAYING, GameState.ROUND_OVER):
            return

        if key == "b":
            self.toggle_buy_menu()
            return

        if self.hud.buy_panel.enabled:
            return

        # F5 — тактический вид от 3-го лица через плечо
        if key == "f5":
            if not self.player.is_alive:
                return
            tp_on = self.player.toggle_third_person()
            self.weapon_mgr.set_visible(True)
            if self.hud.root.enabled:
                self.hud.show_notice(f"КАМЕРА: {'3-Е ЛИЦО (ТАКТИЧЕСКИЙ ВИД)' if tp_on else '1-Е ЛИЦО'}", duration=1.6)
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

        # C — тактическая рация с радиовызовами CS2!
        if key == "c":
            callout = random.choice(RADIO_CALLOUTS)
            self.sound_mgr.play_sfx("radio_beep", volume=0.6)
            self.hud.show_notice(callout, duration=2.6)
            return

        if key in ("z", "middle mouse down"):
            ignore_all = [self.player, self.weapon_mgr.pivot, *collect_bot_ignore_list(self.bots)]
            self.fx_mgr.place_tactical_ping(camera.world_position, camera.forward, ignore_all)
            return

        # Клавиша 5: тренировочная установка C4 на точке A/B, если бомба ещё не заложена
        if key == "5" and not self.fx_mgr.c4_planted and self.state == GameState.PLAYING:
            if self.settings.game_mode == "DEATHMATCH":
                self.hud.show_notice("В DEATHMATCH БОМБЫ НЕ ЗАЛАГАЮТСЯ!", duration=1.8)
                return
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

        # 1. КИНЕМАТОГРАФИЧНАЯ ЗАСТАВКА
        if self.state == GameState.SPLASH:
            self.splash.update(raw_dt)
            return

        # 2. Живой панорамный 3D-облёт арены в Главном меню + оперативник на подиуме
        if self.state == GameState.MENU:
            self._menu_cam_angle += raw_dt * 0.14
            radius = 25.0
            camera.position = Vec3(
                math.sin(self._menu_cam_angle) * radius,
                12.5,
                math.cos(self._menu_cam_angle) * radius,
            )
            camera.look_at(Vec3(0.0, 1.8, 0.0))
            self.showcase.update(raw_dt)
            self.menu.update()
            return

        if self.state == GameState.PAUSED:
            return

        if self._slowmo_timer > 0.0:
            self._slowmo_timer = max(0.0, self._slowmo_timer - raw_dt)
            dt = raw_dt * 0.35
        else:
            dt = raw_dt

        # 3. Возрождения Deathmatch (игрок + боты)
        if self.settings.game_mode == "DEATHMATCH":
            self._update_dm_respawns(raw_dt)

        player_frozen = not self.player.enabled or not self.player.is_alive
        ignore_bots = [self.player, *collect_bot_ignore_list(self.bots)]

        if not player_frozen:
            self.weapon_mgr.update(dt)
            self.weapon_mgr.set_visible(True)
        self.fx_mgr.update(dt, ignore_bots)
        self.hud.update(raw_dt)
        self._check_loot_pickups()

        # 4. Таблица счёта при удержании Tab
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

        # 5. Обновление ИИ живых ботов (с учётом дымовых завес и закладки C4!)
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

        # 6. Прогресс обезвреживания C4 по удержанию клавиши E рядом с бомбой
        defuse_prog = 0.0
        if self.state == GameState.PLAYING and self.fx_mgr.c4_planted and self.player.is_alive:
            defuse_prog = self.fx_mgr.step_defuse(
                dt=raw_dt,
                player_pos=self.player.world_position,
                has_defuse_kit=self.player.has_defuse_kit,
                holding_use=bool(held_keys["e"]),
            )

        # 7. Условия победы / поражения в раунде — С УЧЁТОМ 4 РЕЖИМОВ!
        if self.state == GameState.PLAYING:
            mode = self.settings.game_mode
            if mode == "DEATHMATCH":
                self.round_time_left -= dt
                team_bot_kills = sum(b.kills for b in self.bots)
                if self.player_kills >= DEATHMATCH_KILL_LIMIT:
                    self._end_round(ct_won=True, reason=f"ВЫ ДОСТИГЛИ {DEATHMATCH_KILL_LIMIT} ФРАГОВ ПЕРВЫМ!")
                elif team_bot_kills >= DEATHMATCH_KILL_LIMIT:
                    self._end_round(ct_won=False, reason="ТЕРРОРИСТЫ ДОСТИГЛИ ЛИМИТА ФРАГОВ")
                elif self.round_time_left <= 0.0:
                    self.round_time_left = 0.0
                    self._end_round(
                        ct_won=self.player_kills >= team_bot_kills,
                        reason=f"ВРЕМЯ ВЫШЛО! ВЫ {self.player_kills} : {team_bot_kills} ТЕРРОРИСТЫ",
                    )
            elif not self.fx_mgr.c4_planted:
                self.round_time_left -= dt
                if alive_bots_count == 0:
                    if mode == "BOSS_ELDAR":
                        self._end_round(ct_won=True, reason="РЕЙД-БОСС «УСАТЫЙ ЭЛЬДАР» ПОВЕРЖЕН!")
                    else:
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

        # 8. Обновление 2D радара (с 3D-дымами!), телеметрии F3 и всех индикаторов HUD
        self.hud.update_radar(
            player_pos=self.player.world_position,
            player_yaw=self.player.rotation_y,
            site_a=self.arena.site_a_center,
            site_b=self.arena.site_b_center,
            bots=self.bots,
            c4_planted=self.fx_mgr.c4_planted,
            c4_pos=self.fx_mgr.c4_pos,
            ping_pos=self.fx_mgr.ping_pos,
            smokes=self.fx_mgr.smokes,
        )

        self._telemetry_accum += raw_dt
        if self._telemetry_accum >= 0.25:
            self._telemetry_accum = 0.0
            self.hud.update_telemetry(
                dt=max(0.001, raw_dt),
                batches=self.arena.static_batch_count,
                active_fx=self.fx_mgr.active_pooled_count,
            )

        wid = self.weapon_mgr.current_weapon_id
        self.hud.sync_stats(
            hp=self.player.hp,
            armor=self.player.armor,
            stamina=self.player.stamina,
            weapon_id=wid,
            weapon_display_name=self.weapon_mgr.active_spec["display_name"],
            skin_idx=self.weapon_mgr.skin_idx,
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
            third_person=self.player.third_person_mode,
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
    required = ("ak47.glb", "awp.glb", "p90.glb", "mp9.glb", "shotgun.glb", "c4.glb", "barrel.glb", "player_operator.glb")
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
        # В offscreen-режиме окна нет: подсовываем безопасную заглушку, чтобы
        # mouse.locked / fullscreen-переключатели не падали в автотестах
        if getattr(app, "win", None) is None:

            class _HeadlessWindowStub:
                def requestProperties(self, _props: Any) -> None:
                    return None

                def getProperties(self) -> Any:
                    from panda3d.core import WindowProperties

                    return WindowProperties()

                def setClearColor(self, *_args: Any, **_kwargs: Any) -> None:
                    return None

                def getClearColor(self) -> Any:
                    from panda3d.core import Vec4

                    return Vec4(0, 0, 0, 1)

            app.win = _HeadlessWindowStub()
    else:
        app = Ursina(
            title="Counter-Strike 2 — 3D Realism Edition • алкодимас × усатый Эльдар",
            borderless=bool(initial_settings.fullscreen),
            fullscreen=bool(initial_settings.fullscreen),
            vsync=bool(initial_settings.vsync_enabled),
            development_mode=False,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True
        apply_fullscreen_mode(bool(initial_settings.fullscreen))
        apply_fps_limit(int(initial_settings.fps_limit), bool(initial_settings.vsync_enabled))

    _GAME = CS2GameController()
    return app, _GAME


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        os.environ["CS2_HEADLESS"] = "1"
        test_app, test_ctrl = main(headless=True)
        # Заставка должна быть активна на старте
        assert test_ctrl.state == GameState.SPLASH
        assert test_ctrl.splash.active
        time.dt = 0.016
        for _ in range(4):
            test_ctrl.update()
        # Пропуск заставки по [SPACE]
        test_ctrl.handle_input("space")
        assert test_ctrl.state == GameState.MENU
        for _ in range(6):
            test_ctrl.update()
        # Старт матча и 30 кадров боя с живыми ботами
        test_ctrl.start_new_match()
        assert test_ctrl.state == GameState.PLAYING
        for _ in range(30):
            test_ctrl.update()
        print("SELF-TEST PASSED! Frozen:", getattr(sys, "frozen", False))
        sys.exit(0)

    ursina_app, _ = main(headless=False)
    ursina_app.run()
