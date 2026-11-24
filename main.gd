extends Node3D
## CS2-GODOT: корневой скрипт единственной сцены (Main.tscn).
## Вся игра строится процедурно отсюда: небо и освещение, карта в стиле Dust 2,
## игрок, боты, HUD, регистрация клавиш и система раундов.
##
## ВАЖНО: никакие узлы, кроме корневого Node3D, в редакторе создавать не нужно.

const ARENA_HALF := 30.0
const WALL_HEIGHT := 6.0
const BOT_COUNT := 5
const PLAYER_SPAWN := Vector3(0.0, 0.15, 24.0)
const PLAYER_SPAWN_YAW := 0.0

const BOT_SPAWNS: Array = [
	Vector3(-20.0, 0.15, -20.0),
	Vector3(20.0, 0.15, -20.0),
	Vector3(-24.0, 0.15, -2.0),
	Vector3(24.0, 0.15, -2.0),
	Vector3(0.0, 0.15, -24.0),
]

var mat_sand: StandardMaterial3D
var mat_sand_dark: StandardMaterial3D
var mat_wall: StandardMaterial3D
var mat_trim: StandardMaterial3D
var wood_mats: Array[StandardMaterial3D] = []
var barrel_colors: Array[Color] = []

var player: PlayerController
var hud: HUDController
var bots: Array[Bot] = []

var round_active := false
var round_seq := 0
var kills := 0
var deaths := 0
var bots_alive := 0


func _ready() -> void:
	randomize()
	_register_inputs()
	_build_materials()
	_build_environment()
	_build_map()
	hud = HUDController.new()
	hud.name = "HUD"
	add_child(hud)
	player = PlayerController.new()
	player.name = "Player"
	add_child(player)
	hud.bind_player(player, player.weapon_manager)
	_start_round()


func _unhandled_input(event: InputEvent) -> void:
	if round_active:
		return
	if event.is_action_pressed("restart_round"):
		_start_round()


# ---------------------------------------------------------------------------
# Ввод: весь Input Map регистрируется кодом, настройки проекта не требуются.
# Используются ФИЗИЧЕСКИЕ коды клавиш — раскладка (RU/EN) не имеет значения.
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
	if not InputMap.has_action("fire"):
		InputMap.add_action("fire", 0.5)
		var mouse_event := InputEventMouseButton.new()
		mouse_event.button_index = MOUSE_BUTTON_LEFT
		InputMap.action_add_event("fire", mouse_event)


# ---------------------------------------------------------------------------
# Окружение: процедурное небо, туман, солнце с тенями.
# ---------------------------------------------------------------------------

func _build_environment() -> void:
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.22, 0.46, 0.82)
	sky_material.sky_horizon_color = Color(0.83, 0.83, 0.76)
	sky_material.ground_horizon_color = Color(0.79, 0.74, 0.63)
	sky_material.ground_bottom_color = Color(0.5, 0.45, 0.36)
	sky_material.sun_angle_max = 25.0
	sky_material.sun_curve = 0.12

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_light_color = Color(0.85, 0.79, 0.66)
	env.fog_density = 0.0035
	env.fog_sky_affect = 0.12

	var world_env := WorldEnvironment.new()
	world_env.environment = env
	add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.light_color = Color(1.0, 0.94, 0.82)
	sun.light_energy = 1.25
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 90.0
	sun.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
	add_child(sun)


func _build_materials() -> void:
	mat_sand = _make_mat(Color(0.76, 0.66, 0.46), 1.0, 0.0)
	mat_sand_dark = _make_mat(Color(0.66, 0.56, 0.38), 1.0, 0.0)
	mat_wall = _make_mat(Color(0.79, 0.69, 0.5), 0.95, 0.0)
	mat_trim = _make_mat(Color(0.55, 0.46, 0.32), 0.9, 0.0)
	wood_mats = [
		_make_mat(Color(0.52, 0.36, 0.2), 0.85, 0.0),
		_make_mat(Color(0.45, 0.3, 0.16), 0.85, 0.0),
		_make_mat(Color(0.6, 0.44, 0.26), 0.85, 0.0),
	]
	barrel_colors = [
		Color(0.5, 0.16, 0.12),
		Color(0.16, 0.3, 0.45),
		Color(0.32, 0.4, 0.16),
	]


func _make_mat(color: Color, roughness: float, metallic: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	m.metallic = metallic
	return m


# ---------------------------------------------------------------------------
# Карта: песчаный пол, стены по периметру, деревянные ящики разных высот,
# низкие стенки, L-образные укрытия и бочки. Всё со StaticBody3D + коллизией.
# ---------------------------------------------------------------------------

func _build_map() -> void:
	var half := ARENA_HALF
	# Пол.
	_add_box(Vector3(0.0, -0.25, 0.0), Vector3(half * 2.0 + 4.0, 0.5, half * 2.0 + 4.0), mat_sand, 0.0)
	# Песчаные пятна — только меш, без коллизии.
	_add_patch(Vector3(-8.0, 0.012, 10.0), Vector3(10.0, 0.02, 7.0))
	_add_patch(Vector3(12.0, 0.012, -6.0), Vector3(8.0, 0.02, 9.0))
	_add_patch(Vector3(-12.0, 0.012, -14.0), Vector3(9.0, 0.02, 8.0))
	_add_patch(Vector3(5.0, 0.012, 18.0), Vector3(6.0, 0.02, 5.0))
	# Стены по периметру.
	_add_box(Vector3(0.0, WALL_HEIGHT * 0.5, -(half + 0.5)), Vector3(half * 2.0 + 3.0, WALL_HEIGHT, 1.0), mat_wall, 0.0)
	_add_box(Vector3(0.0, WALL_HEIGHT * 0.5, half + 0.5), Vector3(half * 2.0 + 3.0, WALL_HEIGHT, 1.0), mat_wall, 0.0)
	_add_box(Vector3(-(half + 0.5), WALL_HEIGHT * 0.5, 0.0), Vector3(1.0, WALL_HEIGHT, half * 2.0 + 3.0), mat_wall, 0.0)
	_add_box(Vector3(half + 0.5, WALL_HEIGHT * 0.5, 0.0), Vector3(1.0, WALL_HEIGHT, half * 2.0 + 3.0), mat_wall, 0.0)
	# Верхняя окантовка стен.
	_add_box(Vector3(0.0, WALL_HEIGHT + 0.15, -(half + 0.5)), Vector3(half * 2.0 + 3.0, 0.3, 1.3), mat_trim, 0.0)
	_add_box(Vector3(0.0, WALL_HEIGHT + 0.15, half + 0.5), Vector3(half * 2.0 + 3.0, 0.3, 1.3), mat_trim, 0.0)
	_add_box(Vector3(-(half + 0.5), WALL_HEIGHT + 0.15, 0.0), Vector3(1.3, 0.3, half * 2.0 + 3.0), mat_trim, 0.0)
	_add_box(Vector3(half + 0.5, WALL_HEIGHT + 0.15, 0.0), Vector3(1.3, 0.3, half * 2.0 + 3.0), mat_trim, 0.0)
	# L-образные укрытия в углах.
	_add_box(Vector3(-20.0, 1.5, 6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(-16.5, 1.5, 10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	_add_box(Vector3(20.0, 1.5, 6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(16.5, 1.5, 10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	_add_box(Vector3(-20.0, 1.5, -6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(-16.5, 1.5, -10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	_add_box(Vector3(20.0, 1.5, -6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(16.5, 1.5, -10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	# Низкие стенки (укрытие по грудь).
	_add_box(Vector3(0.0, 0.6, 10.0), Vector3(6.0, 1.2, 0.6), mat_wall, 0.0)
	_add_box(Vector3(0.0, 0.6, -10.0), Vector3(6.0, 1.2, 0.6), mat_wall, 0.0)
	_add_box(Vector3(13.0, 0.6, 6.0), Vector3(0.6, 1.2, 7.0), mat_wall, 0.0)
	_add_box(Vector3(-13.0, 0.6, 6.0), Vector3(0.6, 1.2, 7.0), mat_wall, 0.0)
	# Центр карты (mid).
	_add_crate_ground(0.0, 0.0, 1.8, 0.0)
	_add_crate_ground(-2.0, 1.4, 1.0, 12.0)
	_add_crate_ground(2.2, -1.6, 1.0, -9.0)
	_add_crate(Vector3(0.1, 2.3, 0.1), 1.0, 5.0)
	# «Ворота» из ящиков слева.
	_add_crate_ground(-9.0, 4.0, 1.4, 6.0)
	_add_crate_ground(-9.0, 2.6, 1.4, -4.0)
	_add_crate_ground(-9.0, 1.2, 1.4, 3.0)
	_add_crate(Vector3(-9.0, 1.9, 2.6), 1.0, 0.0)
	# «Ворота» из ящиков справа.
	_add_crate_ground(9.0, -2.0, 1.4, -7.0)
	_add_crate_ground(9.0, -3.4, 1.4, 5.0)
	_add_crate_ground(9.0, -4.8, 1.4, -3.0)
	_add_crate(Vector3(9.0, 1.9, -3.4), 1.0, 0.0)
	# Сторона игрока (спавн).
	_add_crate_ground(-5.0, 15.0, 1.0, 8.0)
	_add_crate_ground(6.0, 16.0, 1.4, -6.0)
	_add_crate_ground(14.0, 12.0, 1.0, 4.0)
	_add_crate_ground(-14.0, 14.0, 1.4, -8.0)
	_add_crate_ground(-2.0, 20.0, 1.0, 3.0)
	# Сторона ботов.
	_add_crate_ground(-6.0, -14.0, 1.4, 7.0)
	_add_crate_ground(6.0, -13.0, 1.0, -5.0)
	_add_crate_ground(-14.0, -10.0, 1.4, 4.0)
	_add_crate_ground(14.0, -11.0, 1.4, -6.0)
	_add_crate_ground(0.0, -18.0, 1.8, 2.0)
	_add_crate_ground(-1.9, -18.2, 1.0, 0.0)
	_add_crate_ground(18.0, -20.0, 1.0, 9.0)
	_add_crate_ground(-18.0, -19.0, 1.4, -7.0)
	_add_crate_ground(22.0, -8.0, 1.0, 5.0)
	_add_crate_ground(-22.0, -9.0, 1.0, -4.0)
	# Фланги.
	_add_crate_ground(-16.0, 4.0, 1.0, 6.0)
	_add_crate_ground(16.0, 6.0, 1.4, -5.0)
	_add_crate_ground(-18.0, -6.0, 1.0, 3.0)
	_add_crate_ground(18.0, -4.0, 1.0, -8.0)
	# Бочки.
	_add_barrel(Vector3(-4.5, 0.0, 8.5), 0)
	_add_barrel(Vector3(4.8, 0.0, 9.5), 1)
	_add_barrel(Vector3(12.0, 0.0, 2.0), 2)
	_add_barrel(Vector3(-12.0, 0.0, -3.0), 0)
	_add_barrel(Vector3(4.5, 0.0, -9.0), 1)
	_add_barrel(Vector3(-7.0, 0.0, -16.0), 2)
	_add_barrel(Vector3(7.6, 0.0, 17.6), 0)


func _add_box(center: Vector3, size: Vector3, mat: StandardMaterial3D, yaw_deg: float) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	var mesh_instance := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh_instance.mesh = box
	mesh_instance.material_override = mat
	body.add_child(mesh_instance)
	var col := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	col.shape = shape
	body.add_child(col)
	body.position = center
	body.rotation_degrees.y = yaw_deg
	add_child(body)
	return body


func _add_patch(center: Vector3, size: Vector3) -> void:
	var mesh_instance := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh_instance.mesh = box
	mesh_instance.material_override = mat_sand_dark
	mesh_instance.position = center
	add_child(mesh_instance)


func _add_crate_ground(x: float, z: float, s: float, yaw_deg: float) -> void:
	var mat: StandardMaterial3D = wood_mats[randi() % wood_mats.size()]
	_add_box(Vector3(x, s * 0.5, z), Vector3(s, s, s), mat, yaw_deg)


func _add_crate(center: Vector3, s: float, yaw_deg: float) -> void:
	var mat: StandardMaterial3D = wood_mats[randi() % wood_mats.size()]
	_add_box(center, Vector3(s, s, s), mat, yaw_deg)


func _add_barrel(pos: Vector3, color_index: int) -> void:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	var mesh_instance := MeshInstance3D.new()
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = 0.42
	cylinder.bottom_radius = 0.42
	cylinder.height = 0.95
	mesh_instance.mesh = cylinder
	var color: Color = barrel_colors[color_index % barrel_colors.size()]
	mesh_instance.material_override = _make_mat(color.darkened(randf() * 0.1), 0.55, 0.35)
	body.add_child(mesh_instance)
	var col := CollisionShape3D.new()
	var shape := CylinderShape3D.new()
	shape.radius = 0.42
	shape.height = 0.95
	col.shape = shape
	body.add_child(col)
	body.position = pos + Vector3(0.0, 0.475, 0.0)
	add_child(body)


# ---------------------------------------------------------------------------
# Игрок и боты.
# ---------------------------------------------------------------------------

func _spawn_bots() -> void:
	var spawns: Array = BOT_SPAWNS.duplicate()
	spawns.shuffle()
	for i in BOT_COUNT:
		var bot := Bot.new()
		bot.name = "Bot%d" % (i + 1)
		bot.bot_name = "Bot-%d" % (i + 1)
		bot.player = player
		bot.position = spawns[i % spawns.size()]
		add_child(bot)
		bot.died.connect(_on_bot_died)
		bots.append(bot)


# ---------------------------------------------------------------------------
# Система раундов.
# ---------------------------------------------------------------------------

func _start_round() -> void:
	round_seq += 1
	round_active = true
	for bot in bots:
		if is_instance_valid(bot):
			bot.queue_free()
	bots.clear()
	_spawn_bots()
	bots_alive = bots.size()
	player.controls_enabled = true
	player.reset_for_round(PLAYER_SPAWN, PLAYER_SPAWN_YAW)
	hud.reset_for_round()
	hud.update_kd(kills, deaths)
	hud.update_enemies(bots_alive)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _on_bot_died(bot: Node3D, weapon: String) -> void:
	var dead_bot := bot as Bot
	if dead_bot != null:
		bots.erase(dead_bot)
	if not round_active:
		return
	kills += 1
	bots_alive = maxi(0, bots_alive - 1)
	hud.update_kd(kills, deaths)
	hud.update_enemies(bots_alive)
	if dead_bot != null:
		hud.add_kill_feed("You", dead_bot.bot_name, weapon)
	hud.show_hitmarker(false, true)
	if bots_alive <= 0:
		_end_round(true)


func _on_player_died() -> void:
	if not round_active:
		return
	deaths += 1
	hud.update_kd(kills, deaths)
	hud.add_kill_feed(player.last_attacker_name, "You", "AK-47")
	_end_round(false)


func _end_round(victory: bool) -> void:
	if not round_active:
		return
	round_active = false
	player.controls_enabled = false
	for bot in bots:
		if is_instance_valid(bot):
			bot.set_combat_enabled(false)
	var seq := round_seq
	await get_tree().create_timer(0.8).timeout
	if seq != round_seq:
		return
	hud.show_round_end(victory, kills, deaths)
