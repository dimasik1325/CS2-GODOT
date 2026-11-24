"""
Точка входа игры CS2 Clone на Python 3.11+ и движке Ursina (Panda3D).
Связывает карту, контроллер игрока, систему оружия, ИИ ботов, раунды, HUD и меню.
Поддерживает сборку в один исполняемый файл .exe через PyInstaller.
"""

from __future__ import annotations

import math
import os
import random
import sys
from enum import Enum

from panda3d.core import loadPrcFileData

# Если запущено в headless-среде (например, при автотестировании без дисплея)
if os.environ.get("CS2_HEADLESS") == "1" or "--self-test" in sys.argv:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null")

from ursina import Ursina, Vec3, camera, mouse, scene, time, window

from src.enemy import BOT_CALLSIGNS, EnemyBot, collect_bot_ignore_list
from src.hud import CS2HUD
from src.map import ArenaMap
from src.menu import MenuManager
from src.player import CS2Player
from src.settings import (
    ASSETS_DIR,
    GameSettings,
    SoundManager,
    configure_ursina_asset_folder,
)
from src.weapon import WeaponManager


class GameState(str, Enum):
    MENU = "MENU"
    PLAYING = "PLAYING"
    ROUND_OVER = "ROUND_OVER"
    PAUSED = "PAUSED"


class CS2GameController:
    """Главный координатор игровых состояний, раундов, спавна команд и UI."""

    def __init__(self) -> None:
        self.settings = GameSettings.load()
        self.sound_mgr = SoundManager(master_volume=self.settings.master_volume)

        # 1. Инициализация 3D-арены
        self.arena = ArenaMap()

        # 2. Инициализация игрока (пока выключен, т.к. стартуем в Главном меню)
        self.player = CS2Player(
            settings=self.settings,
            sound_mgr=self.sound_mgr,
            on_death_callback=self._on_player_died,
            on_hurt_callback=self._on_player_hurt,
            position=tuple(self.arena.ct_spawn_pos),
        )
        self.player.enabled = False

        # 3. Система оружия от первого лица
        self.weapon_mgr = WeaponManager(
            player=self.player,
            sound_mgr=self.sound_mgr,
            on_hit_enemy=self._on_weapon_hit_enemy,
        )
        self.weapon_mgr.set_visible(False)

        # 4. Боевой HUD в стиле CS2
        self.hud = CS2HUD()
        self.hud.set_visible(False)

        # 5. Главное меню, Пауза и Настройки
        self.menu = MenuManager(
            settings=self.settings,
            sound_mgr=self.sound_mgr,
            on_start_play=self.start_new_match,
            on_resume_play=self.resume_from_pause,
            on_restart_match=self.start_new_match,
            on_return_main_menu=self.return_to_main_menu,
            on_settings_applied=self._apply_live_settings,
        )

        # Состояние матча и раундов
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

        self.return_to_main_menu()

    def _apply_live_settings(self) -> None:
        self.player.apply_sensitivity(self.settings.mouse_sensitivity)
        camera.fov = self.settings.fov

    def _clear_bots(self) -> None:
        for bot in self.bots:
            bot.cleanup()
        self.bots.clear()

    def _spawn_bots_for_round(self) -> None:
        self._clear_bots()
        count = max(1, min(len(self.arena.t_spawn_points), int(self.settings.bot_count)))
        spawns = random.sample(self.arena.t_spawn_points, k=count)

        for idx, sp_pos in enumerate(spawns):
            callsign = BOT_CALLSIGNS[idx % len(BOT_CALLSIGNS)]
            bot = EnemyBot(
                bot_name=callsign,
                spawn_pos=sp_pos,
                waypoints=self.arena.patrol_waypoints,
                sound_mgr=self.sound_mgr,
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
        """Сбрасывает счёт команд CT/T в 0:0 и начинает 1-й раунд."""
        self.ct_score = 0
        self.t_score = 0
        self.round_number = 1
        self._match_finished = False
        self.hud.clear_killfeed()
        self.start_round()

    def start_round(self) -> None:
        """Респавнит игрока, пополняет патроны/броню и спавнит новую волну ботов."""
        self.weapon_mgr.clear_decals()
        self.player.respawn(self.arena.ct_spawn_pos, yaw=self.arena.ct_spawn_yaw)
        self.weapon_mgr.reset_all_ammo()
        self._spawn_bots_for_round()

        self.round_time_left = float(self.settings.round_time_seconds)
        self.hud.hide_round_banner()
        self.hud.set_visible(True)
        self.weapon_mgr.set_visible(True)
        self._activate_fps_camera()
        self.state = GameState.PLAYING

    def _end_round(self, ct_won: bool, reason: str) -> None:
        if self.state != GameState.PLAYING:
            return

        self.state = GameState.ROUND_OVER
        if ct_won:
            self.ct_score += 1
            self.sound_mgr.play_sfx("round_win", volume=0.85)
            headline = "COUNTER-TERRORISTS WIN"
        else:
            self.t_score += 1
            self.sound_mgr.play_sfx("round_lose", volume=0.85)
            headline = "TERRORISTS WIN"

        # Проверка победы в матче (например, до 5 раундов)
        target_wins = int(self.settings.rounds_to_win)
        if self.ct_score >= target_wins or self.t_score >= target_wins:
            self._match_finished = True
            champ = "ПОБЕДА СПЕЦНАЗА (CT)!" if self.ct_score > self.t_score else "ПОБЕДА ТЕРРОРИСТОВ (T)!"
            sub = f"{champ}  Итоговый счёт {self.ct_score} : {self.t_score}. Новый матч через 4 сек..."
            self._next_round_countdown = 4.2
        else:
            sub = f"{reason}   |   Следующий раунд через 3 сек..."
            self._next_round_countdown = 3.2

        self.hud.show_round_banner(headline, sub, ct_won=ct_won)

    def pause_game(self) -> None:
        if self.state not in (GameState.PLAYING, GameState.ROUND_OVER):
            return
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
        """Возвращает игру в Главное меню с панорамным облётом арены."""
        self._clear_bots()
        self.weapon_mgr.clear_decals()
        self.player.enabled = False
        self.weapon_mgr.set_visible(False)
        self.hud.hide_round_banner()
        self.hud.set_visible(False)

        camera.parent = scene
        camera.fov = 78.0
        self.state = GameState.MENU
        self.menu.show_main_menu()

    def _on_weapon_hit_enemy(
        self,
        is_headshot: bool,
        killed: bool,
        weapon_name: str,
        victim_name: str,
    ) -> None:
        self.hud.show_hitmarker(is_headshot=is_headshot)
        if killed:
            self.hud.push_killfeed(weapon_name, victim_name, is_headshot)

    def _on_player_hurt(self) -> None:
        self.hud.flash_damage()

    def _on_player_died(self) -> None:
        if self.state == GameState.PLAYING:
            self._end_round(ct_won=False, reason="ВЫ ПАЛИ В ПЕРЕСТРЕЛКЕ")

    def handle_input(self, key: str) -> None:
        if key == "escape":
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

        if self.state in (GameState.PLAYING, GameState.ROUND_OVER):
            self.weapon_mgr.handle_input(key)

    def update(self) -> None:
        dt = min(float(time.dt), 0.05)

        # Плавный кинематографичный облёт арены на фоне Главного меню
        if self.state == GameState.MENU:
            self._menu_cam_angle += dt * 0.16
            radius = 22.0
            camera.position = Vec3(
                math.sin(self._menu_cam_angle) * radius,
                11.5,
                math.cos(self._menu_cam_angle) * radius,
            )
            camera.look_at(Vec3(0.0, 1.5, 0.0))
            return

        if self.state == GameState.PAUSED:
            return

        # Обновление оружия и HUD
        self.weapon_mgr.update(dt)
        self.hud.update(dt)

        # Обновление ИИ живых ботов
        ignore_bots = [self.player, *collect_bot_ignore_list(self.bots)]
        alive_bots_count = 0
        for bot in self.bots:
            if bot.state != "DEAD":
                alive_bots_count += 1
                if self.state == GameState.PLAYING:
                    bot.update_ai(dt, self.player, ignore_bots)

        # Логика активного раунда
        if self.state == GameState.PLAYING:
            self.round_time_left -= dt
            if alive_bots_count == 0:
                self._end_round(ct_won=True, reason="ВСЕ ВРАГИ ЛИКВИДИРОВАНЫ")
            elif self.round_time_left <= 0.0:
                self.round_time_left = 0.0
                self._end_round(ct_won=False, reason="ВРЕМЯ РАУНДА ВЫШЛО")

        # Пауза между раундами
        elif self.state == GameState.ROUND_OVER:
            self._next_round_countdown -= dt
            if self._next_round_countdown <= 0.0:
                if self._match_finished:
                    self.start_new_match()
                else:
                    self.round_number += 1
                    self.start_round()

        # Обновление цифр HUD
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
        )


# Глобальный экземпляр контроллера для хуков Ursina update() / input(key)
_GAME: CS2GameController | None = None


def update() -> None:
    if _GAME is not None:
        _GAME.update()


def input(key: str) -> None:
    if _GAME is not None:
        _GAME.handle_input(key)


def bootstrap_assets_if_needed() -> None:
    """Если папка assets пуста при запуске из исходников — генерирует стартовый набор."""
    models_dir = ASSETS_DIR / "models"
    if not models_dir.is_dir() or not any(models_dir.glob("*.glb")):
        try:
            from generate_assets import ensure_all_starter_assets

            ensure_all_starter_assets()
        except Exception:
            # Даже без генератора игра штатно запустится на примитивах Ursina
            pass


def main(headless: bool = False) -> tuple[Ursina, CS2GameController]:
    global _GAME

    configure_ursina_asset_folder()
    bootstrap_assets_if_needed()

    if headless or os.environ.get("CS2_HEADLESS") == "1":
        app = Ursina(window_type="none")
    else:
        app = Ursina(
            title="Counter-Strike 2 — Python Ursina Edition",
            borderless=False,
            fullscreen=False,
            size=(1280, 720),
            vsync=True,
            development_mode=False,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True

    _GAME = CS2GameController()
    return app, _GAME


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        os.environ["CS2_HEADLESS"] = "1"
        test_app, test_ctrl = main(headless=True)
        test_ctrl.start_new_match()
        time.dt = 0.016
        for _ in range(5):
            test_ctrl.update()
        print("SELF-TEST PASSED! Frozen:", getattr(sys, "frozen", False))
        sys.exit(0)

    ursina_app, _ = main(headless=False)
    ursina_app.run()
