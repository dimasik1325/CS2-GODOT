class_name MapBuilder
extends Node3D
## Процедурный генератор карт: 4 визуальные темы (Dust, Winter, Industry,
## Sunset) и 3 планировки (Arena, Crossroads, Compound). Строит пол, стены
## по периметру, укрытия и пропсы; всё со StaticBody3D + CollisionShape3D.

const ARENA_HALF := 30.0
const WALL_HEIGHT := 6.0

const THEME_NAMES: Array[String] = ["Dust", "Winter", "Industry", "Sunset"]
const LAYOUT_NAMES: Array[String] = ["Arena", "Crossroads", "Compound"]

const THEMES: Array[Dictionary] = [
	{
		"floor": Color(0.76, 0.66, 0.46), "floor_dark": Color(0.66, 0.56, 0.38),
		"wall": Color(0.79, 0.69, 0.5), "trim": Color(0.55, 0.46, 0.32),
		"crates": [Color(0.52, 0.36, 0.2), Color(0.45, 0.3, 0.16), Color(0.6, 0.44, 0.26)],
		"crate_lid": Color(0.4, 0.27, 0.14), "barrel": Color(0.5, 0.16, 0.12),
		"sand": Color(0.7, 0.62, 0.44), "container": Color(0.5, 0.3, 0.14),
		"sky_top": Color(0.22, 0.46, 0.82), "sky_horizon": Color(0.83, 0.81, 0.72),
		"ground_horizon": Color(0.79, 0.74, 0.63), "ground_bottom": Color(0.5, 0.45, 0.36),
		"sun_color": Color(1.0, 0.94, 0.82), "sun_energy": 1.25, "sun_deg": Vector3(-48.0, -32.0, 0.0),
		"fog_color": Color(0.85, 0.79, 0.66), "fog_density": 0.0035, "ambient": 1.0,
	},
	{
		"floor": Color(0.85, 0.87, 0.9), "floor_dark": Color(0.76, 0.79, 0.84),
		"wall": Color(0.62, 0.63, 0.65), "trim": Color(0.45, 0.47, 0.5),
		"crates": [Color(0.35, 0.28, 0.2), Color(0.5, 0.4, 0.28), Color(0.3, 0.25, 0.18)],
		"crate_lid": Color(0.25, 0.2, 0.14), "barrel": Color(0.2, 0.35, 0.5),
		"sand": Color(0.75, 0.77, 0.8), "container": Color(0.3, 0.45, 0.55),
		"sky_top": Color(0.55, 0.68, 0.85), "sky_horizon": Color(0.85, 0.88, 0.92),
		"ground_horizon": Color(0.8, 0.83, 0.88), "ground_bottom": Color(0.6, 0.62, 0.66),
		"sun_color": Color(0.9, 0.95, 1.0), "sun_energy": 0.95, "sun_deg": Vector3(-38.0, 25.0, 0.0),
		"fog_color": Color(0.8, 0.85, 0.9), "fog_density": 0.006, "ambient": 1.05,
	},
	{
		"floor": Color(0.28, 0.28, 0.3), "floor_dark": Color(0.24, 0.24, 0.26),
		"wall": Color(0.42, 0.45, 0.5), "trim": Color(0.3, 0.32, 0.36),
		"crates": [Color(0.75, 0.45, 0.12), Color(0.6, 0.35, 0.1), Color(0.5, 0.5, 0.52)],
		"crate_lid": Color(0.4, 0.25, 0.08), "barrel": Color(0.75, 0.5, 0.1),
		"sand": Color(0.45, 0.44, 0.4), "container": Color(0.65, 0.4, 0.12),
		"sky_top": Color(0.35, 0.38, 0.45), "sky_horizon": Color(0.65, 0.66, 0.7),
		"ground_horizon": Color(0.55, 0.56, 0.6), "ground_bottom": Color(0.4, 0.4, 0.44),
		"sun_color": Color(0.85, 0.85, 0.9), "sun_energy": 0.85, "sun_deg": Vector3(-42.0, 10.0, 0.0),
		"fog_color": Color(0.5, 0.52, 0.55), "fog_density": 0.0045, "ambient": 1.0,
	},
	{
		"floor": Color(0.65, 0.45, 0.34), "floor_dark": Color(0.55, 0.38, 0.3),
		"wall": Color(0.58, 0.36, 0.28), "trim": Color(0.4, 0.26, 0.2),
		"crates": [Color(0.5, 0.34, 0.2), Color(0.42, 0.28, 0.16), Color(0.6, 0.42, 0.24)],
		"crate_lid": Color(0.35, 0.24, 0.14), "barrel": Color(0.4, 0.15, 0.12),
		"sand": Color(0.6, 0.44, 0.33), "container": Color(0.45, 0.28, 0.16),
		"sky_top": Color(0.28, 0.3, 0.55), "sky_horizon": Color(0.95, 0.6, 0.35),
		"ground_horizon": Color(0.75, 0.5, 0.35), "ground_bottom": Color(0.45, 0.32, 0.26),
		"sun_color": Color(1.0, 0.75, 0.5), "sun_energy": 1.1, "sun_deg": Vector3(-24.0, -55.0, 0.0),
		"fog_color": Color(0.8, 0.55, 0.4), "fog_density": 0.004, "ambient": 1.0,
	},
]

var player_spawn := Vector3(0.0, 0.15, 24.0)
var bot_spawns: Array[Vector3] = []

var mat_floor: StandardMaterial3D
var mat_floor_dark: StandardMaterial3D
var mat_wall: StandardMaterial3D
var mat_trim: StandardMaterial3D
var mat_sand: StandardMaterial3D
var mat_container: StandardMaterial3D
var wood_mats: Array[StandardMaterial3D] = []
var mat_barrel: StandardMaterial3D
var mat_barrel_2: StandardMaterial3D


func clear_map() -> void:
	for child in get_children():
		child.queue_free()


func build_map(theme_index: int, layout_index: int) -> void:
	clear_map()
	var theme := THEMES[clampi(theme_index, 0, THEMES.size() - 1)]
	_build_materials(theme)
	_build_base(theme)
	match clampi(layout_index, 0, LAYOUT_NAMES.size() - 1):
		0:
			_layout_arena()
		1:
			_layout_crossroads()
		2:
			_layout_compound()


func get_theme(index: int) -> Dictionary:
	return THEMES[clampi(index, 0, THEMES.size() - 1)]


# ---------------------------------------------------------------------------
# Материалы.
# ---------------------------------------------------------------------------

func _build_materials(theme: Dictionary) -> void:
	mat_floor = _mat(theme["floor"])
	mat_floor_dark = _mat(theme["floor_dark"])
	mat_wall = _mat(theme["wall"])
	mat_trim = _mat(theme["trim"])
	mat_sand = _mat(theme["sand"])
	mat_container = _mat(theme["container"])
	mat_container.metallic = 0.4
	mat_container.roughness = 0.6
	mat_barrel = _mat(theme["barrel"])
	mat_barrel.metallic = 0.5
	mat_barrel.roughness = 0.55
	mat_barrel_2 = _mat((theme["barrel"] as Color).lightened(0.25))
	mat_barrel_2.metallic = 0.5
	mat_barrel_2.roughness = 0.55
	wood_mats = []
	for color in theme["crates"]:
		wood_mats.append(_mat(color))
	mat_trim.metallic = 0.1


func _mat(color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 0.9
	m.metallic = 0.0
	return m


# ---------------------------------------------------------------------------
# Базовая геометрия.
# ---------------------------------------------------------------------------

func _build_base(theme: Dictionary) -> void:
	var half := ARENA_HALF
	# Пол.
	_add_box(Vector3(0.0, -0.25, 0.0), Vector3(half * 2.0 + 4.0, 0.5, half * 2.0 + 4.0), mat_floor, 0.0)
	# Пятна на полу (только меш).
	_add_patch(Vector3(-8.0, 0.012, 10.0), Vector3(10.0, 0.02, 7.0))
	_add_patch(Vector3(12.0, 0.012, -6.0), Vector3(8.0, 0.02, 9.0))
	_add_patch(Vector3(-12.0, 0.012, -14.0), Vector3(9.0, 0.02, 8.0))
	_add_patch(Vector3(5.0, 0.012, 18.0), Vector3(6.0, 0.02, 5.0))
	_add_patch(Vector3(-2.0, 0.012, -22.0), Vector3(7.0, 0.02, 5.0))
	# Стены по периметру.
	_add_box(Vector3(0.0, WALL_HEIGHT * 0.5, -(half + 0.5)), Vector3(half * 2.0 + 3.0, WALL_HEIGHT, 1.0), mat_wall, 0.0)
	_add_box(Vector3(0.0, WALL_HEIGHT * 0.5, half + 0.5), Vector3(half * 2.0 + 3.0, WALL_HEIGHT, 1.0), mat_wall, 0.0)
	_add_box(Vector3(-(half + 0.5), WALL_HEIGHT * 0.5, 0.0), Vector3(1.0, WALL_HEIGHT, half * 2.0 + 3.0), mat_wall, 0.0)
	_add_box(Vector3(half + 0.5, WALL_HEIGHT * 0.5, 0.0), Vector3(1.0, WALL_HEIGHT, half * 2.0 + 3.0), mat_wall, 0.0)
	# Окантовка стен.
	_add_box(Vector3(0.0, WALL_HEIGHT + 0.15, -(half + 0.5)), Vector3(half * 2.0 + 3.0, 0.3, 1.3), mat_trim, 0.0)
	_add_box(Vector3(0.0, WALL_HEIGHT + 0.15, half + 0.5), Vector3(half * 2.0 + 3.0, 0.3, 1.3), mat_trim, 0.0)
	_add_box(Vector3(-(half + 0.5), WALL_HEIGHT + 0.15, 0.0), Vector3(1.3, 0.3, half * 2.0 + 3.0), mat_trim, 0.0)
	_add_box(Vector3(half + 0.5, WALL_HEIGHT + 0.15, 0.0), Vector3(1.3, 0.3, half * 2.0 + 3.0), mat_trim, 0.0)
	# Колонны вдоль стен для «реалистичности».
	for x in [-24.0, -12.0, 0.0, 12.0, 24.0]:
		_add_box(Vector3(x, 3.0, -(half + 0.1)), Vector3(1.4, 6.0, 1.2), mat_trim, 0.0)
		_add_box(Vector3(x, 3.0, half + 0.1), Vector3(1.4, 6.0, 1.2), mat_trim, 0.0)
	for z in [-18.0, -6.0, 6.0, 18.0]:
		_add_box(Vector3(-(half + 0.1), 3.0, z), Vector3(1.2, 6.0, 1.4), mat_trim, 0.0)
		_add_box(Vector3(half + 0.1, 3.0, z), Vector3(1.2, 6.0, 1.4), mat_trim, 0.0)


# ---------------------------------------------------------------------------
# Планировки.
# ---------------------------------------------------------------------------

func _layout_arena() -> void:
	# L-образные укрытия в четырёх углах.
	_add_box(Vector3(-20.0, 1.5, 6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(-16.5, 1.5, 10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	_add_box(Vector3(20.0, 1.5, 6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(16.5, 1.5, 10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	_add_box(Vector3(-20.0, 1.5, -6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(-16.5, 1.5, -10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	_add_box(Vector3(20.0, 1.5, -6.0), Vector3(0.6, 3.0, 9.0), mat_wall, 0.0)
	_add_box(Vector3(16.5, 1.5, -10.6), Vector3(7.7, 3.0, 0.6), mat_wall, 0.0)
	# Низкие стенки.
	_add_box(Vector3(0.0, 0.6, 10.0), Vector3(6.0, 1.2, 0.6), mat_wall, 0.0)
	_add_box(Vector3(0.0, 0.6, -10.0), Vector3(6.0, 1.2, 0.6), mat_wall, 0.0)
	_add_box(Vector3(13.0, 0.6, 6.0), Vector3(0.6, 1.2, 7.0), mat_wall, 0.0)
	_add_box(Vector3(-13.0, 0.6, 6.0), Vector3(0.6, 1.2, 7.0), mat_wall, 0.0)
	# Центр.
	_add_crate(Vector3(0.0, 0.9, 0.0), 1.8, 0.0)
	_add_crate(Vector3(-2.0, 0.5, 1.4), 1.0, 12.0)
	_add_crate(Vector3(2.2, 0.5, -1.6), 1.0, -9.0)
	_add_crate(Vector3(0.1, 2.3, 0.1), 1.0, 5.0)
	# «Ворота» из ящиков.
	_add_crate(Vector3(-9.0, 0.7, 4.0), 1.4, 6.0)
	_add_crate(Vector3(-9.0, 0.7, 2.6), 1.4, -4.0)
	_add_crate(Vector3(-9.0, 0.7, 1.2), 1.4, 3.0)
	_add_crate(Vector3(-9.0, 1.9, 2.6), 1.0, 0.0)
	_add_crate(Vector3(9.0, 0.7, -2.0), 1.4, -7.0)
	_add_crate(Vector3(9.0, 0.7, -3.4), 1.4, 5.0)
	_add_crate(Vector3(9.0, 0.7, -4.8), 1.4, -3.0)
	_add_crate(Vector3(9.0, 1.9, -3.4), 1.0, 0.0)
	# Сторона игрока.
	_add_crate(Vector3(-5.0, 0.5, 15.0), 1.0, 8.0)
	_add_crate(Vector3(6.0, 0.7, 16.0), 1.4, -6.0)
	_add_crate(Vector3(14.0, 0.5, 12.0), 1.0, 4.0)
	_add_crate(Vector3(-14.0, 0.7, 14.0), 1.4, -8.0)
	_add_crate(Vector3(-2.0, 0.5, 20.0), 1.0, 3.0)
	# Сторона ботов.
	_add_crate(Vector3(-6.0, 0.7, -14.0), 1.4, 7.0)
	_add_crate(Vector3(6.0, 0.5, -13.0), 1.0, -5.0)
	_add_crate(Vector3(-14.0, 0.7, -10.0), 1.4, 4.0)
	_add_crate(Vector3(14.0, 0.7, -11.0), 1.4, -6.0)
	_add_crate(Vector3(0.0, 0.9, -18.0), 1.8, 2.0)
	_add_crate(Vector3(-1.9, 0.5, -18.2), 1.0, 0.0)
	_add_crate(Vector3(18.0, 0.5, -20.0), 1.0, 9.0)
	_add_crate(Vector3(-18.0, 0.7, -19.0), 1.4, -7.0)
	_add_crate(Vector3(22.0, 0.5, -8.0), 1.0, 5.0)
	_add_crate(Vector3(-22.0, 0.5, -9.0), 1.0, -4.0)
	# Контейнер и мешки.
	_add_container(Vector3(-25.0, 0.0, -2.0), 0.0)
	_add_container(Vector3(25.5, 0.0, 3.0), 90.0)
	_add_sandbags(Vector3(-4.0, 0.0, 8.0), 0.0)
	_add_sandbags(Vector3(5.0, 0.0, -8.5), 25.0)
	# Бочки.
	_add_barrel(Vector3(-4.5, 0.0, 8.5), true)
	_add_barrel(Vector3(4.8, 0.0, 9.5), false)
	_add_barrel(Vector3(12.0, 0.0, 2.0), true)
	_add_barrel(Vector3(-12.0, 0.0, -3.0), false)
	_add_barrel(Vector3(4.5, 0.0, -9.0), true)
	_add_barrel(Vector3(-7.0, 0.0, -16.0), false)
	_add_barrel(Vector3(7.6, 0.0, 17.6), true)
	player_spawn = Vector3(0.0, 0.15, 24.0)
	bot_spawns = [
		Vector3(-20.0, 0.15, -20.0), Vector3(20.0, 0.15, -20.0),
		Vector3(-24.0, 0.15, -2.0), Vector3(24.0, 0.15, -2.0),
		Vector3(0.0, 0.15, -24.0), Vector3(-12.0, 0.15, -18.0),
		Vector3(12.0, 0.15, -18.0), Vector3(-8.0, 0.15, -24.0),
	]


func _layout_crossroads() -> void:
	# Центральная площадь с крестом низких стен и четырьмя контейнерами.
	_add_box(Vector3(0.0, 0.6, 3.0), Vector3(10.0, 1.2, 0.6), mat_wall, 0.0)
	_add_box(Vector3(0.0, 0.6, -3.0), Vector3(10.0, 1.2, 0.6), mat_wall, 0.0)
	_add_box(Vector3(3.0, 0.6, 0.0), Vector3(0.6, 1.2, 10.0), mat_wall, 0.0)
	_add_box(Vector3(-3.0, 0.6, 0.0), Vector3(0.6, 1.2, 10.0), mat_wall, 0.0)
	_add_container(Vector3(-8.0, 0.0, 0.0), 0.0)
	_add_container(Vector3(8.0, 0.0, 0.0), 0.0)
	_add_container(Vector3(0.0, 0.0, -9.0), 90.0)
	_add_container(Vector3(0.0, 0.0, 9.0), 90.0)
	# Угловые бункеры.
	_add_box(Vector3(-22.0, 1.75, -22.0), Vector3(8.0, 3.5, 8.0), mat_wall, 0.0)
	_add_box(Vector3(22.0, 1.75, -22.0), Vector3(8.0, 3.5, 8.0), mat_wall, 0.0)
	_add_box(Vector3(-22.0, 1.75, 22.0), Vector3(8.0, 3.5, 8.0), mat_wall, 0.0)
	_add_box(Vector3(22.0, 1.75, 22.0), Vector3(8.0, 3.5, 8.0), mat_wall, 0.0)
	# Диагонали.
	_add_crate(Vector3(-14.0, 0.7, 14.0), 1.4, 8.0)
	_add_crate(Vector3(-12.6, 0.5, 14.2), 1.0, -6.0)
	_add_crate(Vector3(14.0, 0.7, 14.0), 1.4, -8.0)
	_add_crate(Vector3(14.2, 0.5, 12.6), 1.0, 4.0)
	_add_crate(Vector3(-14.0, 0.7, -14.0), 1.4, -4.0)
	_add_crate(Vector3(14.0, 0.7, -14.0), 1.4, 6.0)
	_add_crate(Vector3(14.4, 0.5, -12.4), 1.0, -9.0)
	# Прикрытия спавнов.
	_add_crate(Vector3(-5.0, 0.5, 20.0), 1.0, 5.0)
	_add_crate(Vector3(5.0, 0.7, 20.0), 1.4, -5.0)
	_add_crate(Vector3(-5.0, 0.5, -20.0), 1.0, -7.0)
	_add_crate(Vector3(5.0, 0.7, -20.0), 1.4, 3.0)
	_add_sandbags(Vector3(-10.0, 0.0, 17.0), 0.0)
	_add_sandbags(Vector3(10.0, 0.0, -17.0), 15.0)
	_add_sandbags(Vector3(12.0, 0.0, 5.0), 90.0)
	_add_barrel(Vector3(-9.5, 0.0, 15.0), true)
	_add_barrel(Vector3(11.0, 0.0, -15.5), false)
	_add_barrel(Vector3(-3.5, 0.0, 0.5), true)
	_add_barrel(Vector3(3.5, 0.0, -0.5), false)
	_add_barrel(Vector3(17.0, 0.0, 10.0), true)
	_add_barrel(Vector3(-17.0, 0.0, -10.0), false)
	player_spawn = Vector3(0.0, 0.15, 26.0)
	bot_spawns = [
		Vector3(-22.0, 0.15, -26.0), Vector3(22.0, 0.15, -26.0),
		Vector3(-26.0, 0.15, -8.0), Vector3(26.0, 0.15, -8.0),
		Vector3(0.0, 0.15, -26.0), Vector3(-14.0, 0.15, -20.0),
		Vector3(14.0, 0.15, -20.0), Vector3(8.0, 0.15, -24.0),
	]


func _layout_compound() -> void:
	# Центральное строение: полый «форт» с воротами — внутри можно ходить.
	# Передняя стена с проёмом-воротами.
	_add_box(Vector3(-4.5, 1.5, 4.0), Vector3(3.0, 3.0, 0.5), mat_wall, 0.0)
	_add_box(Vector3(4.5, 1.5, 4.0), Vector3(3.0, 3.0, 0.5), mat_wall, 0.0)
	_add_box(Vector3(0.0, 3.25, 4.0), Vector3(12.0, 1.5, 0.5), mat_wall, 0.0)
	# Задняя стена — глухая.
	_add_box(Vector3(0.0, 1.5, -6.0), Vector3(12.0, 3.0, 0.5), mat_wall, 0.0)
	# Боковые стены.
	_add_box(Vector3(-6.0, 1.5, -1.0), Vector3(0.5, 3.0, 9.5), mat_wall, 0.0)
	_add_box(Vector3(6.0, 1.5, -1.0), Vector3(0.5, 3.0, 9.5), mat_wall, 0.0)
	# Навес-крыша на столбах над внутренним двором.
	_add_box(Vector3(0.0, 3.6, -1.0), Vector3(13.0, 0.4, 11.0), mat_trim, 0.0)
	_add_box(Vector3(-5.6, 5.5, 4.0), Vector3(0.5, 3.6, 0.5), mat_trim, 0.0)
	_add_box(Vector3(5.6, 5.5, 4.0), Vector3(0.5, 3.6, 0.5), mat_trim, 0.0)
	_add_box(Vector3(-5.6, 5.5, -6.0), Vector3(0.5, 3.6, 0.5), mat_trim, 0.0)
	_add_box(Vector3(5.6, 5.5, -6.0), Vector3(0.5, 3.6, 0.5), mat_trim, 0.0)
	# Ящики внутри форта (на них можно запрыгнуть и выглянуть поверх стен).
	_add_crate(Vector3(-3.0, 0.5, 1.0), 1.0, 6.0)
	_add_crate(Vector3(3.0, 0.5, -2.0), 1.0, -8.0)
	_add_crate(Vector3(0.5, 0.5, -3.5), 1.0, 3.0)
	# Внешние укрытия.
	_add_container(Vector3(-18.0, 0.0, -6.0), 90.0)
	_add_container(Vector3(18.0, 0.0, 6.0), 90.0)
	_add_container(Vector3(-24.0, 0.0, 14.0), 0.0)
	_add_container(Vector3(24.0, 0.0, -14.0), 0.0)
	_add_crate(Vector3(-8.0, 0.7, -12.0), 1.4, 5.0)
	_add_crate(Vector3(8.0, 0.7, -12.0), 1.4, -5.0)
	_add_crate(Vector3(-10.0, 0.5, 12.0), 1.0, -6.0)
	_add_crate(Vector3(10.0, 0.5, 12.0), 1.0, 8.0)
	_add_crate(Vector3(0.0, 0.9, -18.0), 1.8, 0.0)
	_add_crate(Vector3(-2.0, 0.5, -18.0), 1.0, 12.0)
	_add_crate(Vector3(16.0, 0.5, -20.0), 1.0, -4.0)
	_add_crate(Vector3(-16.0, 0.7, -20.0), 1.4, 7.0)
	_add_sandbags(Vector3(0.0, 0.0, 12.0), 0.0)
	_add_sandbags(Vector3(-6.0, 0.0, -8.0), 90.0)
	_add_sandbags(Vector3(6.0, 0.0, -8.0), 90.0)
	_add_barrel(Vector3(-3.5, 0.0, 4.0), true)
	_add_barrel(Vector3(3.5, 0.0, 4.0), false)
	_add_barrel(Vector3(-12.0, 0.0, 2.0), false)
	_add_barrel(Vector3(12.0, 0.0, -2.0), true)
	_add_barrel(Vector3(6.5, 0.0, -16.5), true)
	_add_barrel(Vector3(-6.5, 0.0, -16.5), false)
	player_spawn = Vector3(0.0, 0.15, 25.0)
	bot_spawns = [
		Vector3(-22.0, 0.15, -22.0), Vector3(22.0, 0.15, -22.0),
		Vector3(-25.0, 0.15, 4.0), Vector3(25.0, 0.15, -4.0),
		Vector3(0.0, 0.15, -25.0), Vector3(-14.0, 0.15, -14.0),
		Vector3(14.0, 0.15, -14.0), Vector3(-8.0, 0.15, -24.0),
	]


# ---------------------------------------------------------------------------
# Пропсы.
# ---------------------------------------------------------------------------

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
	mesh_instance.material_override = mat_floor_dark
	mesh_instance.position = center
	add_child(mesh_instance)


## Деревянный ящик: корпус + крышка + диагональные планки.
func _add_crate(center: Vector3, s: float, yaw_deg: float) -> StaticBody3D:
	var mat: StandardMaterial3D = wood_mats[randi() % wood_mats.size()]
	var body := _add_box(center, Vector3(s, s, s), mat, yaw_deg)
	var lid := MeshInstance3D.new()
	var lid_mesh := BoxMesh.new()
	lid_mesh.size = Vector3(s * 1.06, s * 0.12, s * 1.06)
	lid.mesh = lid_mesh
	lid.material_override = mat_trim
	lid.position = Vector3(0.0, s * 0.5 + s * 0.02, 0.0)
	lid.rotation_degrees.y = yaw_deg
	body.add_child(lid)
	for i in 2:
		var plank := MeshInstance3D.new()
		var plank_mesh := BoxMesh.new()
		plank_mesh.size = Vector3(s * 0.9, 0.06, s * 0.14)
		plank.mesh = plank_mesh
		plank.material_override = mat_floor_dark
		plank.position = Vector3(0.0, s * 0.5 + s * 0.09, 0.0)
		plank.rotation_degrees = Vector3(0.0, yaw_deg + (30.0 if i == 0 else -30.0), 0.0)
		body.add_child(plank)
	return body


## Морской контейнер с вертикальными рёбрами.
func _add_container(pos: Vector3, yaw_deg: float) -> void:
	var size := Vector3(2.5, 2.6, 6.0)
	var body := _add_box(pos + Vector3(0.0, 1.3, 0.0), size, mat_container, yaw_deg)
	for i in 5:
		var offset := -2.7 + i * 1.35
		var rib_a := MeshInstance3D.new()
		var rib_mesh := BoxMesh.new()
		rib_mesh.size = Vector3(0.12, 2.62, 0.14)
		rib_a.mesh = rib_mesh
		rib_a.material_override = mat_trim
		rib_a.position = Vector3(-1.2, 0.0, offset)
		body.add_child(rib_a)
		var rib_b := rib_a.duplicate()
		rib_b.position = Vector3(1.2, 0.0, offset)
		body.add_child(rib_b)


## Бочка с двумя обручами.
func _add_barrel(pos: Vector3, primary: bool) -> void:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	var mesh_instance := MeshInstance3D.new()
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = 0.42
	cylinder.bottom_radius = 0.42
	cylinder.height = 0.95
	mesh_instance.mesh = cylinder
	mesh_instance.material_override = mat_barrel if primary else mat_barrel_2
	body.add_child(mesh_instance)
	for i in 2:
		var rim := MeshInstance3D.new()
		var rim_mesh := CylinderMesh.new()
		rim_mesh.top_radius = 0.45
		rim_mesh.bottom_radius = 0.45
		rim_mesh.height = 0.07
		rim.mesh = rim_mesh
		rim.material_override = mat_trim
		rim.position = Vector3(0.0, 0.3 if i == 0 else -0.3, 0.0)
		body.add_child(rim)
	var col := CollisionShape3D.new()
	var shape := CylinderShape3D.new()
	shape.radius = 0.42
	shape.height = 0.95
	col.shape = shape
	body.add_child(col)
	body.position = pos + Vector3(0.0, 0.475, 0.0)
	add_child(body)


## Линия мешков с песком (три мешка со ступенькой).
func _add_sandbags(pos: Vector3, yaw_deg: float) -> void:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	for i in 3:
		var lower := MeshInstance3D.new()
		var lower_mesh := BoxMesh.new()
		lower_mesh.size = Vector3(1.0, 0.45, 0.7)
		lower.mesh = lower_mesh
		lower.material_override = mat_sand
		lower.position = Vector3(-0.9 + i * 0.9, 0.225, 0.0)
		body.add_child(lower)
		var upper := MeshInstance3D.new()
		var upper_mesh := BoxMesh.new()
		upper_mesh.size = Vector3(0.9, 0.35, 0.6)
		upper.mesh = upper_mesh
		upper.material_override = mat_sand
		upper.position = Vector3(-0.9 + i * 0.9, 0.6, 0.02)
		body.add_child(upper)
	var col := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(3.0, 0.8, 0.75)
	col.shape = shape
	col.position = Vector3(0.0, 0.4, 0.0)
	body.add_child(col)
	body.position = pos
	body.rotation_degrees.y = yaw_deg
	add_child(body)
