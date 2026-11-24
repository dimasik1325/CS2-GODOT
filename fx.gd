class_name FX
extends RefCounted
## Утилиты визуальных эффектов: трассеры, вспышки, следы попаданий, взрывы,
## гильзы и дым. Все функции статические — создают одноразовые меши на
## корневом узле текущей сцены и уничтожают их через короткий Tween.

## Случайное отклонение направления внутри конуса разброса (spread в радианах).
static func spread_direction(dir: Vector3, spread: float) -> Vector3:
	var dir_n := dir.normalized()
	if spread <= 0.0:
		return dir_n
	var t1 := dir_n.cross(Vector3.UP)
	if t1.length() < 0.01:
		t1 = dir_n.cross(Vector3.RIGHT)
	t1 = t1.normalized()
	var t2 := dir_n.cross(t1).normalized()
	var angle := randf() * TAU
	var radius := sqrt(randf()) * spread
	return (dir_n + t1 * cos(angle) * radius + t2 * sin(angle) * radius).normalized()


## Безопасное чтение нормали из результата intersect_ray.
static func normal_from(hit: Dictionary, fallback: Vector3) -> Vector3:
	var n: Variant = hit.get("normal")
	if n is Vector3:
		return n
	return fallback


static func _unshaded_material(color: Color, alpha: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color(color.r, color.g, color.b, alpha)
	if alpha < 0.99:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return m


static func _quick_mesh(root: Node, mesh: Mesh, color: Color, pos: Vector3, no_shadow: bool = true) -> MeshInstance3D:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.mesh = mesh
	mesh_instance.material_override = _unshaded_material(color, 0.9)
	if no_shadow:
		mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(mesh_instance)
	mesh_instance.global_position = pos
	return mesh_instance


## Светящийся трассер от дула до точки попадания.
static func spawn_tracer(root: Node, from_pos: Vector3, to_pos: Vector3, color: Color) -> void:
	if root == null:
		return
	var diff := to_pos - from_pos
	var dist := diff.length()
	if dist < 0.4:
		return
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(0.02, 0.02, 1.0)
	mesh.mesh = box
	mesh.material_override = _unshaded_material(color, 0.85)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(mesh)
	mesh.global_position = (from_pos + to_pos) * 0.5
	var up := Vector3.UP
	if absf(diff.normalized().dot(Vector3.UP)) > 0.99:
		up = Vector3.RIGHT
	mesh.look_at(to_pos, up)
	mesh.scale = Vector3(1.0, 1.0, dist)
	var tween := mesh.create_tween()
	tween.tween_property(mesh.material_override, "albedo_color:a", 0.0, 0.08)
	tween.tween_callback(mesh.queue_free)


## Вспышка выстрела: маленькая сфера + (опционально) вспышка света.
static func spawn_muzzle_flash(root: Node, pos: Vector3, with_light: bool) -> void:
	if root == null:
		return
	var mesh := _quick_mesh(root, SphereMesh.new(), Color(1.0, 0.85, 0.35), pos)
	(mesh.mesh as SphereMesh).radius = 0.05
	(mesh.mesh as SphereMesh).height = 0.12
	mesh.scale = Vector3.ONE * randf_range(0.8, 1.5)
	if with_light:
		var light := OmniLight3D.new()
		light.omni_range = 5.0
		light.light_energy = 2.2
		light.light_color = Color(1.0, 0.8, 0.45)
		light.shadow_enabled = false
		root.add_child(light)
		light.global_position = pos
		var light_tween := light.create_tween()
		light_tween.tween_property(light, "light_energy", 0.0, 0.07)
		light_tween.tween_callback(light.queue_free)
	var tween := mesh.create_tween()
	tween.tween_property(mesh, "scale", Vector3.ONE * 0.01, 0.07)
	tween.tween_callback(mesh.queue_free)


## Короткая вспышка в точке попадания (пыль от стены или кровь).
static func spawn_impact(root: Node, pos: Vector3, normal: Vector3, color: Color, size_scale: float = 1.0) -> void:
	if root == null:
		return
	var mesh := _quick_mesh(root, SphereMesh.new(), color, pos + normal * 0.03)
	(mesh.mesh as SphereMesh).radius = 0.05
	(mesh.mesh as SphereMesh).height = 0.12
	mesh.scale = Vector3.ONE * size_scale
	var tween := mesh.create_tween()
	tween.tween_property(mesh, "scale", Vector3.ONE * 0.01, 0.09)
	tween.tween_callback(mesh.queue_free)


## Взрыв: огненная сфера, свет, дым и искры.
static func spawn_explosion(root: Node, pos: Vector3) -> void:
	if root == null:
		return
	var fire := _quick_mesh(root, SphereMesh.new(), Color(1.0, 0.6, 0.15), pos)
	(fire.mesh as SphereMesh).radius = 0.5
	(fire.mesh as SphereMesh).height = 1.0
	fire.scale = Vector3.ONE * 0.4
	var fire_tween := fire.create_tween().set_parallel(true)
	fire_tween.tween_property(fire, "scale", Vector3.ONE * 3.2, 0.22).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	fire_tween.tween_property(fire.material_override, "albedo_color:a", 0.0, 0.3)
	fire_tween.chain().tween_callback(fire.queue_free)

	var light := OmniLight3D.new()
	light.omni_range = 14.0
	light.light_energy = 6.0
	light.light_color = Color(1.0, 0.6, 0.25)
	light.shadow_enabled = false
	root.add_child(light)
	light.global_position = pos + Vector3(0.0, 0.5, 0.0)
	var light_tween := light.create_tween()
	light_tween.tween_property(light, "light_energy", 0.0, 0.45)
	light_tween.tween_callback(light.queue_free)

	for i in 6:
		var smoke := _quick_mesh(root, SphereMesh.new(), Color(0.45, 0.42, 0.38, 0.75), pos)
		(smoke.mesh as SphereMesh).radius = 0.4
		(smoke.mesh as SphereMesh).height = 0.8
		smoke.scale = Vector3.ONE * randf_range(0.5, 0.9)
		var drift := Vector3(randf_range(-1.6, 1.6), randf_range(1.0, 2.6), randf_range(-1.6, 1.6))
		var smoke_tween := smoke.create_tween().set_parallel(true)
		smoke_tween.tween_property(smoke, "position", pos + drift, randf_range(0.7, 1.2)).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
		smoke_tween.tween_property(smoke, "scale", Vector3.ONE * 1.6, 1.0)
		smoke_tween.tween_property(smoke.material_override, "albedo_color:a", 0.0, 1.0)
		smoke_tween.chain().tween_callback(smoke.queue_free)

	for i in 10:
		var spark := _quick_mesh(root, SphereMesh.new(), Color(1.0, 0.9, 0.4), pos)
		(spark.mesh as SphereMesh).radius = 0.03
		(spark.mesh as SphereMesh).height = 0.06
		var spark_dir := Vector3(randf_range(-1.0, 1.0), randf_range(0.2, 1.4), randf_range(-1.0, 1.0)).normalized()
		var spark_tween := spark.create_tween()
		spark_tween.tween_property(spark, "position", pos + spark_dir * randf_range(2.0, 4.5), 0.3).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
		spark_tween.tween_callback(spark.queue_free)


## Выброс гильзы: маленькая латунная гильза с физикой (RigidBody3D).
static func spawn_shell(root: Node, pos: Vector3, eject_dir: Vector3, back_dir: Vector3) -> void:
	if root == null:
		return
	var body := RigidBody3D.new()
	body.collision_layer = 8
	body.collision_mask = 1
	body.mass = 0.02
	var physics := PhysicsMaterial.new()
	physics.bounce = 0.35
	physics.friction = 0.8
	body.physics_material_override = physics
	var mesh_instance := MeshInstance3D.new()
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = 0.012
	cylinder.bottom_radius = 0.014
	cylinder.height = 0.05
	mesh_instance.mesh = cylinder
	var brass := StandardMaterial3D.new()
	brass.albedo_color = Color(0.85, 0.68, 0.3)
	brass.metallic = 0.9
	brass.roughness = 0.3
	mesh_instance.material_override = brass
	body.add_child(mesh_instance)
	var col := CollisionShape3D.new()
	var shape := CylinderShape3D.new()
	shape.radius = 0.013
	shape.height = 0.05
	col.shape = shape
	body.add_child(col)
	root.add_child(body)
	body.global_position = pos
	body.linear_velocity = eject_dir * randf_range(1.6, 2.4) + Vector3.UP * randf_range(1.8, 2.6) + back_dir * 0.4
	body.angular_velocity = Vector3(randf_range(-12.0, 12.0), randf_range(-12.0, 12.0), randf_range(-12.0, 12.0))
	var tree := root.get_tree()
	if tree != null:
		var body_ref := body
		tree.create_timer(2.5).timeout.connect(func() -> void:
			if is_instance_valid(body_ref):
				body_ref.queue_free()
		)


## Облачко пыли под ногами при приземлении/беге.
static func spawn_dust(root: Node, pos: Vector3) -> void:
	if root == null:
		return
	var mesh := _quick_mesh(root, SphereMesh.new(), Color(0.75, 0.7, 0.6, 0.5), pos)
	(mesh.mesh as SphereMesh).radius = 0.15
	(mesh.mesh as SphereMesh).height = 0.3
	var tween := mesh.create_tween().set_parallel(true)
	tween.tween_property(mesh, "scale", Vector3(1.6, 0.6, 1.6), 0.4)
	tween.tween_property(mesh.material_override, "albedo_color:a", 0.0, 0.4)
	tween.chain().tween_callback(mesh.queue_free)
