class_name Grenade
extends RigidBody3D
## Осколочная граната: физический снаряд с запалом, взрывается через ~1.9 с.
## Наносит урон с падением по расстоянию, проверяя стены рейкастом.

const FUSE := 1.9
const DAMAGE_RADIUS := 7.0
const MAX_DAMAGE := 98.0

var fuse := FUSE
var blink_time := 0.0
var blink_on := false

var _mesh_material: StandardMaterial3D
var _exploded := false


func _ready() -> void:
	collision_layer = 8
	collision_mask = 1
	mass = 0.35
	var physics := PhysicsMaterial.new()
	physics.bounce = 0.3
	physics.friction = 0.7
	physics_material_override = physics

	var mesh_instance := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.08
	sphere.height = 0.16
	mesh_instance.mesh = sphere
	_mesh_material = StandardMaterial3D.new()
	_mesh_material.albedo_color = Color(0.2, 0.32, 0.18)
	_mesh_material.roughness = 0.6
	_mesh_material.metallic = 0.3
	_mesh_material.emission_enabled = true
	_mesh_material.emission = Color(1.0, 0.1, 0.05)
	_mesh_material.emission_energy_multiplier = 0.0
	mesh_instance.material_override = _mesh_material
	add_child(mesh_instance)

	var lever := MeshInstance3D.new()
	var lever_box := BoxMesh.new()
	lever_box.size = Vector3(0.03, 0.09, 0.02)
	lever.mesh = lever_box
	lever.material_override = _mesh_material
	lever.position = Vector3(0.0, 0.1, 0.0)
	add_child(lever)

	var col := CollisionShape3D.new()
	var shape := SphereShape3D.new()
	shape.radius = 0.08
	col.shape = shape
	add_child(col)

	angular_velocity = Vector3(randf_range(-8.0, 8.0), randf_range(-8.0, 8.0), randf_range(-8.0, 8.0))


func _physics_process(delta: float) -> void:
	if _exploded:
		return
	fuse -= delta
	blink_time -= delta
	if blink_time <= 0.0:
		blink_time = 0.22 if fuse > 0.6 else 0.09
		blink_on = not blink_on
		_mesh_material.emission_energy_multiplier = 4.0 if blink_on else 0.0
	if fuse <= 0.0:
		_explode()


func _explode() -> void:
	_exploded = true
	var scene := get_tree().current_scene
	var explosion_pos := global_position
	FX.spawn_explosion(scene, explosion_pos)
	SfxManager.instance.play_at("explosion", explosion_pos, 2.0)

	var space := get_world_3d().direct_space_state
	# Урон ботам.
	for node in get_tree().get_nodes_in_group("bots"):
		var bot := node as Node3D
		if bot == null or not is_instance_valid(bot):
			continue
		var bot_damageable := bot as Bot
		if bot_damageable == null or bot_damageable.state == Bot.BotState.DEAD:
			continue
		var target := bot.global_position + Vector3(0.0, 0.9, 0.0)
		var dist := explosion_pos.distance_to(target)
		if dist > DAMAGE_RADIUS:
			continue
		if _wall_blocks(space, explosion_pos, target):
			continue
		var damage := MAX_DAMAGE * clampf(1.0 - dist / DAMAGE_RADIUS, 0.0, 1.0)
		bot_damageable.take_damage(damage, "HE Grenade", false)
	# Урон игроку (включая самоурон).
	var player := get_tree().get_first_node_in_group("player") as PlayerController
	if player != null and is_instance_valid(player) and not player.dead:
		var target := player.global_position + Vector3(0.0, 0.9, 0.0)
		var dist := explosion_pos.distance_to(target)
		if dist <= DAMAGE_RADIUS and not _wall_blocks(space, explosion_pos, target):
			var damage := MAX_DAMAGE * 0.6 * clampf(1.0 - dist / DAMAGE_RADIUS, 0.0, 1.0)
			player.take_damage(damage, "HE Grenade")
		if player != null and is_instance_valid(player):
			player.add_shake(clampf(1.2 - explosion_pos.distance_to(player.global_position) / 12.0, 0.1, 1.0))
	# Боты реагируют на звук взрыва.
	for node in get_tree().get_nodes_in_group("bots"):
		var bot := node as Node3D
		if bot != null and bot.has_method("hear_shot"):
			bot.call("hear_shot", explosion_pos)
	queue_free()


func _wall_blocks(space: PhysicsDirectSpaceState3D, from_pos: Vector3, target: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(from_pos, target, 1)
	return not space.intersect_ray(query).is_empty()
