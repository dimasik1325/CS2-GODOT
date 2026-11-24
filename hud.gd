class_name HUDController
extends CanvasLayer
## HUD, построенный полностью программно: здоровье с полосой, патроны,
## название оружия, прицел из ColorRect, хитмаркер, килл-фид, виньетка урона
## и экран конца раунда с рестартом по Enter.

var root: Control
var hp_fill: ColorRect
var hp_label: Label
var weapon_label: Label
var ammo_label: Label
var kd_label: Label
var enemies_label: Label
var reload_label: Label
var vignette: ColorRect
var feed_box: VBoxContainer
var end_overlay: Control
var end_title: Label
var end_sub: Label
var crosshair_parts: Array[ColorRect] = []
var hitmarker_root: Control
var _hitmarker_tween: Tween
var _vignette_tween: Tween
var _prev_health := 100
var _feed_style: StyleBoxFlat


func _ready() -> void:
	root = Control.new()
	root.name = "HUDRoot"
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	_build_vignette()
	_build_crosshair()
	_build_hitmarker()
	_build_status_labels()
	_build_feed()
	_build_reload_label()
	_build_end_overlay()
	_make_unclickable(root)


# ---------------------------------------------------------------------------
# Построение интерфейса.
# ---------------------------------------------------------------------------

func _build_vignette() -> void:
	vignette = ColorRect.new()
	vignette.color = Color(0.75, 0.05, 0.05, 0.0)
	vignette.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	vignette.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(vignette)


func _build_crosshair() -> void:
	# 0 — верх, 1 — низ, 2 — лево, 3 — право, 4 — центральная точка.
	for i in 5:
		var rect := ColorRect.new()
		rect.color = Color(0.15, 1.0, 0.4, 0.85)
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		rect.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
		root.add_child(rect)
		crosshair_parts.append(rect)
	_layout_crosshair()


func _layout_crosshair() -> void:
	var thickness := 2.0
	var length := 7.0
	var gap := 5.0
	crosshair_parts[0].offset_left = -thickness * 0.5
	crosshair_parts[0].offset_right = thickness * 0.5
	crosshair_parts[0].offset_top = -gap - length
	crosshair_parts[0].offset_bottom = -gap
	crosshair_parts[1].offset_left = -thickness * 0.5
	crosshair_parts[1].offset_right = thickness * 0.5
	crosshair_parts[1].offset_top = gap
	crosshair_parts[1].offset_bottom = gap + length
	crosshair_parts[2].offset_left = -gap - length
	crosshair_parts[2].offset_right = -gap
	crosshair_parts[2].offset_top = -thickness * 0.5
	crosshair_parts[2].offset_bottom = thickness * 0.5
	crosshair_parts[3].offset_left = gap
	crosshair_parts[3].offset_right = gap + length
	crosshair_parts[3].offset_top = -thickness * 0.5
	crosshair_parts[3].offset_bottom = thickness * 0.5
	crosshair_parts[4].offset_left = -1.0
	crosshair_parts[4].offset_right = 1.0
	crosshair_parts[4].offset_top = -1.0
	crosshair_parts[4].offset_bottom = 1.0


func _build_hitmarker() -> void:
	hitmarker_root = Control.new()
	hitmarker_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hitmarker_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hitmarker_root.modulate.a = 0.0
	root.add_child(hitmarker_root)
	for i in 2:
		var rect := ColorRect.new()
		rect.color = Color(1.0, 1.0, 1.0, 0.95)
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		rect.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
		rect.offset_left = -9.0
		rect.offset_right = 9.0
		rect.offset_top = -1.5
		rect.offset_bottom = 1.5
		rect.pivot_offset = Vector2(9.0, 1.5)
		rect.rotation = PI * 0.25 if i == 0 else -PI * 0.25
		hitmarker_root.add_child(rect)


func _build_status_labels() -> void:
	# Полоса здоровья слева внизу.
	var hp_background := ColorRect.new()
	hp_background.color = Color(0.05, 0.07, 0.05, 0.6)
	hp_background.anchor_left = 0.0
	hp_background.anchor_top = 1.0
	hp_background.anchor_right = 0.0
	hp_background.anchor_bottom = 1.0
	hp_background.offset_left = 24.0
	hp_background.offset_top = -64.0
	hp_background.offset_right = 264.0
	hp_background.offset_bottom = -46.0
	hp_background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(hp_background)

	hp_fill = ColorRect.new()
	hp_fill.color = Color(0.35, 0.8, 0.35, 1.0)
	hp_fill.anchor_left = 0.0
	hp_fill.anchor_top = 0.0
	hp_fill.anchor_right = 0.0
	hp_fill.anchor_bottom = 0.0
	hp_fill.offset_left = 2.0
	hp_fill.offset_top = 2.0
	hp_fill.offset_right = 238.0
	hp_fill.offset_bottom = -2.0
	hp_fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hp_background.add_child(hp_fill)

	hp_label = _make_label("100", 30, Color(1.0, 1.0, 1.0))
	hp_label.anchor_left = 0.0
	hp_label.anchor_top = 1.0
	hp_label.anchor_right = 0.0
	hp_label.anchor_bottom = 1.0
	hp_label.offset_left = 274.0
	hp_label.offset_top = -68.0
	hp_label.offset_right = 380.0
	hp_label.offset_bottom = -34.0
	root.add_child(hp_label)

	# Оружие и патроны справа внизу.
	weapon_label = _make_label("AK-47", 20, Color(0.85, 0.85, 0.85))
	weapon_label.anchor_left = 1.0
	weapon_label.anchor_top = 1.0
	weapon_label.anchor_right = 1.0
	weapon_label.anchor_bottom = 1.0
	weapon_label.offset_left = -300.0
	weapon_label.offset_top = -96.0
	weapon_label.offset_right = -24.0
	weapon_label.offset_bottom = -66.0
	weapon_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	root.add_child(weapon_label)

	ammo_label = _make_label("30 / 90", 34, Color(1.0, 1.0, 1.0))
	ammo_label.anchor_left = 1.0
	ammo_label.anchor_top = 1.0
	ammo_label.anchor_right = 1.0
	ammo_label.anchor_bottom = 1.0
	ammo_label.offset_left = -300.0
	ammo_label.offset_top = -64.0
	ammo_label.offset_right = -24.0
	ammo_label.offset_bottom = -24.0
	ammo_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	root.add_child(ammo_label)

	# Счёт и враги сверху слева.
	kd_label = _make_label("Kills: 0    Deaths: 0", 20, Color(1.0, 1.0, 1.0))
	kd_label.offset_left = 24.0
	kd_label.offset_top = 14.0
	kd_label.offset_right = 420.0
	kd_label.offset_bottom = 44.0
	root.add_child(kd_label)

	enemies_label = _make_label("Enemies left: 0", 20, Color(1.0, 0.75, 0.35))
	enemies_label.offset_left = 24.0
	enemies_label.offset_top = 44.0
	enemies_label.offset_right = 420.0
	enemies_label.offset_bottom = 74.0
	root.add_child(enemies_label)


func _build_reload_label() -> void:
	reload_label = _make_label("RELOADING...", 22, Color(1.0, 0.72, 0.2))
	reload_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	reload_label.offset_left = -140.0
	reload_label.offset_right = 140.0
	reload_label.offset_top = 56.0
	reload_label.offset_bottom = 88.0
	reload_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	reload_label.visible = false
	root.add_child(reload_label)


func _build_feed() -> void:
	_feed_style = StyleBoxFlat.new()
	_feed_style.bg_color = Color(0.0, 0.0, 0.0, 0.45)
	_feed_style.content_margin_left = 8.0
	_feed_style.content_margin_right = 8.0
	_feed_style.content_margin_top = 3.0
	_feed_style.content_margin_bottom = 3.0

	feed_box = VBoxContainer.new()
	feed_box.anchor_left = 1.0
	feed_box.anchor_top = 0.0
	feed_box.anchor_right = 1.0
	feed_box.anchor_bottom = 0.0
	feed_box.offset_left = -380.0
	feed_box.offset_top = 16.0
	feed_box.offset_right = -20.0
	feed_box.offset_bottom = 280.0
	feed_box.add_theme_constant_override("separation", 4)
	feed_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(feed_box)


func _build_end_overlay() -> void:
	end_overlay = Control.new()
	end_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	end_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	end_overlay.visible = false
	root.add_child(end_overlay)

	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.02, 0.04, 0.62)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	end_overlay.add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	end_overlay.add_child(center)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	center.add_child(box)

	end_title = _make_label("VICTORY", 58, Color(0.35, 0.9, 0.45))
	end_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(end_title)

	end_sub = _make_label("", 20, Color(0.9, 0.9, 0.9))
	end_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(end_sub)

	var hint := _make_label("Press ENTER to start next round", 18, Color(0.75, 0.75, 0.75))
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(hint)


func _make_label(text: String, size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	label.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.85))
	label.add_theme_constant_override("outline_size", 4)
	return label


func _make_unclickable(control: Control) -> void:
	# HUD не должен перехватывать мышь (иначе клики не доходят до игры).
	control.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for child in control.get_children():
		var child_control := child as Control
		if child_control != null:
			_make_unclickable(child_control)


# ---------------------------------------------------------------------------
# Привязка к игроку и оружию.
# ---------------------------------------------------------------------------

func bind_player(player: PlayerController, weapon_manager: WeaponManager) -> void:
	player.health_changed.connect(update_health)
	player.died.connect(_on_player_died)
	weapon_manager.ammo_changed.connect(update_ammo)
	weapon_manager.weapon_switched.connect(update_weapon)
	weapon_manager.reload_started.connect(_on_reload_started)
	weapon_manager.reload_finished.connect(_on_reload_finished)
	weapon_manager.target_hit.connect(show_hitmarker)


# ---------------------------------------------------------------------------
# Обновление состояния.
# ---------------------------------------------------------------------------

func update_health(current: int, max_health: int) -> void:
	hp_label.text = str(current)
	if current < _prev_health:
		flash_damage(0.42)
	_prev_health = current
	var ratio := clampf(float(current) / float(max_health), 0.0, 1.0)
	hp_fill.offset_right = 2.0 + 236.0 * ratio
	if ratio > 0.6:
		hp_fill.color = Color(0.35, 0.8, 0.35)
	elif ratio > 0.3:
		hp_fill.color = Color(0.92, 0.72, 0.2)
	else:
		hp_fill.color = Color(0.85, 0.2, 0.15)


func update_ammo(mag: int, reserve: int) -> void:
	if mag < 0:
		# Нож — без патронов.
		ammo_label.text = "--"
		ammo_label.add_theme_color_override("font_color", Color(0.9, 0.9, 0.9))
		return
	ammo_label.text = "%d / %d" % [mag, reserve]
	if mag == 0:
		ammo_label.add_theme_color_override("font_color", Color(1.0, 0.35, 0.3))
	else:
		ammo_label.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0))


func update_weapon(weapon_name: String) -> void:
	weapon_label.text = weapon_name


func update_kd(kills: int, deaths: int) -> void:
	kd_label.text = "Kills: %d    Deaths: %d" % [kills, deaths]


func update_enemies(count: int) -> void:
	if count > 0:
		enemies_label.text = "Enemies left: %d" % count
		enemies_label.add_theme_color_override("font_color", Color(1.0, 0.75, 0.35))
	else:
		enemies_label.text = "Area clear!"
		enemies_label.add_theme_color_override("font_color", Color(0.4, 0.95, 0.5))


func show_hitmarker(headshot: bool = false, killed: bool = false) -> void:
	var color := Color(1.0, 0.3, 0.25)
	if not killed:
		color = Color(1.0, 0.9, 0.35) if headshot else Color(1.0, 1.0, 1.0, 0.95)
	for child in hitmarker_root.get_children():
		var rect := child as ColorRect
		if rect != null:
			rect.color = color
	hitmarker_root.modulate.a = 1.0
	if _hitmarker_tween != null and _hitmarker_tween.is_valid():
		_hitmarker_tween.kill()
	_hitmarker_tween = hitmarker_root.create_tween()
	_hitmarker_tween.tween_interval(0.05)
	_hitmarker_tween.tween_property(hitmarker_root, "modulate:a", 0.0, 0.16)


func flash_damage(strength: float) -> void:
	vignette.color = Color(0.75, 0.05, 0.05, strength)
	if _vignette_tween != null and _vignette_tween.is_valid():
		_vignette_tween.kill()
	_vignette_tween = vignette.create_tween()
	_vignette_tween.tween_property(vignette, "color:a", 0.0, 0.45)


func add_kill_feed(attacker: String, victim: String, weapon: String) -> void:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _feed_style)
	panel.size_flags_horizontal = Control.SIZE_SHRINK_END
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var label := Label.new()
	label.text = "%s  >>  %s   [%s]" % [attacker, victim, weapon]
	label.add_theme_font_size_override("font_size", 15)
	if attacker == "You":
		label.add_theme_color_override("font_color", Color(0.75, 0.95, 1.0))
	else:
		label.add_theme_color_override("font_color", Color(1.0, 0.5, 0.45))
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(label)
	feed_box.add_child(panel)
	feed_box.move_child(panel, 0)
	while feed_box.get_child_count() > 6:
		var oldest := feed_box.get_child(feed_box.get_child_count() - 1)
		oldest.queue_free()
	var tween := panel.create_tween()
	tween.tween_interval(3.6)
	tween.tween_property(panel, "modulate:a", 0.0, 0.6)
	tween.tween_callback(panel.queue_free)


func _on_reload_started(_duration: float) -> void:
	reload_label.visible = true


func _on_reload_finished() -> void:
	reload_label.visible = false


func _on_player_died() -> void:
	flash_damage(0.55)
	reload_label.visible = false
	for rect in crosshair_parts:
		rect.visible = false


func show_round_end(victory: bool, kills: int, deaths: int) -> void:
	if victory:
		end_title.text = "VICTORY"
		end_title.add_theme_color_override("font_color", Color(0.35, 0.9, 0.45))
		end_sub.text = "All terrorists eliminated.    Kills: %d   Deaths: %d" % [kills, deaths]
	else:
		end_title.text = "DEFEAT"
		end_title.add_theme_color_override("font_color", Color(0.95, 0.3, 0.25))
		end_sub.text = "You were eliminated.    Kills: %d   Deaths: %d" % [kills, deaths]
	end_overlay.visible = true


func hide_round_end() -> void:
	end_overlay.visible = false


func reset_for_round() -> void:
	hide_round_end()
	vignette.color = Color(0.75, 0.05, 0.05, 0.0)
	reload_label.visible = false
	for rect in crosshair_parts:
		rect.visible = true
	for child in feed_box.get_children():
		child.queue_free()
	_prev_health = 100
