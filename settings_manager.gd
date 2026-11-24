class_name SettingsManager
extends Node
## Менеджер настроек: хранит все опции, сохраняет их в user://settings.cfg
## и применяет к рендереру, окну и звуку. Доступен из любого скрипта через
## SettingsManager.instance (синглтон создаётся в main.gd).

static var instance: SettingsManager

## Ссылки, которые main.gd заполняет после построения окружения.
var sun: DirectionalLight3D = null
var env: Environment = null

# Геймплей.
var mouse_sensitivity: float = 1.0
var difficulty: int = 1          # 0 Easy, 1 Normal, 2 Hard
var bots_count: int = 5
var match_rounds: int = 8        # сколько раундов нужно выиграть для победы в матче
var map_index: int = 0

# Графика.
var shadows: bool = true
var shadow_quality: int = 1      # 0 Low, 1 Medium, 2 High
var msaa: int = 2                # 0 / 2 / 4 / 8
var resolution_scale: float = 1.0
var fog_enabled: bool = true
var brightness: float = 1.0      # экспозиция тонмаппинга

# Окно.
var fullscreen: bool = false
var vsync: bool = true

# Интерфейс.
var show_fps: bool = false
var show_radar: bool = true

# Звук.
var master_volume: float = 0.8

const SETTINGS_PATH := "user://settings.cfg"
const DIFFICULTY_NAMES: Array[String] = ["Easy", "Normal", "Hard"]
const MSAA_VALUES: Array[int] = [0, 2, 4, 8]
const MSAA_NAMES: Array[String] = ["Off", "2x", "4x", "8x"]
const SHADOW_NAMES: Array[String] = ["Low", "Medium", "High"]
const ROUNDS_VALUES: Array[int] = [3, 8, 16]


func _enter_tree() -> void:
	SettingsManager.instance = self
	load_settings()


func _exit_tree() -> void:
	if SettingsManager.instance == self:
		SettingsManager.instance = null


func get_difficulty_name() -> String:
	return DIFFICULTY_NAMES[clampi(difficulty, 0, DIFFICULTY_NAMES.size() - 1)]


func get_shadow_size() -> int:
	if shadow_quality <= 0:
		return 1024
	elif shadow_quality == 1:
		return 2048
	return 4096


func get_msaa_enum() -> int:
	var idx := MSAA_VALUES.find(msaa)
	if idx < 0:
		idx = 1
	# Viewport.MSAA_2X == 1, MSAA_4X == 2, MSAA_8X == 3, DISABLED == 0.
	var enums: Array[int] = [Viewport.MSAA_DISABLED, Viewport.MSAA_2X, Viewport.MSAA_4X, Viewport.MSAA_8X]
	return enums[idx]


func apply_graphics() -> void:
	if sun != null:
		sun.shadow_enabled = shadows
		sun.directional_shadow_size = get_shadow_size()
	if env != null:
		env.fog_enabled = fog_enabled
		env.tonemap_exposure = brightness
	var viewport := get_viewport()
	if viewport != null:
		viewport.msaa_3d = get_msaa_enum()
		viewport.scaling_3d_scale = clampf(resolution_scale, 0.5, 1.0)
	if fullscreen:
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
	else:
		if DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN:
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	if vsync:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED)
	else:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)


func apply_audio() -> void:
	var volume := clampf(master_volume, 0.0, 1.0)
	if volume <= 0.001:
		AudioServer.set_bus_volume_db(0, -80.0)
	else:
		AudioServer.set_bus_volume_db(0, linear_to_db(volume))


func apply_all() -> void:
	apply_graphics()
	apply_audio()


func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("gameplay", "mouse_sensitivity", mouse_sensitivity)
	cfg.set_value("gameplay", "difficulty", difficulty)
	cfg.set_value("gameplay", "bots_count", bots_count)
	cfg.set_value("gameplay", "match_rounds", match_rounds)
	cfg.set_value("gameplay", "map_index", map_index)
	cfg.set_value("graphics", "shadows", shadows)
	cfg.set_value("graphics", "shadow_quality", shadow_quality)
	cfg.set_value("graphics", "msaa", msaa)
	cfg.set_value("graphics", "resolution_scale", resolution_scale)
	cfg.set_value("graphics", "fog_enabled", fog_enabled)
	cfg.set_value("graphics", "brightness", brightness)
	cfg.set_value("window", "fullscreen", fullscreen)
	cfg.set_value("window", "vsync", vsync)
	cfg.set_value("ui", "show_fps", show_fps)
	cfg.set_value("ui", "show_radar", show_radar)
	cfg.set_value("audio", "master_volume", master_volume)
	cfg.save(SETTINGS_PATH)


func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SETTINGS_PATH) != OK:
		return
	mouse_sensitivity = float(cfg.get_value("gameplay", "mouse_sensitivity", mouse_sensitivity))
	difficulty = int(cfg.get_value("gameplay", "difficulty", difficulty))
	bots_count = int(cfg.get_value("gameplay", "bots_count", bots_count))
	match_rounds = int(cfg.get_value("gameplay", "match_rounds", match_rounds))
	map_index = int(cfg.get_value("gameplay", "map_index", map_index))
	shadows = bool(cfg.get_value("graphics", "shadows", shadows))
	shadow_quality = int(cfg.get_value("graphics", "shadow_quality", shadow_quality))
	msaa = int(cfg.get_value("graphics", "msaa", msaa))
	resolution_scale = float(cfg.get_value("graphics", "resolution_scale", resolution_scale))
	fog_enabled = bool(cfg.get_value("graphics", "fog_enabled", fog_enabled))
	brightness = float(cfg.get_value("graphics", "brightness", brightness))
	fullscreen = bool(cfg.get_value("window", "fullscreen", fullscreen))
	vsync = bool(cfg.get_value("window", "vsync", vsync))
	show_fps = bool(cfg.get_value("ui", "show_fps", show_fps))
	show_radar = bool(cfg.get_value("ui", "show_radar", show_radar))
	master_volume = float(cfg.get_value("audio", "master_volume", master_volume))
