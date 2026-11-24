class_name MenuController
extends CanvasLayer
## Главное меню: запуск игры, выбор карты, сложность, настройки графики/звука,
## открытие кейсов со скинами, инвентарь и пауза. Работает в режиме ALWAYS,
## поэтому продолжает работать и на паузе.

signal start_requested
signal map_changed(index: int)
signal resume_requested
signal quit_to_menu_requested
signal esc_pressed

const CARD_W := 130.0
const CARD_H := 120.0
const CARD_SEP := 8.0
const STRIP_LEN := 44
const RESULT_INDEX := 40

var root: Control
var main_panel: Control
var settings_panel: Control
var cases_panel: Control
var inventory_panel: Control
var pause_panel: Control
var stack: Array[Control] = []

var map_label: Label
var diff_label: Label
var bots_label: Label
var rounds_label: Label
var menu_money_label: Label
var menu_stats_label: Label

var case_money_label: Label
var case_open_button: Button
var strip_window: Control
var strip: Control
var result_popup: Control

var inventory_box: VBoxContainer

var _opening := false
var _btn_normal: StyleBoxFlat
var _btn_hover: StyleBoxFlat
var _btn_pressed: StyleBoxFlat


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	layer = 10
	_build_button_styles()
	root = Control.new()
	root.name = "MenuRoot"
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(root)
	_build_main_panel()
	_build_settings_panel()
	_build_cases_panel()
	_build_inventory_panel()
	_build_pause_panel()
	show_main()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		if _opening:
			return
		esc_pressed.emit()


# ---------------------------------------------------------------------------
# Помощники UI.
# ---------------------------------------------------------------------------

func _build_button_styles() -> void:
	_btn_normal = StyleBoxFlat.new()
	_btn_normal.bg_color = Color(0.14, 0.16, 0.14, 0.92)
	_btn_normal.border_color = Color(0.35, 0.75, 0.4, 0.8)
	_btn_normal.set_border_width_all(2)
	_btn_normal.set_corner_radius_all(6)
	_btn_normal.content_margin_left = 18.0
	_btn_normal.content_margin_right = 18.0
	_btn_normal.content_margin_top = 10.0
	_btn_normal.content_margin_bottom = 10.0
	_btn_hover = _btn_normal.duplicate()
	_btn_hover.bg_color = Color(0.2, 0.26, 0.2, 0.95)
	_btn_pressed = _btn_normal.duplicate()
	_btn_pressed.bg_color = Color(0.1, 0.2, 0.12, 0.95)


func _styled_button(text: String, font_size: int = 22) -> Button:
	var button := Button.new()
	button.text = text
	button.mouse_filter = Control.MOUSE_FILTER_STOP
	button.add_theme_font_size_override("font_size", font_size)
	button.add_theme_color_override("font_color", Color(0.92, 0.95, 0.92))
	button.add_theme_color_override("font_hover_color", Color(1.0, 1.0, 1.0))
	button.add_theme_stylebox_override("normal", _btn_normal)
	button.add_theme_stylebox_override("hover", _btn_hover)
	button.add_theme_stylebox_override("pressed", _btn_pressed)
	button.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	button.pressed.connect(func() -> void: SfxManager.instance.play("click", -6.0))
	return button


func _dim_background() -> ColorRect:
	var dim := ColorRect.new()
	dim.color = Color(0.01, 0.02, 0.01, 0.62)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	return dim


func _panel_with_dim() -> Array[Control]:
	var panel := Control.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.visible = false
	root.add_child(panel)
	var dim := _dim_background()
	panel.add_child(dim)
	return [panel, dim]


func _title(text: String, size: int = 44) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", Color(0.55, 0.95, 0.6))
	label.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.9))
	label.add_theme_constant_override("outline_size", 6)
	return label


func _selector_row(parent: Control, title: String, value_label: Label) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	parent.add_child(row)
	var name_label := Label.new()
	name_label.text = title
	name_label.add_theme_font_size_override("font_size", 18)
	name_label.add_theme_color_override("font_color", Color(0.8, 0.82, 0.8))
	name_label.custom_minimum_size = Vector2(150.0, 0.0)
	row.add_child(name_label)
	var left := _styled_button("<", 18)
	left.custom_minimum_size = Vector2(40.0, 0.0)
	row.add_child(left)
	value_label.add_theme_font_size_override("font_size", 18)
	value_label.custom_minimum_size = Vector2(170.0, 0.0)
	value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	row.add_child(value_label)
	var right := _styled_button(">", 18)
	right.custom_minimum_size = Vector2(40.0, 0.0)
	row.add_child(right)
	return row


func _add_slider_row(parent: Control, title: String, min_value: float, max_value: float, step: float, initial: float, on_change: Callable) -> HSlider:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	parent.add_child(row)
	var name_label := Label.new()
	name_label.text = title
	name_label.add_theme_font_size_override("font_size", 18)
	name_label.add_theme_color_override("font_color", Color(0.8, 0.82, 0.8))
	name_label.custom_minimum_size = Vector2(220.0, 0.0)
	row.add_child(name_label)
	var slider := HSlider.new()
	slider.min_value = min_value
	slider.max_value = max_value
	slider.step = step
	slider.value = initial
	slider.custom_minimum_size = Vector2(320.0, 24.0)
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.mouse_filter = Control.MOUSE_FILTER_STOP
	row.add_child(slider)
	var value_label := Label.new()
	value_label.add_theme_font_size_override("font_size", 16)
	value_label.custom_minimum_size = Vector2(80.0, 0.0)
	row.add_child(value_label)
	slider.value_changed.connect(func(value: float) -> void:
		on_change.call(value)
		value_label.text = "%.2f" % value if step < 1.0 else str(int(value))
		SfxManager.instance.play("tick", -14.0)
	)
	value_label.text = "%.2f" % initial if step < 1.0 else str(int(initial))
	return slider


func _add_check_row(parent: Control, title: String, initial: bool, on_change: Callable) -> CheckButton:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	parent.add_child(row)
	var name_label := Label.new()
	name_label.text = title
	name_label.add_theme_font_size_override("font_size", 18)
	name_label.add_theme_color_override("font_color", Color(0.8, 0.82, 0.8))
	name_label.custom_minimum_size = Vector2(220.0, 0.0)
	row.add_child(name_label)
	var check := CheckButton.new()
	check.button_pressed = initial
	check.mouse_filter = Control.MOUSE_FILTER_STOP
	row.add_child(check)
	check.toggled.connect(func(value: bool) -> void:
		on_change.call(value)
		SfxManager.instance.play("click", -8.0)
	)
	return check


func _push_panel(panel: Control) -> void:
	for p in stack:
		p.visible = false
	stack.append(panel)
	panel.visible = true


func _pop_panel() -> void:
	if stack.size() <= 1:
		return
	var top: Control = stack.pop_back()
	top.visible = false
	stack[stack.size() - 1].visible = true


func show_main() -> void:
	for p in stack:
		p.visible = false
	stack.clear()
	main_panel.visible = true
	stack.append(main_panel)
	_refresh_main()


func go_back() -> void:
	if stack.size() > 1:
		_pop_panel()
	else:
		show_main()


# ---------------------------------------------------------------------------
# Главная панель.
# ---------------------------------------------------------------------------

func _build_main_panel() -> void:
	var controls := _panel_with_dim()
	main_panel = controls[0]
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 90)
	margin.add_theme_constant_override("margin_top", 60)
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main_panel.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	column.custom_minimum_size = Vector2(380.0, 0.0)
	column.mouse_filter = Control.MOUSE_FILTER_PASS
	margin.add_child(column)

	var title := _title("CS2-GODOT", 54)
	column.add_child(title)
	var subtitle := Label.new()
	subtitle.text = "Procedural FPS  —  Godot 4 Edition"
	subtitle.add_theme_font_size_override("font_size", 16)
	subtitle.add_theme_color_override("font_color", Color(0.6, 0.85, 0.65))
	column.add_child(subtitle)
	column.add_child(_spacer(16))

	var play := _styled_button("►  PLAY", 28)
	play.pressed.connect(func() -> void: start_requested.emit())
	column.add_child(play)
	column.add_child(_spacer(10))

	# Выбор карты.
	map_label = Label.new()
	var map_row := _selector_row(column, "Map", map_label)
	var map_left := map_row.get_child(1) as Button
	var map_right := map_row.get_child(3) as Button
	map_left.pressed.connect(func() -> void: _cycle_map(-1))
	map_right.pressed.connect(func() -> void: _cycle_map(1))
	# Сложность.
	diff_label = Label.new()
	var diff_row := _selector_row(column, "Difficulty", diff_label)
	var diff_left := diff_row.get_child(1) as Button
	var diff_right := diff_row.get_child(3) as Button
	diff_left.pressed.connect(func() -> void: _cycle_difficulty(-1))
	diff_right.pressed.connect(func() -> void: _cycle_difficulty(1))
	# Количество ботов.
	bots_label = Label.new()
	var bots_row := _selector_row(column, "Bots", bots_label)
	var bots_left := bots_row.get_child(1) as Button
	var bots_right := bots_row.get_child(3) as Button
	bots_left.pressed.connect(func() -> void: _cycle_bots(-1))
	bots_right.pressed.connect(func() -> void: _cycle_bots(1))
	# Раундов до победы.
	rounds_label = Label.new()
	var rounds_row := _selector_row(column, "Rounds to win", rounds_label)
	var rounds_left := rounds_row.get_child(1) as Button
	var rounds_right := rounds_row.get_child(3) as Button
	rounds_left.pressed.connect(func() -> void: _cycle_rounds(-1))
	rounds_right.pressed.connect(func() -> void: _cycle_rounds(1))

	column.add_child(_spacer(10))
	var settings_btn := _styled_button("⚙  SETTINGS")
	settings_btn.pressed.connect(open_settings)
	column.add_child(settings_btn)
	var cases_btn := _styled_button("📦  CASES  (%d $)" % Skins.CASE_PRICE)
	cases_btn.pressed.connect(open_cases)
	column.add_child(cases_btn)
	var inventory_btn := _styled_button("🎒  INVENTORY")
	inventory_btn.pressed.connect(open_inventory)
	column.add_child(inventory_btn)
	var quit_btn := _styled_button("✕  QUIT GAME")
	quit_btn.pressed.connect(func() -> void: get_tree().quit())
	column.add_child(quit_btn)

	# Статистика и баланс справа внизу.
	menu_money_label = Label.new()
	menu_money_label.anchor_left = 1.0
	menu_money_label.anchor_top = 1.0
	menu_money_label.anchor_right = 1.0
	menu_money_label.anchor_bottom = 1.0
	menu_money_label.offset_left = -420.0
	menu_money_label.offset_top = -110.0
	menu_money_label.offset_right = -40.0
	menu_money_label.offset_bottom = -76.0
	menu_money_label.add_theme_font_size_override("font_size", 26)
	menu_money_label.add_theme_color_override("font_color", Color(0.45, 0.9, 0.45))
	menu_money_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	menu_money_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main_panel.add_child(menu_money_label)
	menu_stats_label = Label.new()
	menu_stats_label.anchor_left = 1.0
	menu_stats_label.anchor_top = 1.0
	menu_stats_label.anchor_right = 1.0
	menu_stats_label.anchor_bottom = 1.0
	menu_stats_label.offset_left = -420.0
	menu_stats_label.offset_top = -72.0
	menu_stats_label.offset_right = -40.0
	menu_stats_label.offset_bottom = -40.0
	menu_stats_label.add_theme_font_size_override("font_size", 16)
	menu_stats_label.add_theme_color_override("font_color", Color(0.75, 0.78, 0.75))
	menu_stats_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	menu_stats_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main_panel.add_child(menu_stats_label)


func _spacer(height: float) -> Control:
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0.0, height)
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return spacer


func _refresh_main() -> void:
	if SettingsManager.instance == null or SaveManager.instance == null:
		return
	var settings := SettingsManager.instance
	map_label.text = MapBuilder.THEME_NAMES[clampi(settings.map_index, 0, MapBuilder.THEME_NAMES.size() - 1)]
	diff_label.text = settings.get_difficulty_name()
	bots_label.text = str(settings.bots_count)
	rounds_label.text = "first to %d" % settings.match_rounds
	menu_money_label.text = "$ %d" % SaveManager.instance.money
	menu_stats_label.text = "Kills: %d    Deaths: %d    Cases: %d    Match wins: %d" % [
		SaveManager.instance.total_kills, SaveManager.instance.total_deaths,
		SaveManager.instance.cases_opened, SaveManager.instance.match_wins,
	]


func _cycle_map(delta: int) -> void:
	var settings := SettingsManager.instance
	settings.map_index = wrapi(settings.map_index + delta, 0, MapBuilder.THEMES.size())
	settings.save_settings()
	_refresh_main()
	map_changed.emit(settings.map_index)


func _cycle_difficulty(delta: int) -> void:
	var settings := SettingsManager.instance
	settings.difficulty = wrapi(settings.difficulty + delta, 0, SettingsManager.DIFFICULTY_NAMES.size())
	settings.save_settings()
	_refresh_main()


func _cycle_bots(delta: int) -> void:
	var settings := SettingsManager.instance
	settings.bots_count = clampi(settings.bots_count + delta, 3, 8)
	settings.save_settings()
	_refresh_main()


func _cycle_rounds(delta: int) -> void:
	var settings := SettingsManager.instance
	var index := SettingsManager.ROUNDS_VALUES.find(settings.match_rounds)
	if index < 0:
		index = 1
	index = wrapi(index + delta, 0, SettingsManager.ROUNDS_VALUES.size())
	settings.match_rounds = SettingsManager.ROUNDS_VALUES[index]
	settings.save_settings()
	_refresh_main()


# ---------------------------------------------------------------------------
# Настройки.
# ---------------------------------------------------------------------------

func open_settings() -> void:
	_push_panel(settings_panel)


func _build_settings_panel() -> void:
	var controls := _panel_with_dim()
	settings_panel = controls[0]
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 140)
	margin.add_theme_constant_override("margin_top", 50)
	margin.add_theme_constant_override("margin_right", 140)
	margin.add_theme_constant_override("margin_bottom", 40)
	margin.mouse_filter = Control.MOUSE_FILTER_PASS
	settings_panel.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	column.mouse_filter = Control.MOUSE_FILTER_PASS
	margin.add_child(column)

	column.add_child(_title("SETTINGS", 38))
	column.add_child(_spacer(6))

	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0.0, 430.0)
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.mouse_filter = Control.MOUSE_FILTER_PASS
	column.add_child(scroll)
	var grid := VBoxContainer.new()
	grid.add_theme_constant_override("separation", 8)
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.mouse_filter = Control.MOUSE_FILTER_PASS
	scroll.add_child(grid)

	# — Графика —
	var graphics_title := _title("Graphics", 22)
	graphics_title.add_theme_color_override("font_color", Color(0.7, 0.9, 0.75))
	grid.add_child(graphics_title)
	_add_check_row(grid, "Shadows", SettingsManager.instance.shadows, func(value: bool) -> void:
		SettingsManager.instance.shadows = value
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_slider_row(grid, "Shadow quality", 0, 2, 1, SettingsManager.instance.shadow_quality, func(value: float) -> void:
		SettingsManager.instance.shadow_quality = int(value)
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_slider_row(grid, "MSAA", 0, 3, 1, SettingsManager.MSAA_VALUES.find(SettingsManager.instance.msaa), func(value: float) -> void:
		var index := clampi(int(value), 0, SettingsManager.MSAA_VALUES.size() - 1)
		SettingsManager.instance.msaa = SettingsManager.MSAA_VALUES[index]
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_slider_row(grid, "Resolution scale", 0.5, 1.0, 0.05, SettingsManager.instance.resolution_scale, func(value: float) -> void:
		SettingsManager.instance.resolution_scale = value
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_slider_row(grid, "Field of view", 70, 100, 1, SettingsManager.instance.base_fov, func(value: float) -> void:
		SettingsManager.instance.base_fov = value
		SettingsManager.instance.save_settings()
	)
	_add_slider_row(grid, "Brightness", 0.7, 1.4, 0.05, SettingsManager.instance.brightness, func(value: float) -> void:
		SettingsManager.instance.brightness = value
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_check_row(grid, "Fog", SettingsManager.instance.fog_enabled, func(value: bool) -> void:
		SettingsManager.instance.fog_enabled = value
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_check_row(grid, "Fullscreen", SettingsManager.instance.fullscreen, func(value: bool) -> void:
		SettingsManager.instance.fullscreen = value
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)
	_add_check_row(grid, "V-Sync", SettingsManager.instance.vsync, func(value: bool) -> void:
		SettingsManager.instance.vsync = value
		SettingsManager.instance.apply_graphics()
		SettingsManager.instance.save_settings()
	)

	# — Звук и интерфейс —
	var other_title := _title("Audio & UI", 22)
	other_title.add_theme_color_override("font_color", Color(0.7, 0.9, 0.75))
	grid.add_child(other_title)
	_add_slider_row(grid, "Master volume", 0.0, 1.0, 0.05, SettingsManager.instance.master_volume, func(value: float) -> void:
		SettingsManager.instance.master_volume = value
		SettingsManager.instance.apply_audio()
		SettingsManager.instance.save_settings()
	)
	_add_check_row(grid, "Show FPS", SettingsManager.instance.show_fps, func(value: bool) -> void:
		SettingsManager.instance.show_fps = value
		SettingsManager.instance.save_settings()
	)
	_add_check_row(grid, "Show radar", SettingsManager.instance.show_radar, func(value: bool) -> void:
		SettingsManager.instance.show_radar = value
		SettingsManager.instance.save_settings()
	)

	# — Управление —
	var controls_title := _title("Controls (mouse sensitivity)", 22)
	controls_title.add_theme_color_override("font_color", Color(0.7, 0.9, 0.75))
	grid.add_child(controls_title)
	_add_slider_row(grid, "Mouse sensitivity", 0.3, 3.0, 0.05, SettingsManager.instance.mouse_sensitivity, func(value: float) -> void:
		SettingsManager.instance.mouse_sensitivity = value
		SettingsManager.instance.save_settings()
	)

	var back := _styled_button("◄  BACK")
	back.pressed.connect(go_back)
	column.add_child(back)


# ---------------------------------------------------------------------------
# Кейсы.
# ---------------------------------------------------------------------------

func open_cases() -> void:
	_push_panel(cases_panel)
	_refresh_case_money()


func _refresh_case_money() -> void:
	if SaveManager.instance != null:
		case_money_label.text = "$ %d" % SaveManager.instance.money
		case_open_button.disabled = SaveManager.instance.money < Skins.CASE_PRICE or _opening


func _build_cases_panel() -> void:
	var controls := _panel_with_dim()
	cases_panel = controls[0]
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 120)
	margin.add_theme_constant_override("margin_top", 40)
	margin.add_theme_constant_override("margin_right", 120)
	margin.add_theme_constant_override("margin_bottom", 30)
	margin.mouse_filter = Control.MOUSE_FILTER_PASS
	cases_panel.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	column.mouse_filter = Control.MOUSE_FILTER_PASS
	margin.add_child(column)

	var header := HBoxContainer.new()
	header.mouse_filter = Control.MOUSE_FILTER_PASS
	column.add_child(header)
	var cases_title := _title("CASES", 38)
	header.add_child(cases_title)
	case_money_label = Label.new()
	case_money_label.add_theme_font_size_override("font_size", 26)
	case_money_label.add_theme_color_override("font_color", Color(0.45, 0.9, 0.45))
	case_money_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	case_money_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	header.add_child(case_money_label)

	# Изображение кейса из примитивов-прямоугольников.
	var case_visual := PanelContainer.new()
	case_visual.custom_minimum_size = Vector2(220.0, 120.0)
	case_visual.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	case_visual.mouse_filter = Control.MOUSE_FILTER_PASS
	var case_style := StyleBoxFlat.new()
	case_style.bg_color = Color(0.25, 0.3, 0.22)
	case_style.border_color = Color(0.7, 0.6, 0.2)
	case_style.set_border_width_all(4)
	case_style.set_corner_radius_all(10)
	case_visual.add_theme_stylebox_override("panel", case_style)
	column.add_child(case_visual)
	var case_inner := VBoxContainer.new()
	case_inner.alignment = BoxContainer.ALIGNMENT_CENTER
	case_inner.mouse_filter = Control.MOUSE_FILTER_PASS
	case_visual.add_child(case_inner)
	var case_name := _title(Skins.CASE_NAME, 20)
	case_name.add_theme_color_override("font_color", Color(0.95, 0.85, 0.4))
	case_name.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	case_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	case_inner.add_child(case_name)
	var case_price := Label.new()
	case_price.text = "$ %d" % Skins.CASE_PRICE
	case_price.add_theme_font_size_override("font_size", 18)
	case_price.add_theme_color_override("font_color", Color(0.6, 0.9, 0.6))
	case_price.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	case_inner.add_child(case_price)

	# Окно ленты предметов.
	strip_window = Control.new()
	strip_window.custom_minimum_size = Vector2(0.0, 170.0)
	strip_window.size_flags_vertical = Control.SIZE_EXPAND_FILL
	strip_window.clip_contents = true
	strip_window.mouse_filter = Control.MOUSE_FILTER_PASS
	column.add_child(strip_window)
	strip = HBoxContainer.new()
	strip.add_theme_constant_override("separation", int(CARD_SEP))
	strip.mouse_filter = Control.MOUSE_FILTER_PASS
	strip_window.add_child(strip)
	var marker := ColorRect.new()
	marker.color = Color(1.0, 0.9, 0.3, 0.85)
	marker.anchor_left = 0.5
	marker.anchor_top = 0.0
	marker.anchor_right = 0.5
	marker.anchor_bottom = 0.0
	marker.offset_left = -2.0
	marker.offset_right = 2.0
	marker.offset_top = 0.0
	marker.offset_bottom = 170.0
	marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	strip_window.add_child(marker)

	var buttons_row := HBoxContainer.new()
	buttons_row.alignment = BoxContainer.ALIGNMENT_CENTER
	buttons_row.add_theme_constant_override("separation", 16)
	buttons_row.mouse_filter = Control.MOUSE_FILTER_PASS
	column.add_child(buttons_row)
	case_open_button = _styled_button("🔓  OPEN CASE  (-$ %d)" % Skins.CASE_PRICE, 24)
	case_open_button.pressed.connect(_open_case)
	buttons_row.add_child(case_open_button)
	var back := _styled_button("◄  BACK")
	back.pressed.connect(go_back)
	buttons_row.add_child(back)


func _skin_card(skin: Dictionary) -> PanelContainer:
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(CARD_W, CARD_H)
	card.mouse_filter = Control.MOUSE_FILTER_PASS
	var rarity := int(skin.get("rarity", -1))
	var rarity_color := Color(0.5, 0.5, 0.5)
	if rarity >= 0:
		rarity_color = Skins.RARITY_COLORS[clampi(rarity, 0, Skins.RARITY_COLORS.size() - 1)]
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.09, 0.1, 0.95)
	style.border_color = rarity_color
	style.set_border_width_all(2)
	style.set_corner_radius_all(6)
	card.add_theme_stylebox_override("panel", style)
	var inner := VBoxContainer.new()
	inner.alignment = BoxContainer.ALIGNMENT_CENTER
	inner.add_theme_constant_override("separation", 6)
	inner.mouse_filter = Control.MOUSE_FILTER_PASS
	card.add_child(inner)
	var swatch := ColorRect.new()
	swatch.custom_minimum_size = Vector2(60.0, 22.0)
	swatch.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	var body_color: Variant = skin.get("body", Color(0.4, 0.4, 0.4))
	swatch.color = body_color
	swatch.mouse_filter = Control.MOUSE_FILTER_IGNORE
	inner.add_child(swatch)
	var name_label := Label.new()
	name_label.text = String(skin.get("name", "?"))
	name_label.add_theme_font_size_override("font_size", 13)
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	name_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	inner.add_child(name_label)
	var weapon_label := Label.new()
	weapon_label.text = String(skin.get("weapon", ""))
	weapon_label.add_theme_font_size_override("font_size", 11)
	weapon_label.add_theme_color_override("font_color", Color(0.65, 0.68, 0.65))
	weapon_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	weapon_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	inner.add_child(weapon_label)
	var rarity_label := Label.new()
	if rarity >= 0:
		rarity_label.text = Skins.RARITY_NAMES[clampi(rarity, 0, Skins.RARITY_NAMES.size() - 1)]
		rarity_label.add_theme_color_override("font_color", rarity_color)
	else:
		rarity_label.text = "Default"
		rarity_label.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
	rarity_label.add_theme_font_size_override("font_size", 11)
	rarity_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	rarity_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	inner.add_child(rarity_label)
	return card


func _open_case() -> void:
	if _opening:
		return
	if SaveManager.instance == null:
		return
	if not SaveManager.instance.try_spend(Skins.CASE_PRICE):
		SfxManager.instance.play("dry", -4.0)
		return
	_opening = true
	SfxManager.instance.play("buy", -2.0)
	_refresh_case_money()
	# Очищаем ленту.
	for child in strip.get_children():
		child.queue_free()
	# Заполняем ленту: случайные карточки + выигрыш на фиксированной позиции.
	var result := Skins.case_roll()
	for i in STRIP_LEN:
		var card_skin := result if i == RESULT_INDEX else Skins.case_roll_visual()
		strip.add_child(_skin_card(card_skin))
	# Анимация прокрутки к выигрышу.
	await get_tree().process_frame
	var window_width := maxf(strip_window.size.x, 100.0)
	var center := window_width * 0.5
	var step_w := CARD_W + CARD_SEP
	var target_x := center - (float(RESULT_INDEX) * step_w + CARD_W * 0.5)
	strip.position = Vector2(center - CARD_W * 0.5, 10.0)
	var last_index := -1
	var tween := create_tween()
	tween.tween_method(func(t: float) -> void:
		var x := lerpf(center - CARD_W * 0.5, target_x, t)
		strip.position = Vector2(x, 10.0)
		var index := int((center - x - CARD_W * 0.5) / step_w)
		if index != last_index:
			last_index = index
			SfxManager.instance.play("tick", -10.0)
	, 0.0, 1.0, 3.6).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tween.tween_callback(func() -> void: _finish_case_opening(result))


func _finish_case_opening(result: Dictionary) -> void:
	_opening = false
	SaveManager.instance.own_skin(String(result["id"]))
	SaveManager.instance.add_case_opened()
	SaveManager.instance.equip_skin(String(result["weapon"]), String(result["id"]))
	SfxManager.instance.play("case_win", 0.0)
	_refresh_case_money()
	# Всплывающее окно результата.
	if result_popup != null and is_instance_valid(result_popup):
		result_popup.queue_free()
	result_popup = Control.new()
	result_popup.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	result_popup.mouse_filter = Control.MOUSE_FILTER_STOP
	cases_panel.add_child(result_popup)
	var dim := _dim_background()
	dim.color = Color(0.0, 0.0, 0.0, 0.5)
	result_popup.add_child(dim)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_PASS
	result_popup.add_child(center)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	box.mouse_filter = Control.MOUSE_FILTER_PASS
	center.add_child(box)
	var rarity := int(result.get("rarity", 0))
	var rarity_color := Skins.RARITY_COLORS[clampi(rarity, 0, Skins.RARITY_COLORS.size() - 1)]
	var card := _skin_card(result)
	card.custom_minimum_size = Vector2(260.0, 220.0)
	box.add_child(card)
	var got := Label.new()
	got.text = "You got:  %s  (%s)" % [String(result["name"]), Skins.RARITY_NAMES[clampi(rarity, 0, Skins.RARITY_NAMES.size() - 1)]]
	got.add_theme_font_size_override("font_size", 20)
	got.add_theme_color_override("font_color", rarity_color)
	got.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(got)
	var equipped := Label.new()
	equipped.text = "Auto-equipped on your %s" % String(result["weapon"])
	equipped.add_theme_font_size_override("font_size", 15)
	equipped.add_theme_color_override("font_color", Color(0.75, 0.8, 0.75))
	equipped.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(equipped)
	var close := _styled_button("NICE!")
	close.pressed.connect(func() -> void:
		result_popup.queue_free()
		result_popup = null
	)
	box.add_child(close)


# ---------------------------------------------------------------------------
# Инвентарь.
# ---------------------------------------------------------------------------

func open_inventory() -> void:
	_push_panel(inventory_panel)
	_rebuild_inventory()


func _build_inventory_panel() -> void:
	var controls := _panel_with_dim()
	inventory_panel = controls[0]
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 100)
	margin.add_theme_constant_override("margin_top", 40)
	margin.add_theme_constant_override("margin_right", 100)
	margin.add_theme_constant_override("margin_bottom", 30)
	margin.mouse_filter = Control.MOUSE_FILTER_PASS
	inventory_panel.add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	column.mouse_filter = Control.MOUSE_FILTER_PASS
	margin.add_child(column)
	column.add_child(_title("INVENTORY  (click a skin to equip)", 32))
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0.0, 440.0)
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.mouse_filter = Control.MOUSE_FILTER_PASS
	column.add_child(scroll)
	inventory_box = VBoxContainer.new()
	inventory_box.add_theme_constant_override("separation", 14)
	inventory_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inventory_box.mouse_filter = Control.MOUSE_FILTER_PASS
	scroll.add_child(inventory_box)
	var back := _styled_button("◄  BACK")
	back.pressed.connect(go_back)
	column.add_child(back)


func _rebuild_inventory() -> void:
	for child in inventory_box.get_children():
		child.queue_free()
	for weapon in ["AK-47", "Glock-18", "Knife"]:
		var section := VBoxContainer.new()
		section.add_theme_constant_override("separation", 6)
		section.mouse_filter = Control.MOUSE_FILTER_PASS
		inventory_box.add_child(section)
		var weapon_title := _title(weapon, 20)
		weapon_title.add_theme_color_override("font_color", Color(0.85, 0.9, 0.85))
		section.add_child(weapon_title)
		var flow := HFlowContainer.new()
		flow.add_theme_constant_override("separation", 8)
		flow.mouse_filter = Control.MOUSE_FILTER_PASS
		section.add_child(flow)
		var equipped_id := ""
		if SaveManager.instance != null:
			equipped_id = SaveManager.instance.get_equipped(weapon)
		# Карточка «Default».
		var default_card := _skin_card(Skins.get_default_skin(weapon))
		default_card.mouse_filter = Control.MOUSE_FILTER_STOP
		if equipped_id == "":
			default_card.modulate = Color(1.3, 1.3, 1.1)
		default_card.gui_input.connect(func(event: InputEvent) -> void:
			if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
				SaveManager.instance.equip_skin(weapon, "")
				SfxManager.instance.play("click", -4.0)
				_rebuild_inventory()
		)
		flow.add_child(default_card)
		for skin in Skins.skins_for_weapon(weapon):
			var skin_id := String(skin["id"])
			if SaveManager.instance == null or not SaveManager.instance.is_owned(skin_id):
				continue
			var card := _skin_card(skin)
			card.mouse_filter = Control.MOUSE_FILTER_STOP
			if equipped_id == skin_id:
				card.modulate = Color(1.3, 1.3, 1.1)
			var captured := skin_id
			card.gui_input.connect(func(event: InputEvent) -> void:
				if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
					SaveManager.instance.equip_skin(weapon, captured)
					SfxManager.instance.play("click", -4.0)
					_rebuild_inventory()
			)
			flow.add_child(card)


# ---------------------------------------------------------------------------
# Пауза.
# ---------------------------------------------------------------------------

func show_pause() -> void:
	for p in stack:
		p.visible = false
	stack.clear()
	pause_panel.visible = true
	stack.append(pause_panel)


func hide_all() -> void:
	for p in stack:
		p.visible = false
	stack.clear()
	root.visible = false


func make_root_visible() -> void:
	root.visible = true


func _build_pause_panel() -> void:
	var controls := _panel_with_dim()
	pause_panel = controls[0]
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_PASS
	pause_panel.add_child(center)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	column.custom_minimum_size = Vector2(320.0, 0.0)
	column.mouse_filter = Control.MOUSE_FILTER_PASS
	center.add_child(column)
	column.add_child(_title("PAUSED", 40))
	var resume := _styled_button("►  RESUME", 24)
	resume.pressed.connect(func() -> void: resume_requested.emit())
	column.add_child(resume)
	var settings_btn := _styled_button("⚙  SETTINGS", 24)
	settings_btn.pressed.connect(open_settings)
	column.add_child(settings_btn)
	var quit_menu := _styled_button("▤  QUIT TO MAIN MENU", 24)
	quit_menu.pressed.connect(func() -> void: quit_to_menu_requested.emit())
	column.add_child(quit_menu)
