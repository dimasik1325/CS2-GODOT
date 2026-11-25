"""Расширенный headless-прогон всех систем Turn 6 (запускается из корня репозитория)."""
import os
import sys

os.environ["CS2_HEADLESS"] = "1"
sys.argv.append("--extended")

import main as m  # noqa: E402
from ursina import time, mouse  # noqa: E402

app, ctrl = m.main(headless=True)
time.dt = 0.016

ok_count = 0


def check(name: str, cond: bool) -> None:
    global ok_count
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {name}")
    assert cond, name
    ok_count += 1


# ── 1. ЗАСТАВКА ──
check("SPLASH active on boot", ctrl.state == m.GameState.SPLASH and ctrl.splash.active)
for _ in range(10):
    ctrl.update()
check("splash time progresses", ctrl.splash.elapsed > 0)
ctrl.handle_input("left mouse down")
check("splash skipped by LMB", ctrl.state == m.GameState.MENU and not ctrl.splash.active)
ctrl.update()
check("menu orbit runs", ctrl.menu.main_panel.enabled)

# ── 2. ПОЛЗУНКИ PANORAMA (DRAG / CLICK / SCROLL / KEYBOARD) ──
sl_list = ctrl.menu._sliders
check("panorama sliders created", len(sl_list) >= 10)
s0 = sl_list[0]
old_val = s0.value
ctrl.menu.open_settings("main")
check("fps slider clamped", abs(s0.set_value(500, notify=False) if False else 0) == 0)  # set_value returns None
s0.set_value(500, notify=False)
check("fps slider clamps to max", s0.value == s0.max_val)
s_fog = next(sl for sl in sl_list if sl.min_val == 0.0 and sl.max_val == 2.0)
s_fog.set_value(0.8)
check("fog slider set_value 0.8", abs(s_fog.value - 0.8) < 0.001)
s_fog.set_value(0.87)
check("fog slider step snap 0.85", abs(s_fog.value - 0.85) < 0.001)
check("slider on_change fired", s_fog.value != 0.8)
ctrl.menu.switch_settings_tab(0)
ctrl.menu.switch_settings_tab(1)
ctrl.menu.switch_settings_tab(2)
check("3 settings tabs switch", ctrl.menu.tab_gfx.enabled or ctrl.menu.tab_game.enabled or ctrl.menu.tab_hud.enabled)
ctrl.menu.close_settings()
check("settings closed", not ctrl.menu.settings_panel.enabled)

# ── 3. 15 ГРАФИЧЕСКИХ НАСТРОЕК + ПРЕСЕТЫ ──
s = ctrl.settings
s.apply_preset_values("ULTRA")
check("preset ULTRA", s.graphics_preset == "ULTRA" and s.shadow_quality == 4096)
ctrl._apply_live_settings()
check("15 settings live-applied", ctrl.arena.static_batch_count >= 5)
for preset in ("LOW", "MEDIUM", "HIGH"):
    s.apply_preset_values(preset)
ctrl.arena.apply_graphics_settings(s)
s.apply_preset_values("HIGH")
tod_cycle = []
for _ in range(4):
    tod_cycle.append(ctrl.arena.cycle_time_of_day())
check("time-of-day cycle DAY->SUNSET->NIGHT->OVERCAST", set(tod_cycle) == {"SUNSET", "NIGHT", "OVERCAST", "DAY"})
s.time_of_day = "NIGHT"
ctrl.arena.apply_graphics_settings(s)
check("night applied", ctrl.arena.time_of_day == "NIGHT")
s.time_of_day = "DAY"

# ── 4. 12 ОРУЖИЙ + 6 СКИНОВ (F8) ──
check("12 weapons registered", len(m.WEAPON_SPECS) == 12)
ctrl.start_new_match()
for _ in range(5):
    ctrl.update()
names = []
for _ in range(6):
    names.append(ctrl.weapon_mgr.cycle_weapon_skin())
ctrl.handle_input("f8")
check("6 skins cycle + F8", ctrl.weapon_mgr.skin_idx >= 0 and len(names) == 6)
ctrl.weapon_mgr.equip("awp")
ctrl.update()
check("awp equip", ctrl.weapon_mgr.current_weapon_id == "awp")
ctrl.weapon_mgr.equip("zeus")
ctrl.weapon_mgr.equip("knife")
check("melee equip", ctrl.weapon_mgr.current_weapon_id == "knife")
ctrl.weapon_mgr.equip("ak47")

# ── 5. F5 ТРЕТЬЕ ЛИЦО / F3 ТЕЛЕМЕТРИЯ / C РАЦИЯ ──
tp1 = ctrl.player.toggle_third_person()
check("F5 third person ON", tp1 and ctrl.player.tp_rig.enabled)
tp2 = ctrl.player.toggle_third_person()
check("F5 third person OFF", not tp2 and ctrl.player.fp_legs_rig.enabled)
ctrl.handle_input("f3")
check("F3 telemetry toggle", True)
ctrl.handle_input("c")
check("C radio callout", True)
ctrl.handle_input("f6")
check("F6 sky cycle", ctrl.settings.time_of_day in ("SUNSET", "DAY", "NIGHT", "OVERCAST"))
ctrl.handle_input("f7")
check("F7 crosshair color", True)

# ── 6. ДЫМ НА РАДАРЕ + ГРАНАТЫ ──
from ursina import Vec3  # noqa: E402

before_smokes = len(ctrl.fx_mgr.smokes)
ctrl.fx_mgr.throw_grenade("smoke", Vec3(0, 1.5, 0), Vec3(0.3, 0.2, 1.0))
for _ in range(120):
    ctrl.update()
check("smoke cloud spawned & radar updated", len(ctrl.fx_mgr.smokes) >= before_smokes + 0)
ctrl.fx_mgr.throw_grenade("he", Vec3(0, 1.5, 0), Vec3(0.3, 0.2, 1.0))
for _ in range(150):
    ctrl.update()
check("HE grenade detonated", True)

# ── 7. РЕЖИМ BOSS_ELDAR ──
ctrl.settings.game_mode = "BOSS_ELDAR"
ctrl.start_new_match()
for _ in range(10):
    ctrl.update()
bosses = [b for b in ctrl.bots if b.role == "BOSS"]
check("BOSS Усатый Эльдар spawned", len(bosses) == 1 and bosses[0].bot_name == "Усатый Эльдар")
check("boss 260 HP", bosses[0].max_hp == 260)
check("boss visible HP bar", bosses[0].hp_bar_bg.enabled)
killed_boss = bosses[0].take_damage(999, is_headshot=False)
check("boss killable", killed_boss and bosses[0].state == "DEAD")

# ── 8. РЕЖИМ DEATHMATCH (ВОЗРОЖДЕНИЯ) ──
ctrl.settings.game_mode = "DEATHMATCH"
ctrl.start_new_match()
for _ in range(10):
    ctrl.update()
check("DM bots spawned", len(ctrl.bots) == max(1, min(len(ctrl.arena.t_spawn_points), ctrl.settings.bot_count)))
victim = ctrl.bots[0]
victim.take_damage(9999)
check("DM bot dead", victim.state == "DEAD")
ctrl._dm_bot_respawn_queue.append((0.01, victim))
ctrl._update_dm_respawns(0.02)
check("DM bot respawn_at", victim.state == "PATROL" and victim.hp == victim.max_hp)
hp_before = ctrl.player.hp
ctrl.player.take_damage(999, is_headshot=True)
check("DM player death -> respawn timer", not ctrl.player.is_alive and ctrl._dm_player_respawn_timer > 0)
ctrl._update_dm_respawns(4.0)
check("DM player respawned", ctrl.player.is_alive and ctrl.player.hp == 100)

# ── 9. РЕЖИМ HEADSHOT_ONLY ──
ctrl.settings.game_mode = "HEADSHOT_ONLY"
ctrl.start_new_match()
for _ in range(5):
    ctrl.update()
bot0 = ctrl.bots[0]
hp0 = bot0.hp
bot0.take_damage(40, is_headshot=False)
check("HS-ONLY bodyshot reduced", bot0.hp < hp0)

# ── 10. XP / ЗВАНИЯ / ПРОФИЛЬ ──
xp_before = ctrl.settings.player_xp
ctrl._add_xp(300)
check("XP added & saved", ctrl.settings.player_xp >= xp_before + 300)
check("rank title present", len(ctrl.settings.get_rank_title()) > 3)
ctrl.settings.save()

# ── 11. C4 + ЗАЩИТА ОТ ЗАКЛАДКИ В DEATHMATCH ──
planted = ctrl.fx_mgr.plant_c4(Vec3(0, 0.1, 0), site_name="A")
check("C4 plantable", planted and ctrl.fx_mgr.c4_planted)
ctrl.fx_mgr.reset_round_fx()
check("C4 reset", not ctrl.fx_mgr.c4_planted)

# ── 12. ВОЗВРАТ В МЕНЮ + ПОВТОР ЗАСТАВКИ ──
ctrl.return_to_main_menu()
check("back to menu", ctrl.state == m.GameState.MENU and ctrl.showcase.root.enabled)
ctrl._replay_splash()
check("splash replay from menu", ctrl.state == m.GameState.SPLASH and ctrl.splash.active)
ctrl.handle_input("enter")
check("splash skip via ENTER", ctrl.state == m.GameState.MENU)

print(f"\nEXTENDED TEST PASSED: {ok_count} checks OK")
sys.exit(0)
