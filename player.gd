class_name PlayerController
extends CharacterBody3D
## Игрок от первого лица: движение WASD, прыжок, приседание (плавное, через lerp),
## обзор мышью (чувствительность из настроек), прицеливание на ПКМ, шаги,
## тряска камеры, здоровье и сигналы для HUD. Оружием управляет WeaponManager.

signal health_changed(current: int, max_health: int)
signal died

const GRAVITY := 14.0
const WALK_SPEED := 5.2
const CROUCH_SPEED := 2.7
const AIM_SPEED_MULT := 0.75
const JUMP_VELOCITY := 5.6
const ACCEL_GROUND := 14.0
const ACCEL_AIR := 3.5
const STAND_HEIGHT := 1.8
const CROUCH_HEIGHT := 1.15
const STAND_EYE := 1.62
const BASE_SENSITIVITY := 0.0022
const FOOTSTEP_INTERVAL := 0.38

var weapon_manager: WeaponManager
var controls_enabled := true
var health := 100
var max_health := 100
var dead := false
var crouching := false
var is_aiming := false
var last_attacker_name := "Enemy"

var _capsule: CapsuleShape3D
var _collision_shape: CollisionShape3D
var _head: Node3D
var _camera: Camera3D
var _capsule_height := STAND_HEIGHT
var _bob_time := 0.0
var _death_tween: Tween
var _shake := 0.0
var _footstep_timer := 0.0
var _air_time := 0.0
var _was_on_floor := true


func _ready() -> void:
	collision_layer = 2
	collision_mask = 1 | 4
	floor_snap_length = 0.4
	add_to_group("player")
	_build_body()


func _build_body() -> void:
	_capsule = CapsuleShape3D.new()
	_capsule.radius = 0.35
	_capsule.height = STAND_HEIGHT
	_collision_shape = CollisionShape3D.new()
	_collision_shape.shape = _capsule
	_collision_shape.position = Vector3(0.0, STAND_HEIGHT * 0.5, 0.0)
	add_child(_collision_shape)

	_head = Node3D.new()
	_head.name = "Head"
	_head.position = Vector3(0.0, STAND_EYE, 0.0)
	add_child(_head)

	_camera = Camera3D.new()
	_camera.name = "Camera"
	_camera.near = 0.05
	_head.add_child(_camera)

	weapon_manager = WeaponManager.new()
	weapon_manager.name = "WeaponManager"
	weapon_manager.camera = _camera
	weapon_manager.exclude_body_rid = get_rid()
	weapon_manager.recoil_requested.connect(_apply_recoil)
	_camera.add_child(weapon_manager)
	_apply_fov()


func _apply_fov() -> void:
	var fov := 85.0
	if SettingsManager.instance != null:
		fov = SettingsManager.instance.base_fov
	weapon_manager.base_fov = fov
	_camera.fov = fov


func _unhandled_input(event: InputEvent) -> void:
	if dead:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		var motion := event as InputEventMouseMotion
		var sensitivity := BASE_SENSITIVITY
		if SettingsManager.instance != null:
			sensitivity = BASE_SENSITIVITY * SettingsManager.instance.mouse_sensitivity
		rotate_y(-motion.relative.x * sensitivity)
		_head.rotation.x = clampf(_head.rotation.x - motion.relative.y * sensitivity, deg_to_rad(-89.0), deg_to_rad(89.0))
		weapon_manager.add_sway(motion.relative.x, motion.relative.y)
	elif event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton
		if mouse_event.pressed and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED and not get_tree().paused:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	var on_floor := is_on_floor()
	if not dead:
		_update_crouch(delta)
		is_aiming = Input.is_action_pressed("aim") and controls_enabled

	var input_dir := Vector2.ZERO
	if not dead and controls_enabled:
		input_dir = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := transform.basis * Vector3(input_dir.x, 0.0, input_dir.y)
	if direction.length() > 1.0:
		direction = direction.normalized()

	var target_speed := 0.0
	if not dead and controls_enabled:
		target_speed = CROUCH_SPEED if crouching else WALK_SPEED
		if is_aiming:
			target_speed *= AIM_SPEED_MULT
	var accel := ACCEL_GROUND if on_floor else ACCEL_AIR
	velocity.x = move_toward(velocity.x, direction.x * target_speed, accel * delta)
	velocity.z = move_toward(velocity.z, direction.z * target_speed, accel * delta)

	if not on_floor:
		velocity.y -= GRAVITY * delta
		_air_time += delta
	elif not dead and controls_enabled and Input.is_action_just_pressed("jump"):
		velocity.y = JUMP_VELOCITY
		SfxManager.instance.play("jump", -6.0)

	move_and_slide()

	# Приземление: звук + пыль + урон от падения не нужен (арена плоская).
	if is_on_floor() and not _was_on_floor:
		if _air_time > 0.25:
			SfxManager.instance.play("land", -4.0)
			FX.spawn_dust(get_tree().current_scene, global_position)
		_air_time = 0.0
	_was_on_floor = is_on_floor()

	if not dead:
		var eye_target := _capsule_height - 0.18
		_head.position.y = lerpf(_head.position.y, eye_target, minf(1.0, 12.0 * delta))
	var moving := (not dead) and controls_enabled and on_floor and Vector2(velocity.x, velocity.z).length() > 1.0
	_update_head_bob(delta, moving)
	_update_footsteps(delta, moving)
	_update_shake(delta)

	# FOV: база из настроек, при прицеливании сужается.
	var base_fov := 85.0
	if SettingsManager.instance != null:
		base_fov = SettingsManager.instance.base_fov
	weapon_manager.base_fov = base_fov
	var fov_target := base_fov * (0.8 if is_aiming else 1.0)
	_camera.fov = lerpf(_camera.fov, fov_target, minf(1.0, 12.0 * delta))

	weapon_manager.player_velocity = velocity
	weapon_manager.player_crouching = crouching
	weapon_manager.player_airborne = not is_on_floor()
	weapon_manager.ads_active = is_aiming
	weapon_manager.active = (not dead) and controls_enabled


func _update_crouch(delta: float) -> void:
	if Input.is_action_pressed("crouch"):
		crouching = true
	elif crouching and _can_stand_up():
		crouching = false
	var target := CROUCH_HEIGHT if crouching else STAND_HEIGHT
	if absf(_capsule_height - target) > 0.001:
		_capsule_height = lerpf(_capsule_height, target, minf(1.0, 12.0 * delta))
		_capsule.height = _capsule_height
		_collision_shape.position.y = _capsule_height * 0.5


func _can_stand_up() -> bool:
	# Проверяем потолок лучом вверх, чтобы не вставать под ящиком.
	var space := get_world_3d().direct_space_state
	var from := global_position + Vector3(0.0, _capsule_height * 0.5, 0.0)
	var to := global_position + Vector3(0.0, STAND_HEIGHT + 0.1, 0.0)
	var exclude: Array[RID] = [get_rid()]
	var query := PhysicsRayQueryParameters3D.create(from, to, 1, exclude)
	var hit := space.intersect_ray(query)
	return hit.is_empty()


func _update_head_bob(delta: float, moving: bool) -> void:
	if moving and not crouching:
		_bob_time += delta * 9.0
		_camera.position.y = sin(_bob_time) * 0.02
		_camera.position.x = cos(_bob_time * 0.5) * 0.012
	else:
		_camera.position.x = lerpf(_camera.position.x, 0.0, minf(1.0, 10.0 * delta))
		_camera.position.y = lerpf(_camera.position.y, 0.0, minf(1.0, 10.0 * delta))


func _update_footsteps(delta: float, moving: bool) -> void:
	if not moving:
		_footstep_timer = FOOTSTEP_INTERVAL * 0.4
		return
	_footstep_timer -= delta
	if _footstep_timer <= 0.0:
		_footstep_timer = FOOTSTEP_INTERVAL
		var volume := -16.0 if crouching else -8.0
		SfxManager.instance.play("footstep", volume)


func _update_shake(delta: float) -> void:
	if _shake > 0.001:
		_camera.h_offset = randf_range(-0.05, 0.05) * _shake
		_camera.v_offset = randf_range(-0.05, 0.05) * _shake
		_shake = maxf(0.0, _shake - delta * 2.5)
	else:
		_camera.h_offset = 0.0
		_camera.v_offset = 0.0


## Толчок камеры (взрыв рядом, урон).
func add_shake(amount: float) -> void:
	_shake = clampf(_shake + amount, 0.0, 1.5)


## Сделать камеру игрока активной (используется main.gd при старте матча).
func activate_camera() -> void:
	_camera.make_current()


func _apply_recoil(pitch_deg: float, yaw_deg: float) -> void:
	_head.rotation.x = clampf(_head.rotation.x + deg_to_rad(pitch_deg), deg_to_rad(-89.0), deg_to_rad(89.0))
	rotate_y(deg_to_rad(yaw_deg))


func take_damage(amount: float, attacker_name: String) -> void:
	if dead:
		return
	health = maxi(0, health - int(roundf(amount)))
	last_attacker_name = attacker_name
	SfxManager.instance.play("damage", -6.0)
	add_shake(0.25)
	health_changed.emit(health, max_health)
	if health <= 0:
		_die()


func _die() -> void:
	dead = true
	crouching = false
	is_aiming = false
	velocity.x *= 0.2
	velocity.z *= 0.2
	weapon_manager.on_player_died()
	if _death_tween != null and _death_tween.is_valid():
		_death_tween.kill()
	_death_tween = create_tween().set_parallel(true)
	_death_tween.tween_property(_head, "position:y", 0.35, 0.5).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_death_tween.tween_property(_head, "rotation:z", deg_to_rad(14.0), 0.5)
	died.emit()


func reset_for_round(spawn_pos: Vector3, yaw_deg: float) -> void:
	if _death_tween != null and _death_tween.is_valid():
		_death_tween.kill()
	dead = false
	crouching = false
	is_aiming = false
	health = max_health
	_capsule_height = STAND_HEIGHT
	_capsule.height = STAND_HEIGHT
	_collision_shape.position.y = STAND_HEIGHT * 0.5
	global_position = spawn_pos
	rotation = Vector3(0.0, deg_to_rad(yaw_deg), 0.0)
	velocity = Vector3.ZERO
	_head.rotation = Vector3.ZERO
	_head.position = Vector3(0.0, STAND_EYE, 0.0)
	_camera.position = Vector3.ZERO
	_shake = 0.0
	_apply_fov()
	weapon_manager.reset_for_round()
	health_changed.emit(health, max_health)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
