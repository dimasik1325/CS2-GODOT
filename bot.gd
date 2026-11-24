class_name Bot
extends CharacterBody3D
## Бот-террорист: анимированная модель (ноги/руки/шлем/разгрузка), патрулирование,
## проверка видимости через PhysicsRayQueryParameters3D, погоня, стрельба
## очередями с задержкой реакции и разбросом (зависят от сложности),
## красная вспышка при попадании и падение при смерти.

signal died(bot: Node3D, weapon_name: String)

enum BotState { PATROL, COMBAT, SEEK, DEAD }

const GRAVITY := 14.0
const PATROL_SPEED := 3.0
const CHASE_SPEED := 4.4
const ACCEL := 16.0
const ATTACK_MIN_DIST := 6.0
const ATTACK_MAX_DIST := 20.0
const FOV_DEG := 105.0
const HEARING_RADIUS := 26.0
const SHOT_INTERVAL := 0.16
const PATROL_BOUNDS := 26.0
const HEAD_HEIGHT := 1.45
const SHOULDER_HEIGHT := 1.32

## Пресеты сложности: reaction_min, reaction_max, spread_mult, vision_dist, damage_mult.
const DIFFICULTIES: Dictionary = {
	0: {"reaction_min": 1.0, "reaction_max": 1.7, "spread_mult": 1.8, "vision_dist": 28.0, "damage_mult": 0.7},
	1: {"reaction_min": 0.5, "reaction_max": 0.95, "spread_mult": 1.0, "vision_dist": 40.0, "damage_mult": 1.0},
	2: {"reaction_min": 0.28, "reaction_max": 0.5, "spread_mult": 0.55, "vision_dist": 48.0, "damage_mult": 1.25},
}

var player: PlayerController
var bot_name := "Bot"
var weapon_name := "AK-47"
var ai_enabled := true
var health := 100.0
var state: BotState = BotState.PATROL

var _reaction_min := 0.5
var _reaction_max := 0.95
var _spread_mult := 1.0
var _vision_dist := 40.0
var _damage_mult := 1.0

var _visible_now := false
var _unseen_time := 10.0
var _last_seen_pos := Vector3.ZERO
var _react_timer := 1.0
var _burst_left := 4
var _shot_timer := 0.0
var _cooldown := 0.0
var _perception_timer := 0.0
var _waypoint := Vector3.ZERO
var _waypoint_wait := 0.0
var _seek_point := Vector3.ZERO
var _seek_wait := 0.0
var _stuck_time := 0.0
var _strafe_dir := 1.0
var _strafe_timer := 0.0

var _visual: Node3D
var _arms: Node3D
var _leg_l: Node3D
var _leg_r: Node3D
var _torso: Node3D
var _muzzle: Node3D
var _walk_phase := 0.0
var _flash_mats: Array[StandardMaterial3D] = []
var _flash_tween: Tween
var _death_tween: Tween


func _ready() -> void:
	collision_layer = 4
	collision_mask = 1 | 2 | 4
	add_to_group("bots")
	_apply_difficulty()
	_build_model()
	_pick_waypoint()
	_perception_timer = randf_range(0.0, 0.15)


func _apply_difficulty() -> void:
	var preset: Dictionary = DIFFICULTIES[1]
	if SettingsManager.instance != null:
		var index := clampi(SettingsManager.instance.difficulty, 0, 2)
		preset = DIFFICULTIES[index]
	_reaction_min = float(preset["reaction_min"])
	_reaction_max = float(preset["reaction_max"])
	_spread_mult = float(preset["spread_mult"])
	_vision_dist = float(preset["vision_dist"])
	_damage_mult = float(preset["damage_mult"])


# ---------------------------------------------------------------------------
# Модель бота из примитивов (с анимируемыми ногами и руками).
# ---------------------------------------------------------------------------

func _build_model() -> void:
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.35
	capsule.height = 1.8
	var col := CollisionShape3D.new()
	col.shape = capsule
	col.position = Vector3(0.0, 0.9, 0.0)
	add_child(col)

	_visual = Node3D.new()
	_visual.rotation.y = randf_range(-PI, PI)
	add_child(_visual)

	var shirt_mat := _flashable_mat(Color(0.62, 0.52, 0.36).darkened(randf() * 0.15))
	var pants_mat := _flashable_mat(Color(0.27, 0.25, 0.22).darkened(randf() * 0.1))
	var skin_mat := _flashable_mat(Color(0.72, 0.55, 0.42))
	_flash_mats = [shirt_mat, pants_mat, skin_mat]
	var mask_mat := _make_mat(Color(0.12, 0.12, 0.13), 0.8, 0.0)
	var helmet_mat := _make_mat(Color(0.18, 0.2, 0.16), 0.6, 0.2)
	var gun_mat := _make_mat(Color(0.14, 0.14, 0.15), 0.5, 0.6)
	var vest_mat := _make_mat(Color(0.2, 0.18, 0.15), 0.85, 0.0)
	var pouch_mat := _make_mat(Color(0.15, 0.13, 0.1), 0.9, 0.0)

	# Торс + разгрузка с подсумками.
	_torso = Node3D.new()
	_visual.add_child(_torso)
	_add_box_part(_torso, Vector3(0.5, 0.62, 0.3), shirt_mat, Vector3(0.0, 1.0, 0.0))
	_add_box_part(_torso, Vector3(0.53, 0.32, 0.34), vest_mat, Vector3(0.0, 1.06, 0.0))
	_add_box_part(_torso, Vector3(0.1, 0.12, 0.06), pouch_mat, Vector3(-0.15, 0.95, -0.19))
	_add_box_part(_torso, Vector3(0.1, 0.12, 0.06), pouch_mat, Vector3(0.15, 0.95, -0.19))
	# Голова, балаклава, шлем.
	_add_box_part(_torso, Vector3(0.26, 0.26, 0.26), skin_mat, Vector3(0.0, 1.5, 0.0))
	_add_box_part(_torso, Vector3(0.275, 0.13, 0.275), mask_mat, Vector3(0.0, 1.58, 0.0))
	_add_box_part(_torso, Vector3(0.3, 0.12, 0.3), helmet_mat, Vector3(0.0, 1.66, 0.0))
	# Ноги (шарниры на бёдрах, y = 0.85).
	_leg_l = _make_leg(pants_mat, Vector3(-0.13, 0.85, 0.0))
	_leg_r = _make_leg(pants_mat, Vector3(0.13, 0.85, 0.0))
	# Руки с оружием (шарнир на плечах, y = 1.32).
	_arms = Node3D.new()
	_arms.position = Vector3(0.0, SHOULDER_HEIGHT, 0.0)
	_visual.add_child(_arms)
	_add_box_part(_arms, Vector3(0.11, 0.11, 0.42), shirt_mat, Vector3(-0.18, -0.06, -0.2), Vector3(-8.0, 12.0, 0.0))
	_add_box_part(_arms, Vector3(0.11, 0.11, 0.34), shirt_mat, Vector3(0.14, -0.1, -0.14), Vector3(-30.0, -10.0, 0.0))
	_add_box_part(_arms, Vector3(0.07, 0.12, 0.5), gun_mat, Vector3(0.1, -0.08, -0.3))
	var mag := MeshInstance3D.new()
	var mag_box := BoxMesh.new()
	mag_box.size = Vector3(0.05, 0.14, 0.09)
	mag.mesh = mag_box
	mag.material_override = gun_mat
	mag.position = Vector3(0.1, -0.16, -0.22)
	mag.rotation_degrees.x = -20.0
	_arms.add_child(mag)

	_muzzle = Node3D.new()
	_muzzle.position = Vector3(0.1, -0.06, -0.62)
	_arms.add_child(_muzzle)


func _make_leg(mat: StandardMaterial3D, hip_pos: Vector3) -> Node3D:
	var leg := Node3D.new()
	leg.position = hip_pos
	_visual.add_child(leg)
	var thigh := MeshInstance3D.new()
	var thigh_mesh := BoxMesh.new()
	thigh_mesh.size = Vector3(0.16, 0.45, 0.17)
	thigh.mesh = thigh_mesh
	thigh.material_override = mat
	thigh.position = Vector3(0.0, -0.225, 0.0)
	leg.add_child(thigh)
	var boot := MeshInstance3D.new()
	var boot_mesh := BoxMesh.new()
	boot_mesh.size = Vector3(0.17, 0.14, 0.28)
	boot.mesh = boot_mesh
	boot.material_override = _make_mat(Color(0.1, 0.1, 0.1), 0.85, 0.0)
	boot.position = Vector3(0.0, -0.5, -0.04)
	leg.add_child(boot)
	return leg


func _make_mat(color: Color, roughness: float, metallic: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	m.metallic = metallic
	return m


func _flashable_mat(color: Color) -> StandardMaterial3D:
	var m := _make_mat(color, 0.9, 0.0)
	m.emission_enabled = true
	m.emission = Color(1.0, 0.0, 0.0)
	m.emission_energy_multiplier = 0.0
	return m


func _add_box_part(parent: Node3D, size: Vector3, mat: StandardMaterial3D, pos: Vector3, rot_deg: Vector3 = Vector3.ZERO) -> void:
	var mesh_instance := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh_instance.mesh = box
	mesh_instance.material_override = mat
	mesh_instance.position = pos
	mesh_instance.rotation_degrees = rot_deg
	parent.add_child(mesh_instance)


# ---------------------------------------------------------------------------
# Главный цикл ИИ.
# ---------------------------------------------------------------------------

func _physics_process(delta: float) -> void:
	if state == BotState.DEAD:
		velocity.x = move_toward(velocity.x, 0.0, ACCEL * delta)
		velocity.z = move_toward(velocity.z, 0.0, ACCEL * delta)
		if not is_on_floor():
			velocity.y -= GRAVITY * delta
		else:
			velocity.y = 0.0
		move_and_slide()
		return

	var player_alive := player != null and is_instance_valid(player) and not player.dead
	_perception_timer -= delta
	if _perception_timer <= 0.0:
		_perception_timer = 0.15
		_update_perception(player_alive)

	var move_dir := Vector3.ZERO
	var speed := PATROL_SPEED
	if ai_enabled and player_alive:
		match state:
			BotState.PATROL:
				move_dir = _do_patrol(delta)
				speed = PATROL_SPEED
			BotState.SEEK:
				move_dir = _do_seek(delta)
				speed = CHASE_SPEED
			BotState.COMBAT:
				move_dir = _do_combat(delta)
				speed = CHASE_SPEED
			BotState.DEAD:
				pass
	else:
		speed = 0.0

	var steered := _avoid_obstacles(move_dir)
	if move_dir.length() > 0.01:
		velocity.x = move_toward(velocity.x, steered.x * speed, ACCEL * delta)
		velocity.z = move_toward(velocity.z, steered.z * speed, ACCEL * delta)
		_update_stuck(delta)
	else:
		velocity.x = move_toward(velocity.x, 0.0, ACCEL * delta)
		velocity.z = move_toward(velocity.z, 0.0, ACCEL * delta)
		_stuck_time = 0.0
	_separate_from_bots()
	velocity.y -= GRAVITY * delta
	move_and_slide()
	_animate_model(delta, speed)


func _animate_model(delta: float, speed: float) -> void:
	# Шаги: ноги качаются в противофазе, корпус слегка подпрыгивает.
	var move_amount := Vector2(velocity.x, velocity.z).length()
	if move_amount > 0.5:
		_walk_phase += delta * move_amount * 2.4
		_leg_l.rotation.x = sin(_walk_phase) * 0.55
		_leg_r.rotation.x = sin(_walk_phase + PI) * 0.55
		_torso.position.y = absf(sin(_walk_phase)) * 0.04
	else:
		_leg_l.rotation.x = lerpf(_leg_l.rotation.x, 0.0, minf(1.0, 10.0 * delta))
		_leg_r.rotation.x = lerpf(_leg_r.rotation.x, 0.0, minf(1.0, 10.0 * delta))
		_torso.position.y = lerpf(_torso.position.y, 0.0, minf(1.0, 10.0 * delta))
	# В бою руки наводятся на игрока по вертикали.
	if state == BotState.COMBAT and player != null and is_instance_valid(player):
		var to_player := player.global_position + Vector3(0.0, 1.0, 0.0) - (global_position + Vector3(0.0, SHOULDER_HEIGHT, 0.0))
		var pitch := atan2(to_player.y, Vector2(to_player.x, to_player.z).length())
		_arms.rotation.x = lerpf(_arms.rotation.x, clampf(-pitch, deg_to_rad(-55.0), deg_to_rad(55.0)), minf(1.0, 8.0 * delta))
	else:
		_arms.rotation.x = lerpf(_arms.rotation.x, 0.0, minf(1.0, 8.0 * delta))


func _update_perception(player_alive: bool) -> void:
	if not player_alive or not ai_enabled:
		_visible_now = false
		return
	var to_player := player.global_position - global_position
	var dist := to_player.length()
	if dist > _vision_dist:
		_visible_now = false
	else:
		var flat := Vector3(to_player.x, 0.0, to_player.z)
		var in_fov := dist < 7.0
		if flat.length() > 0.5:
			var forward := -_visual.global_transform.basis.z
			var angle := rad_to_deg(forward.angle_to(flat.normalized()))
			if angle <= FOV_DEG * 0.5:
				in_fov = true
		if in_fov and _has_line_of_sight():
			_visible_now = true
			_last_seen_pos = player.global_position
			_unseen_time = 0.0
			if state == BotState.PATROL or state == BotState.SEEK:
				state = BotState.COMBAT
				_react_timer = randf_range(_reaction_min, _reaction_max)
				_burst_left = randi_range(3, 6)
				_shot_timer = 0.0
				_cooldown = 0.0
			return
		_visible_now = false
	_unseen_time += 0.15
	if state == BotState.COMBAT and _unseen_time > 2.2:
		state = BotState.SEEK
		_seek_point = _last_seen_pos
		_seek_wait = 0.0


func _has_line_of_sight() -> bool:
	var from := global_position + Vector3(0.0, 1.55, 0.0)
	var target := player.global_position + Vector3(0.0, 1.05, 0.0)
	var exclude: Array[RID] = [get_rid()]
	var query := PhysicsRayQueryParameters3D.create(from, target, 1 | 2, exclude)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return false
	return hit["collider"] == player


# ---------------------------------------------------------------------------
# Состояния.
# ---------------------------------------------------------------------------

func _do_patrol(delta: float) -> Vector3:
	if _waypoint_wait > 0.0:
		_waypoint_wait -= delta
		return Vector3.ZERO
	var to_waypoint := _waypoint - global_position
	to_waypoint.y = 0.0
	if to_waypoint.length() < 1.2:
		_waypoint_wait = randf_range(0.6, 1.6)
		_pick_waypoint()
		return Vector3.ZERO
	_face_direction(to_waypoint, delta)
	return to_waypoint.normalized()


func _do_seek(delta: float) -> Vector3:
	var to_seek := _seek_point - global_position
	to_seek.y = 0.0
	if to_seek.length() < 1.3:
		if _seek_wait <= 0.0:
			_seek_wait = randf_range(1.0, 2.0)
		else:
			_seek_wait -= delta
			if _seek_wait <= 0.0:
				state = BotState.PATROL
				_pick_waypoint()
		return Vector3.ZERO
	_face_direction(to_seek, delta)
	return to_seek.normalized()


func _do_combat(delta: float) -> Vector3:
	var to_player := player.global_position - global_position
	to_player.y = 0.0
	var dist := to_player.length()
	_face_direction(to_player, delta)
	_strafe_timer -= delta
	if _strafe_timer <= 0.0:
		_strafe_timer = randf_range(1.2, 2.6)
		_strafe_dir = -_strafe_dir
	var move_dir := Vector3.ZERO
	if dist > ATTACK_MAX_DIST:
		move_dir = to_player.normalized()
	elif dist < ATTACK_MIN_DIST:
		move_dir = -to_player.normalized()
	else:
		var side := Vector3(to_player.z, 0.0, -to_player.x).normalized()
		move_dir = side * _strafe_dir * 0.7
	if _react_timer > 0.0:
		_react_timer -= delta
		return move_dir
	if _cooldown > 0.0:
		_cooldown -= delta
		return move_dir
	_shot_timer -= delta
	if _shot_timer <= 0.0 and _visible_now:
		_shoot_at_player(dist)
		_burst_left -= 1
		if _burst_left <= 0:
			_burst_left = randi_range(3, 6)
			_cooldown = randf_range(0.7, 1.4)
		else:
			_shot_timer = SHOT_INTERVAL + randf() * 0.05
	return move_dir


func _shoot_at_player(dist: float) -> void:
	if _muzzle == null or player == null or not is_instance_valid(player):
		return
	var muzzle_pos := _muzzle.global_position
	var aim_target := player.global_position + Vector3(0.0, 1.0, 0.0)
	var aim := (aim_target - muzzle_pos).normalized()
	var move_speed := Vector2(velocity.x, velocity.z).length()
	var spread_deg := (1.6 + 2.4 * clampf(move_speed / CHASE_SPEED, 0.0, 1.0) + 0.035 * clampf(dist - 10.0, 0.0, 30.0)) * _spread_mult
	var dir := FX.spread_direction(aim, deg_to_rad(spread_deg))
	var to := muzzle_pos + dir * (dist + 6.0)
	var exclude: Array[RID] = [get_rid()]
	var query := PhysicsRayQueryParameters3D.create(muzzle_pos, to, 1 | 2, exclude)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	var end := to
	if not hit.is_empty():
		end = hit["position"]
		var collider: Variant = hit.get("collider")
		if collider == player:
			var base_damage := randf_range(7.0, 12.0) * _damage_mult
			var falloff := clampf(1.25 - dist / 55.0, 0.6, 1.25)
			player.take_damage(base_damage * falloff, bot_name)
		else:
			FX.spawn_impact(get_tree().current_scene, end, FX.normal_from(hit, Vector3.UP), Color(0.75, 0.68, 0.5))
	FX.spawn_tracer(get_tree().current_scene, muzzle_pos, end, Color(1.0, 0.85, 0.4))
	FX.spawn_muzzle_flash(get_tree().current_scene, muzzle_pos, false)
	SfxManager.instance.play_at("ak_shot", muzzle_pos, -8.0)


# ---------------------------------------------------------------------------
# Движение и обход препятствий.
# ---------------------------------------------------------------------------

func _face_direction(dir_flat: Vector3, delta: float) -> void:
	if dir_flat.length() < 0.01:
		return
	var target_yaw := atan2(-dir_flat.x, -dir_flat.z)
	_visual.rotation.y = lerp_angle(_visual.rotation.y, target_yaw, minf(1.0, 9.0 * delta))


func _pick_waypoint() -> void:
	for i in 10:
		var point := Vector3(randf_range(-PATROL_BOUNDS, PATROL_BOUNDS), 0.0, randf_range(-PATROL_BOUNDS, PATROL_BOUNDS))
		if global_position.distance_to(point) > 6.0:
			_waypoint = point
			return
	_waypoint = Vector3.ZERO


func _avoid_obstacles(dir: Vector3) -> Vector3:
	if dir.length() < 0.01:
		return dir
	var space := get_world_3d().direct_space_state
	var origin := global_position + Vector3(0.0, 0.9, 0.0)
	var forward := dir.normalized()
	if _cast_blocked(space, origin, forward, 2.0):
		var left := forward.rotated(Vector3.UP, deg_to_rad(55.0))
		var right := forward.rotated(Vector3.UP, deg_to_rad(-55.0))
		var left_blocked := _cast_blocked(space, origin, left, 1.7)
		var right_blocked := _cast_blocked(space, origin, right, 1.7)
		if not left_blocked and right_blocked:
			return left * dir.length()
		if not right_blocked and left_blocked:
			return right * dir.length()
		if not left_blocked and not right_blocked:
			var pick := left if randf() < 0.5 else right
			return pick * dir.length()
		return forward.rotated(Vector3.UP, PI * 0.5) * dir.length() * 0.6
	return dir


func _cast_blocked(space: PhysicsDirectSpaceState3D, origin: Vector3, dir: Vector3, dist: float) -> bool:
	var query := PhysicsRayQueryParameters3D.create(origin, origin + dir.normalized() * dist, 1)
	return not space.intersect_ray(query).is_empty()


func _update_stuck(delta: float) -> void:
	if Vector2(velocity.x, velocity.z).length() < 0.6:
		_stuck_time += delta
		if _stuck_time > 1.4:
			_stuck_time = 0.0
			if state == BotState.COMBAT:
				_strafe_dir = -_strafe_dir
			else:
				state = BotState.PATROL
				_pick_waypoint()
	else:
		_stuck_time = 0.0


func _separate_from_bots() -> void:
	for node in get_tree().get_nodes_in_group("bots"):
		if node == self:
			continue
		var other := node as Node3D
		if other == null:
			continue
		var diff := global_position - other.global_position
		diff.y = 0.0
		var d := diff.length()
		if d < 1.2 and d > 0.01:
			velocity += diff.normalized() * (1.2 - d) * 6.0


# ---------------------------------------------------------------------------
# Внешние воздействия.
# ---------------------------------------------------------------------------

## Выстрел или взрыв рядом — бот идёт проверять источник звука.
func hear_shot(from_pos: Vector3) -> void:
	if state == BotState.DEAD or not ai_enabled:
		return
	if global_position.distance_to(from_pos) > HEARING_RADIUS:
		return
	if state == BotState.PATROL or state == BotState.SEEK:
		state = BotState.SEEK
		_seek_point = from_pos
		_seek_wait = 0.0


func take_damage(amount: float, src_weapon: String, headshot: bool) -> void:
	if state == BotState.DEAD:
		return
	health -= amount
	_flash_red(1.3 if headshot else 1.0)
	if health <= 0.0:
		_die(src_weapon)


func _flash_red(intensity: float) -> void:
	if _flash_tween != null and _flash_tween.is_valid():
		_flash_tween.kill()
	_flash_tween = create_tween()
	_flash_tween.tween_method(_set_flash_energy, 1.6 * intensity, 0.0, 0.28)


func _set_flash_energy(value: float) -> void:
	for m in _flash_mats:
		m.emission_energy_multiplier = value


func _die(src_weapon: String) -> void:
	state = BotState.DEAD
	collision_layer = 0
	collision_mask = 1
	velocity = Vector3.ZERO
	if _death_tween != null and _death_tween.is_valid():
		_death_tween.kill()
	_death_tween = create_tween()
	var fall_dir := 90.0 if randf() < 0.5 else -90.0
	_death_tween.set_parallel(true)
	_death_tween.tween_property(_visual, "rotation_degrees:x", fall_dir, 0.55).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_death_tween.tween_property(_visual, "position:y", -0.55, 0.55).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_death_tween.tween_property(_leg_l, "rotation:x", 0.3, 0.55)
	_death_tween.tween_property(_leg_r, "rotation:x", -0.25, 0.55)
	died.emit(self, src_weapon)


func set_combat_enabled(enabled: bool) -> void:
	ai_enabled = enabled
