class_name FX
extends RefCounted
## Утилиты визуальных эффектов: трассеры, вспышки выстрелов, следы попаданий.
## Все функции статические — они создают одноразовые меши на корневом узле
## текущей сцены и уничтожают их через короткий Tween.

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


## Вспышка выстрела: маленькая сфера + (опционально) короткая вспышка света.
static func spawn_muzzle_flash(root: Node, pos: Vector3, with_light: bool) -> void:
	if root == null:
		return
	var mesh := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.05
	sphere.height = 0.12
	mesh.mesh = sphere
	mesh.material_override = _unshaded_material(Color(1.0, 0.85, 0.35), 0.9)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(mesh)
	mesh.global_position = pos
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
	var mesh := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.05
	sphere.height = 0.12
	mesh.mesh = sphere
	mesh.material_override = _unshaded_material(color, 0.9)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(mesh)
	mesh.global_position = pos + normal * 0.03
	mesh.scale = Vector3.ONE * size_scale
	var tween := mesh.create_tween()
	tween.tween_property(mesh, "scale", Vector3.ONE * 0.01, 0.09)
	tween.tween_callback(mesh.queue_free)


static func _unshaded_material(color: Color, alpha: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color(color.r, color.g, color.b, alpha)
	if alpha < 0.99:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return m
