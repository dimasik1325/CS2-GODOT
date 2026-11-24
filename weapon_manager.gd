class_name WeaponManager
extends Node3D
## Управление оружием игрока: три слота (AK-47 — авто, Glock-18 — полуавто,
## нож — ближний бой), стрельба хитсканом через камеру, разброс, отдача,
## перезарядка, трассеры и вспышки. Все модели собраны из примитивов.

signal ammo_changed(mag: int, reserve: int)
signal weapon_switched(weapon_name: String)
signal reload_started(duration: float)
signal reload_finished()
signal target_hit(headshot: bool)
signal recoil_requested(pitch_deg: float, yaw_deg: float)

const BASE_HOLDER_POS := Vector3(0.26, -0.23, -0.45)
const BASE_HOLDER_ROT := Vector3(0.0, -3.0, 0.0)
const KNIFE_RANGE := 2.3
const BOTS_HEARING_RADIUS := 26.0
const HEAD_HEIGHT := 1.45

var camera: Camera3D
var exclude_body_rid: RID = RID()
var player_velocity := Vector3.ZERO
var player_crouching := false
var player_airborne := false
var active := true

var weapons: Array[Dictionary] = []
var holders: Array[Node3D] = []
var holders_base: Array[Vector3] = []
var muzzles: Array[Node3D] = []
var current_index := 0

var fire_cooldown := 0.0
var reload_timer := 0.0
var reloading := false

var _semi_lock := false
var _bloom := 0.0
var _recoil_tween: Tween
var _reload_tween: Tween
var _raise_tween: Tween
var _death_tween: Tween

var _mat_metal: StandardMaterial3D
var _mat_metal_dark: StandardMaterial3D
var _mat_wood: StandardMaterial3D
var _mat_polymer: StandardMaterial3D
var _mat_steel: StandardMaterial3D
var _mat_grip: StandardMaterial3D


func _ready() -> void:
	_build_materials()
	_define_weapons()
	_build_models()
	_apply_selection(0, false)
	weapon_switched.emit(String(weapons[0]["name"]))
	ammo_changed.emit(int(weapons[0]["mag"]), int(weapons[0]["reserve"]))


func _unhandled_input(event: InputEvent) -> void:
	if not active:
		return
	if event.is_action_pressed("weapon_1"):
		_select_weapon(0)
	elif event.is_action_pressed("weapon_2"):
		_select_weapon(1)
	elif event.is_action_pressed("weapon_3"):
		_select_weapon(2)
	elif event.is_action_pressed("reload"):
		_start_reload()


func _physics_process(delta: float) -> void:
	_bloom = maxf(0.0, _bloom - delta * 0.015)
	if reload_timer > 0.0:
		reload_timer -= delta
		if reload_timer <= 0.0:
			_finish_reload()
	fire_cooldown = maxf(0.0, fire_cooldown - delta)
	if not active or reload_timer > 0.0:
		return
	var weapon := weapons[current_index]
	var fire_pressed := Input.is_action_pressed("fire") and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	if fire_pressed and fire_cooldown <= 0.0:
		if bool(weapon["auto"]) or not _semi_lock:
			_try_fire()
			_semi_lock = true
	if not fire_pressed:
		_semi_lock = false


# ---------------------------------------------------------------------------
# Данные оружия.
# ---------------------------------------------------------------------------

func _define_weapons() -> void:
	weapons = [
		{
			"name": "AK-47",
			"damage": 33.0,
			"headshot_mult": 3.2,
			"interval": 0.1,
			"auto": true,
			"mag_size": 30,
			"reserve_max": 90,
			"reload_time": 2.4,
			"spread_base": 0.005,
			"spread_move": 0.045,
			"recoil_pitch": 0.55,
			"recoil_yaw": 0.2,
			"range": 250.0,
			"melee": false,
			"mag": 30,
			"reserve": 90,
		},
		{
			"name": "Glock-18",
			"damage": 22.0,
			"headshot_mult": 2.5,
			"interval": 0.13,
			"auto": false,
			"mag_size": 20,
			"reserve_max": 120,
			"reload_time": 2.0,
			"spread_base": 0.008,
			"spread_move": 0.04,
			"recoil_pitch": 0.35,
			"recoil_yaw": 0.15,
			"range": 150.0,
			"melee": false,
			"mag": 20,
			"reserve": 120,
		},
		{
			"name": "Knife",
			"damage": 55.0,
			"headshot_mult": 1.5,
			"interval": 0.5,
			"auto": false,
			"mag_size": -1,
			"reserve_max": -1,
			"reload_time": 0.0,
			"spread_base": 0.0,
			"spread_move": 0.0,
			"recoil_pitch": 0.0,
			"recoil_yaw": 0.0,
			"range": KNIFE_RANGE,
			"melee": true,
			"mag": -1,
			"reserve": -1,
		},
	]


# ---------------------------------------------------------------------------
# Модели оружия из примитивов.
# ---------------------------------------------------------------------------

func _build_models() -> void:
	var ak := _build_ak_model()
	add_child(ak)
	holders.append(ak)
	holders_base.append(BASE_HOLDER_POS)
	muzzles.append(ak.get_node("Muzzle") as Node3D)

	var glock := _build_glock_model()
	add_child(glock)
	holders.append(glock)
	holders_base.append(Vector3(0.22, -0.21, -0.38))
	muzzles.append(glock.get_node("Muzzle") as Node3D)

	var knife := _build_knife_model()
	add_child(knife)
	holders.append(knife)
	holders_base.append(Vector3(0.24, -0.22, -0.35))
	muzzles.append(knife.get_node("Muzzle") as Node3D)


func _build_ak_model() -> Node3D:
	var holder := Node3D.new()
	holder.name = "AK47"
	holder.position = BASE_HOLDER_POS
	holder.rotation_degrees = BASE_HOLDER_ROT
	# Ствольная коробка и крышка.
	_add_box_part(holder, Vector3(0.06, 0.085, 0.42), _mat_metal_dark, Vector3(0.0, 0.0, -0.05))
	_add_box_part(holder, Vector3(0.055, 0.03, 0.4), _mat_metal, Vector3(0.0, 0.055, -0.05))
	# Ствол и газовая трубка.
	_add_cyl_part(holder, 0.016, 0.34, _mat_metal_dark, Vector3(0.0, 0.01, -0.42), Vector3(90.0, 0.0, 0.0))
	_add_cyl_part(holder, 0.011, 0.18, _mat_metal, Vector3(0.0, 0.05, -0.33), Vector3(90.0, 0.0, 0.0))
	# Мушка.
	_add_box_part(holder, Vector3(0.02, 0.05, 0.02), _mat_metal_dark, Vector3(0.0, 0.055, -0.55))
	# Деревянное цевье.
	_add_box_part(holder, Vector3(0.055, 0.06, 0.2), _mat_wood, Vector3(0.0, 0.005, -0.3))
	# Изогнутый магазин из двух сегментов.
	_add_box_part(holder, Vector3(0.045, 0.14, 0.075), _mat_metal_dark, Vector3(0.0, -0.1, -0.06), Vector3(-18.0, 0.0, 0.0))
	_add_box_part(holder, Vector3(0.045, 0.1, 0.07), _mat_metal_dark, Vector3(0.0, -0.2, -0.115), Vector3(-35.0, 0.0, 0.0))
	# Рукоять и приклад.
	_add_box_part(holder, Vector3(0.04, 0.09, 0.045), _mat_grip, Vector3(0.0, -0.08, 0.1), Vector3(22.0, 0.0, 0.0))
	_add_box_part(holder, Vector3(0.045, 0.075, 0.24), _mat_wood, Vector3(0.0, 0.01, 0.22))
	_add_muzzle_marker(holder, Vector3(0.0, 0.01, -0.6))
	return holder


func _build_glock_model() -> Node3D:
	var holder := Node3D.new()
	holder.name = "Glock"
	holder.position = Vector3(0.22, -0.21, -0.38)
	holder.rotation_degrees = BASE_HOLDER_ROT
	# Затвор и рамка.
	_add_box_part(holder, Vector3(0.045, 0.06, 0.2), _mat_metal_dark, Vector3(0.0, 0.02, -0.04))
	_add_box_part(holder, Vector3(0.04, 0.045, 0.16), _mat_polymer, Vector3(0.0, -0.02, -0.02))
	# Рукоять.
	_add_box_part(holder, Vector3(0.038, 0.12, 0.055), _mat_polymer, Vector3(0.0, -0.09, 0.05), Vector3(16.0, 0.0, 0.0))
	# Прицельные приспособления.
	_add_box_part(holder, Vector3(0.012, 0.014, 0.012), _mat_metal, Vector3(0.0, 0.058, -0.11))
	_add_box_part(holder, Vector3(0.012, 0.014, 0.012), _mat_metal, Vector3(0.0, 0.058, 0.04))
	_add_muzzle_marker(holder, Vector3(0.0, 0.02, -0.16))
	return holder


func _build_knife_model() -> Node3D:
	var holder := Node3D.new()
	holder.name = "Knife"
	holder.position = Vector3(0.24, -0.22, -0.35)
	holder.rotation_degrees = BASE_HOLDER_ROT
	# Клинок, гарда и рукоять.
	_add_box_part(holder, Vector3(0.018, 0.045, 0.26), _mat_steel, Vector3(0.0, 0.01, -0.17))
	_add_box_part(holder, Vector3(0.05, 0.018, 0.03), _mat_metal_dark, Vector3(0.0, 0.0, -0.03))
	_add_cyl_part(holder, 0.02, 0.11, _mat_grip, Vector3(0.0, 0.0, 0.04), Vector3(90.0, 0.0, 0.0))
	_add_muzzle_marker(holder, Vector3(0.0, 0.0, -0.3))
	return holder


func _add_box_part(parent: Node3D, size: Vector3, mat: StandardMaterial3D, pos: Vector3, rot_deg: Vector3 = Vector3.ZERO) -> void:
	var mesh_instance := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh_instance.mesh = box
	mesh_instance.material_override = mat
	mesh_instance.position = pos
	mesh_instance.rotation_degrees = rot_deg
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mesh_instance)


func _add_cyl_part(parent: Node3D, radius: float, height: float, mat: StandardMaterial3D, pos: Vector3, rot_deg: Vector3) -> void:
	var mesh_instance := MeshInstance3D.new()
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = radius
	cylinder.bottom_radius = radius
	cylinder.height = height
	mesh_instance.mesh = cylinder
	mesh_instance.material_override = mat
	mesh_instance.position = pos
	mesh_instance.rotation_degrees = rot_deg
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mesh_instance)


func _add_muzzle_marker(parent: Node3D, pos: Vector3) -> void:
	var muzzle := Node3D.new()
	muzzle.name = "Muzzle"
	muzzle.position = pos
	parent.add_child(muzzle)


func _build_materials() -> void:
	_mat_metal = _make_mat(Color(0.3, 0.3, 0.32), 0.4, 0.8)
	_mat_metal_dark = _make_mat(Color(0.16, 0.16, 0.17), 0.45, 0.75)
	_mat_wood = _make_mat(Color(0.42, 0.26, 0.14), 0.8, 0.0)
	_mat_polymer = _make_mat(Color(0.13, 0.13, 0.14), 0.7, 0.1)
	_mat_steel = _make_mat(Color(0.75, 0.77, 0.8), 0.25, 0.9)
	_mat_grip = _make_mat(Color(0.2, 0.12, 0.08), 0.9, 0.0)


func _make_mat(color: Color, roughness: float, metallic: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	m.metallic = metallic
	return m


# ---------------------------------------------------------------------------
# Стрельба.
# ---------------------------------------------------------------------------

func _try_fire() -> void:
	var weapon := weapons[current_index]
	fire_cooldown = float(weapon["interval"])
	if bool(weapon["melee"]):
		_melee_attack(weapon)
		return
	if int(weapon["mag"]) <= 0:
		# Пустой магазин — автоматическая перезарядка.
		_start_reload()
		return
	weapon["mag"] = int(weapon["mag"]) - 1
	_bloom = minf(_bloom + 0.0045, 0.02)
	ammo_changed.emit(int(weapon["mag"]), int(weapon["reserve"]))
	_hitscan(weapon)
	_apply_view_recoil(float(weapon["recoil_pitch"]), randf_range(-float(weapon["recoil_yaw"]), float(weapon["recoil_yaw"])))
	_notify_bots()


func _hitscan(weapon: Dictionary) -> void:
	if camera == null:
		return
	var origin := camera.global_position
	var spread := float(weapon["spread_base"]) + _bloom
	spread += float(weapon["spread_move"]) * clampf(player_velocity.length() / 5.2, 0.0, 1.4)
	if player_crouching:
		spread *= 0.55
	if player_airborne:
		spread += 0.07
	var dir := FX.spread_direction(-camera.global_transform.basis.z, spread)
	var to := origin + dir * float(weapon["range"])
	var exclude: Array[RID] = [exclude_body_rid]
	var query := PhysicsRayQueryParameters3D.create(origin, to, 1 | 4, exclude)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	var end := to
	if not hit.is_empty():
		end = hit["position"]
		var collider: Variant = hit.get("collider")
		var obj := collider as Object
		if obj != null and obj.has_method("take_damage"):
			var body := obj as Node3D
			var headshot := end.y >= body.global_position.y + HEAD_HEIGHT
			var mult := float(weapon["headshot_mult"]) if headshot else 1.0
			target_hit.emit(headshot)
			obj.call("take_damage", float(weapon["damage"]) * mult, String(weapon["name"]), headshot)
			FX.spawn_impact(get_tree().current_scene, end, FX.normal_from(hit, Vector3.UP), Color(0.55, 0.05, 0.05), 1.5 if headshot else 1.0)
		else:
			FX.spawn_impact(get_tree().current_scene, end, FX.normal_from(hit, Vector3.UP), Color(0.8, 0.72, 0.55))
	var muzzle := muzzles[current_index]
	if muzzle != null:
		FX.spawn_tracer(get_tree().current_scene, muzzle.global_position, end, Color(1.0, 0.9, 0.55))
		FX.spawn_muzzle_flash(get_tree().current_scene, muzzle.global_position, true)


func _melee_attack(weapon: Dictionary) -> void:
	var holder := holders[current_index]
	if _recoil_tween != null and _recoil_tween.is_valid():
		_recoil_tween.kill()
	holder.rotation_degrees = BASE_HOLDER_ROT
	_recoil_tween = create_tween()
	_recoil_tween.tween_property(holder, "rotation_degrees", BASE_HOLDER_ROT + Vector3(-38.0, 22.0, 12.0), 0.08).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_recoil_tween.tween_property(holder, "rotation_degrees", BASE_HOLDER_ROT, 0.3).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	if camera == null:
		return
	var origin := camera.global_position
	var dir := -camera.global_transform.basis.z
	var to := origin + dir * KNIFE_RANGE
	var exclude: Array[RID] = [exclude_body_rid]
	var query := PhysicsRayQueryParameters3D.create(origin, to, 1 | 4, exclude)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return
	var end: Vector3 = hit["position"]
	var collider: Variant = hit.get("collider")
	var obj := collider as Object
	if obj != null and obj.has_method("take_damage"):
		var body := obj as Node3D
		var headshot := end.y >= body.global_position.y + HEAD_HEIGHT
		var mult := float(weapon["headshot_mult"]) if headshot else 1.0
		target_hit.emit(headshot)
		obj.call("take_damage", float(weapon["damage"]) * mult, String(weapon["name"]), headshot)
		FX.spawn_impact(get_tree().current_scene, end, FX.normal_from(hit, Vector3.UP), Color(0.55, 0.05, 0.05), 1.5 if headshot else 1.0)
	else:
		FX.spawn_impact(get_tree().current_scene, end, FX.normal_from(hit, Vector3.UP), Color(0.85, 0.8, 0.7))


func _apply_view_recoil(pitch_deg: float, yaw_deg: float) -> void:
	var holder := holders[current_index]
	var base := holders_base[current_index]
	_kill_tween(_recoil_tween)
	holder.position = base
	_recoil_tween = create_tween()
	_recoil_tween.tween_property(holder, "position", base + Vector3(0.0, 0.015, 0.055), 0.045).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_recoil_tween.tween_property(holder, "position", base, 0.13).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	recoil_requested.emit(pitch_deg, yaw_deg)


func _notify_bots() -> void:
	# Выстрел слышен ботам в радиусе — они идут проверять источник звука.
	if camera == null:
		return
	var origin := camera.global_position
	for node in get_tree().get_nodes_in_group("bots"):
		var bot := node as Node3D
		if bot != null and bot.has_method("hear_shot"):
			if bot.global_position.distance_to(origin) <= BOTS_HEARING_RADIUS:
				bot.call("hear_shot", origin)


# ---------------------------------------------------------------------------
# Смена оружия и перезарядка.
# ---------------------------------------------------------------------------

func _select_weapon(index: int) -> void:
	if index == current_index:
		return
	if reload_timer > 0.0:
		reload_timer = 0.0
		reloading = false
		holders[current_index].rotation_degrees = BASE_HOLDER_ROT
		reload_finished.emit()
	_apply_selection(index, true)
	weapon_switched.emit(String(weapons[index]["name"]))
	ammo_changed.emit(int(weapons[index]["mag"]), int(weapons[index]["reserve"]))


func _apply_selection(index: int, animate: bool) -> void:
	current_index = index
	_kill_tween(_recoil_tween)
	_kill_tween(_raise_tween)
	_kill_tween(_reload_tween)
	for i in holders.size():
		holders[i].visible = i == index
		holders[i].position = holders_base[i]
		holders[i].rotation_degrees = BASE_HOLDER_ROT
	if animate:
		_raise_weapon()


func _raise_weapon() -> void:
	var holder := holders[current_index]
	var base := holders_base[current_index]
	holder.position = base + Vector3(0.0, -0.3, 0.15)
	_raise_tween = create_tween()
	_raise_tween.tween_property(holder, "position", base, 0.16).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)


func _start_reload() -> void:
	var weapon := weapons[current_index]
	if bool(weapon["melee"]):
		return
	if reloading or int(weapon["mag"]) >= int(weapon["mag_size"]) or int(weapon["reserve"]) <= 0:
		return
	reloading = true
	reload_timer = float(weapon["reload_time"])
	reload_started.emit(float(weapon["reload_time"]))
	var holder := holders[current_index]
	_kill_tween(_reload_tween)
	_reload_tween = create_tween()
	_reload_tween.tween_property(holder, "rotation_degrees", BASE_HOLDER_ROT + Vector3(26.0, 0.0, 8.0), 0.18).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)


func _finish_reload() -> void:
	var weapon := weapons[current_index]
	var need := int(weapon["mag_size"]) - int(weapon["mag"])
	var take := mini(need, int(weapon["reserve"]))
	weapon["mag"] = int(weapon["mag"]) + take
	weapon["reserve"] = int(weapon["reserve"]) - take
	reloading = false
	reload_timer = 0.0
	reload_finished.emit()
	ammo_changed.emit(int(weapon["mag"]), int(weapon["reserve"]))
	var holder := holders[current_index]
	_kill_tween(_reload_tween)
	_reload_tween = create_tween()
	_reload_tween.tween_property(holder, "rotation_degrees", BASE_HOLDER_ROT, 0.18).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)


# ---------------------------------------------------------------------------
# Состояние между раундами.
# ---------------------------------------------------------------------------

func on_player_died() -> void:
	_kill_tween(_death_tween)
	var holder := holders[current_index]
	_death_tween = create_tween()
	_death_tween.tween_property(holder, "position", holders_base[current_index] + Vector3(-0.08, -0.5, 0.1), 0.5).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)


func reset_for_round() -> void:
	_kill_tween(_recoil_tween)
	_kill_tween(_reload_tween)
	_kill_tween(_raise_tween)
	_kill_tween(_death_tween)
	reloading = false
	reload_timer = 0.0
	fire_cooldown = 0.0
	_bloom = 0.0
	_semi_lock = false
	for i in weapons.size():
		weapons[i]["mag"] = int(weapons[i]["mag_size"])
		weapons[i]["reserve"] = int(weapons[i]["reserve_max"])
	_apply_selection(0, false)
	weapon_switched.emit(String(weapons[0]["name"]))
	ammo_changed.emit(int(weapons[0]["mag"]), int(weapons[0]["reserve"]))


func _kill_tween(tween: Tween) -> void:
	if tween != null and tween.is_valid():
		tween.kill()
