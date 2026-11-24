extends Node3D
## CS2-GODOT v2.0: корневой скрипт единственной сцены (Main.tscn).
## Управляет всей игрой: главное меню (на фоне — живая карта с облётом
## камерой), настройками, кейсами, раундами и матчем, спавном игрока и ботов.
##
## ВАЖНО: в редакторе не нужно создавать ничего, кроме корневого Node3D
## со скриптом main.gd (сцена Main.tscn уже в проекте).

enum GameState { IN_MENU, FREEZE, LIVE, ROUND_END, MATCH_END }

const FREEZE_TIME := 2.5
const KILL_REWARD := 300
const KNIFE_KILL_REWARD := 750
const ROUND_WIN_REWARD := 1000
const ROUND_LOSS_REWARD := 400
const MATCH_WIN_BONUS := 1000

var state: GameState = GameState.IN_MENU

# Подсистемы.
var settings: SettingsManager
var sfx: SfxManager
var save_manager: SaveManager
var map_builder: MapBuilder
var menu: MenuController
var hud: HUDController

# Окружение.
var env: Environment
var sun: DirectionalLight3D
var sky_material: ProceduralSkyMaterial
var menu_camera: Camera3D
var _menu_angle := 0.0

# Матч.
var player: PlayerController
var bots: Array[Bot] = []
var player_score := 0
var bot_score := 0
var kills := 0
var deaths := 0
var bots_alive := 0
var round_seq := 0
var freeze_left := 0.0


func _ready() -> void:
	randomize()
	_register_inputs()
	# Менеджеры (синглтоны через статические поля).
	settings = SettingsManager.new()
	settings.name = "SettingsManager"
	add_child(settings)
	sfx = SfxManager.new()
	sfx.name = "SfxManager"
	add_child(sfx)
	save_manager = SaveManager.new()
	save_manager.name = "SaveManager"
	add_child(save_manager)

	_build_environment()
	map_builder = MapBuilder.new()
	map_builder.name = "MapRoot"
	add_child(map_builder)
	_rebuild_map(settings.map_index)
	settings.apply_all()

	hud = HUDController.new()
	hud.name = "HUD"
	add_child(hud)
	hud.visible = false
	hud.bind_main(save_manager, _get_bots_for_radar)

	menu = MenuController.new()
	menu.name = "Menu"
	add_child(menu)
	menu.start_requested.connect(_start_match)
	menu.map_changed.connect(_on_map_changed)
	menu.resume_requested.connect(_resume_game)
	menu.quit_to_menu_requested.connect(_quit_to_menu)
	menu.esc_pressed.connect(_on_menu_esc)
	menu.show_main()

	_build_menu_camera()


func _get_bots_for_radar() -> Array:
	return bots


# ---------------------------------------------------------------------------
# Ввод: весь Input Map регистрируется кодом, настройки проекта не требуются.
# Физические коды клавиш — раскладка (RU/EN) не имеет значения.
# ---------------------------------------------------------------------------

func _register_inputs() -> void:
	var key_actions := {
		"move_forward": [KEY_W],
		"move_back": [KEY_S],
		"move_left": [KEY_A],
		"move_right": [KEY_D],
		"jump": [KEY_SPACE],
		"crouch": [KEY_CTRL],
		"reload": [KEY_R],
		"weapon_1": [KEY_1],
		"weapon_2": [KEY_2],
		"weapon_3": [KEY_3],
		"throw_grenade": [KEY_G, KEY_4],
		"restart_round": [KEY_ENTER, KEY_KP_ENTER],
	}
	for action in key_actions:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action, 0.5)
		for key in key_actions[action]:
			var key_event := InputEventKey.new()
			key_event.physical_keycode = key
			InputMap.action_add_event(action, key_event)
	var mouse_actions := {
		"fire": [MOUSE_BUTTON_LEFT],
		"aim": [MOUSE_BUTTON_RIGHT],
	}
	for action in mouse_actions:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action, 0.5)
		for button in mouse_actions[action]:
			var mouse_event := InputEventMouseButton.new()
			mouse_event.button_index = button
			InputMap.action_add_event(action, mouse_event)


# ---------------------------------------------------------------------------
# Окружение и карта.
# ---------------------------------------------------------------------------

func _build_environment() -> void:
	sky_material = ProceduralSkyMaterial.new()
	var sky := Sky.new()
	sky.sky_material = sky_material

	env = Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_sky_affect = 0.12

	var world_env := WorldEnvironment.new()
	world_env.environment = env
	add_child(world_env)

	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 90.0
	add_child(sun)

	settings.sun = sun
	settings.env = env


func _apply_theme(theme: Dictionary) -> void:
	sky_material.sky_top_color = theme["sky_top"]
	sky_material.sky_horizon_color = theme["sky_horizon"]
	sky_material.ground_horizon_color = theme["ground_horizon"]
	sky_material.ground_bottom_color = theme["ground_bottom"]
	sun.light_color = theme["sun_color"]
	sun.light_energy = theme["sun_energy"]
	sun.rotation_degrees = theme["sun_deg"]
	env.fog_light_color = theme["fog_color"]
	env.fog_density = theme["fog_density"]
	env.ambient_light_energy = theme["ambient"]


func _rebuild_map(theme_index: int) -> void:
	map_builder.build_map(theme_index, randi() % MapBuilder.LAYOUT_NAMES.size())
	_apply_theme(map_builder.get_theme(theme_index))


func _build_menu_camera() -> void:
	menu_camera = Camera3D.new()
	menu_camera.name = "MenuCamera"
	menu_camera.fov = 70.0
	add_child(menu_camera)
	menu_camera.make_current()


func _on_map_changed(index: int) -> void:
	if state == GameState.IN_MENU:
		_rebuild_map(index)


func _process(delta: float) -> void:
	if state == GameState.IN_MENU and not get_tree().paused:
		# Медленный облёт карты за меню.
		_menu_angle += delta * 0.08
		var radius := 26.0
		menu_camera.position = Vector3(cos(_menu_angle) * radius, 11.0, sin(_menu_angle) * radius)
		menu_camera.look_at(Vector3(0.0, 1.0, 0.0))
	elif state == GameState.FREEZE:
		freeze_left -= delta
		hud.set_freeze(maxf(0.0, freeze_left))
		if freeze_left <= 0.0:
			_begin_live()


# ---------------------------------------------------------------------------
# Меню → матч.
# ---------------------------------------------------------------------------

func _start_match() -> void:
	player_score = 0
	bot_score = 0
	kills = 0
	deaths = 0
	menu.hide_all()
	menu.visible = false
	hud.visible = true
	hud.set_radar_visible(settings.show_radar)

	player = PlayerController.new()
	player.name = "Player"
	add_child(player)
	hud.bind_player(player, player.weapon_manager)
	player.activate_camera()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

	hud.update_score(player_score, bot_score)
	hud.update_kd(kills, deaths)
	SfxManager.instance.play("buy", -4.0)
	_begin_round()


func _spawn_bots() -> void:
	for bot in bots:
		if is_instance_valid(bot):
			bot.queue_free()
	bots.clear()
	var spawns := map_builder.bot_spawns.duplicate()
	spawns.shuffle()
	for i in settings.bots_count:
		var bot := Bot.new()
		bot.name = "Bot%d" % (i + 1)
		bot.bot_name = "Bot-%d" % (i + 1)
		bot.player = player
		bot.position = spawns[i % spawns.size()]
		add_child(bot)
		bot.died.connect(_on_bot_died)
		bot.set_combat_enabled(false)
		bots.append(bot)
	bots_alive = bots.size()
	hud.update_enemies(bots_alive)


func _begin_round() -> void:
	round_seq += 1
	state = GameState.FREEZE
	freeze_left = FREEZE_TIME
	player.controls_enabled = false
	player.reset_for_round(map_builder.player_spawn, 0.0)
	# Каждый раунд — свежая волна ботов.
	_spawn_bots()
	hud.reset_for_round()
	hud.update_score(player_score, bot_score)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _begin_live() -> void:
	state = GameState.LIVE
	hud.set_freeze(-1.0)
	player.controls_enabled = true
	for bot in bots:
		if is_instance_valid(bot):
			bot.set_combat_enabled(true)


# ---------------------------------------------------------------------------
# Убийства и раунды.
# ---------------------------------------------------------------------------

func _on_bot_died(bot: Node3D, weapon: String) -> void:
	var dead_bot := bot as Bot
	if dead_bot != null:
		bots.erase(dead_bot)
	if state != GameState.LIVE:
		return
	kills += 1
	SaveManager.instance.add_kill()
	SaveManager.instance.add_money(KNIFE_KILL_REWARD if weapon == "Knife" else KILL_REWARD)
	SfxManager.instance.play("kill", -2.0)
	bots_alive = maxi(0, bots_alive - 1)
	hud.update_kd(kills, deaths)
	hud.update_enemies(bots_alive)
	if dead_bot != null:
		hud.add_kill_feed("You", dead_bot.bot_name, weapon)
	hud.show_hitmarker(false, true)
	if bots_alive <= 0:
		_end_round(true)


func _on_player_died() -> void:
	if state != GameState.LIVE:
		return
	deaths += 1
	SaveManager.instance.add_death()
	hud.update_kd(kills, deaths)
	var attacker := "Enemy"
	if player != null:
		attacker = player.last_attacker_name
	hud.add_kill_feed(attacker, "You", "AK-47")
	_end_round(false)


func _end_round(victory: bool) -> void:
	if state != GameState.LIVE:
		return
	state = GameState.ROUND_END
	player.controls_enabled = false
	for bot in bots:
		if is_instance_valid(bot):
			bot.set_combat_enabled(false)
	if victory:
		player_score += 1
		SaveManager.instance.add_money(ROUND_WIN_REWARD)
		SfxManager.instance.play("round_win", 0.0)
	else:
		bot_score += 1
		SaveManager.instance.add_money(ROUND_LOSS_REWARD)
		SfxManager.instance.play("round_lose", 0.0)
	hud.update_score(player_score, bot_score)
	var seq := round_seq
	await get_tree().create_timer(0.9).timeout
	if seq != round_seq:
		return
	# Проверяем конец матча.
	if player_score >= settings.match_rounds or bot_score >= settings.match_rounds:
		_finish_match(player_score >= settings.match_rounds)
	else:
		hud.show_round_end(victory, kills, deaths, player_score, bot_score)


func _finish_match(win: bool) -> void:
	state = GameState.MATCH_END
	if win:
		SaveManager.instance.add_money(MATCH_WIN_BONUS)
		SaveManager.instance.add_match_win()
	hud.show_match_end(win, player_score, bot_score)


func _back_to_menu() -> void:
	round_seq += 1
	state = GameState.IN_MENU
	get_tree().paused = false
	for bot in bots:
		if is_instance_valid(bot):
			bot.queue_free()
	bots.clear()
	if player != null and is_instance_valid(player):
		player.queue_free()
	player = null
	hud.visible = false
	menu.visible = true
	menu.make_root_visible()
	menu.show_main()
	menu_camera.make_current()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


# ---------------------------------------------------------------------------
# Пауза и глобальный ввод.
# ---------------------------------------------------------------------------

func _resume_game() -> void:
	get_tree().paused = false
	menu.hide_all()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _quit_to_menu() -> void:
	get_tree().paused = false
	_back_to_menu()


func _set_paused(value: bool) -> void:
	get_tree().paused = value
	if value:
		menu.visible = true
		menu.make_root_visible()
		menu.show_pause()
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	else:
		menu.hide_all()
		menu.visible = false
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _on_menu_esc() -> void:
	if get_tree().paused:
		_resume_game()
		return
	match state:
		GameState.IN_MENU:
			menu.go_back()
		GameState.MATCH_END:
			_back_to_menu()
		GameState.FREEZE, GameState.LIVE, GameState.ROUND_END:
			_set_paused(true)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("restart_round"):
		if state == GameState.ROUND_END:
			_begin_round()
		elif state == GameState.MATCH_END:
			_back_to_menu()
