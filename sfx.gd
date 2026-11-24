class_name SfxManager
extends Node
## Процедурный звук: все эффекты синтезируются в коде (без .wav файлов)
## и хранятся как AudioStreamWAV. Доступен через SfxManager.instance.
## play() — обычный 2D-звук, play_at() — позиционный 3D-звук.

static var instance: SfxManager

const MIX_RATE := 22050

var streams: Dictionary = {}
var _pool: Array[AudioStreamPlayer] = []
var _pool_index := 0


func _enter_tree() -> void:
	SfxManager.instance = self


func _exit_tree() -> void:
	if SfxManager.instance == self:
		SfxManager.instance = null


func _ready() -> void:
	_build_streams()
	for i in 10:
		var player := AudioStreamPlayer.new()
		player.bus = "Master"
		add_child(player)
		_pool.append(player)


func play(sound_name: String, volume_db: float = 0.0) -> void:
	var stream: Variant = streams.get(sound_name)
	if stream == null:
		return
	var player := _pool[_pool_index]
	_pool_index = (_pool_index + 1) % _pool.size()
	player.stream = stream as AudioStream
	player.volume_db = volume_db
	player.pitch_scale = randf_range(0.96, 1.04)
	player.play()


func play_at(sound_name: String, pos: Vector3, volume_db: float = 0.0) -> void:
	var stream: Variant = streams.get(sound_name)
	if stream == null:
		return
	var scene := get_tree().current_scene
	if scene == null:
		return
	var player := AudioStreamPlayer3D.new()
	player.stream = stream as AudioStream
	player.volume_db = volume_db
	player.pitch_scale = randf_range(0.94, 1.03)
	player.max_distance = 70.0
	player.attenuation_filter_cutoff_hz = 8000.0
	scene.add_child(player)
	player.global_position = pos
	player.finished.connect(player.queue_free)
	player.play()


# ---------------------------------------------------------------------------
# Синтез.
# ---------------------------------------------------------------------------

func _build_streams() -> void:
	# Выстрел AK: резкий шумовой удар + низкий «бах».
	var ak := _mix(_noise(0.09, 22.0, 0.95), _tone(85.0, 0.09, 14.0, 0.8))
	streams["ak_shot"] = _to_stream(ak)
	# Выстрел пистолета: короче и выше.
	var glock := _mix(_noise(0.06, 28.0, 0.8), _tone(120.0, 0.06, 16.0, 0.6))
	streams["glock_shot"] = _to_stream(glock)
	# Сухой щелчок пустого магазина.
	streams["dry"] = _to_stream(_concat([_tone(2100.0, 0.02, 60.0, 0.3), _noise(0.015, 40.0, 0.2)]))
	# Перезарядка: три щелчка.
	streams["reload"] = _to_stream(_concat([
		_tone(1500.0, 0.02, 55.0, 0.35), _delay(_tone(900.0, 0.03, 40.0, 0.4), 0.16),
		_delay(_tone(1300.0, 0.02, 50.0, 0.45), 0.3),
	]))
	# Нож.
	streams["knife_swing"] = _to_stream(_noise(0.09, 10.0, 0.35))
	streams["knife_hit"] = _to_stream(_mix(_noise(0.05, 30.0, 0.5), _tone(320.0, 0.06, 20.0, 0.5)))
	# Попадания.
	streams["hit"] = _to_stream(_tone(1100.0, 0.05, 30.0, 0.45))
	streams["headshot"] = _to_stream(_tone(1650.0, 0.08, 24.0, 0.55))
	streams["kill"] = _to_stream(_concat([_tone(880.0, 0.07, 18.0, 0.5), _tone(1320.0, 0.09, 16.0, 0.5)]))
	# Взрыв и граната.
	streams["explosion"] = _to_stream(_mix(_noise(0.5, 6.0, 1.0), _tone(55.0, 0.45, 5.0, 0.9)))
	streams["throw"] = _to_stream(_noise(0.08, 14.0, 0.3))
	# Движение.
	streams["footstep"] = _to_stream(_noise(0.05, 45.0, 0.22))
	streams["jump"] = _to_stream(_noise(0.04, 40.0, 0.18))
	streams["land"] = _to_stream(_mix(_noise(0.06, 30.0, 0.4), _tone(90.0, 0.06, 18.0, 0.4)))
	streams["damage"] = _to_stream(_mix(_noise(0.06, 26.0, 0.5), _tone(140.0, 0.08, 14.0, 0.6)))
	# Раунд.
	streams["round_win"] = _to_stream(_concat([
		_tone(523.0, 0.12, 8.0, 0.4), _delay(_tone(659.0, 0.12, 8.0, 0.4), 0.13),
		_delay(_tone(784.0, 0.2, 6.0, 0.45), 0.26),
	]))
	streams["round_lose"] = _to_stream(_concat([
		_tone(440.0, 0.14, 8.0, 0.4), _delay(_tone(349.0, 0.14, 8.0, 0.4), 0.15),
		_delay(_tone(262.0, 0.24, 5.0, 0.45), 0.3),
	]))
	# Интерфейс и кейсы.
	streams["click"] = _to_stream(_tone(880.0, 0.03, 45.0, 0.3))
	streams["tick"] = _to_stream(_tone(1800.0, 0.02, 55.0, 0.3))
	streams["case_win"] = _to_stream(_concat([
		_tone(660.0, 0.1, 12.0, 0.45), _delay(_tone(880.0, 0.1, 12.0, 0.45), 0.11),
		_delay(_tone(1100.0, 0.18, 8.0, 0.5), 0.22),
	]))
	streams["buy"] = _to_stream(_concat([_tone(1200.0, 0.04, 40.0, 0.35), _delay(_tone(1600.0, 0.06, 35.0, 0.35), 0.07)]))


## Белый шум с экспоненциальным затуханием.
func _noise(duration: float, decay: float, amp: float) -> PackedFloat32Array:
	var count := int(duration * MIX_RATE)
	var samples := PackedFloat32Array()
	samples.resize(count)
	for i in count:
		var envelope := exp(-decay * float(i) / MIX_RATE)
		samples[i] = randf_range(-1.0, 1.0) * envelope * amp
	return samples


## Тон (синус) с затуханием.
func _tone(freq: float, duration: float, decay: float, amp: float) -> PackedFloat32Array:
	var count := int(duration * MIX_RATE)
	var samples := PackedFloat32Array()
	samples.resize(count)
	var phase := 0.0
	for i in count:
		var t := float(i) / MIX_RATE
		var envelope := exp(-decay * t)
		phase += TAU * freq / MIX_RATE
		samples[i] = sin(phase) * envelope * amp
	return samples


func _concat(parts: Array) -> PackedFloat32Array:
	var total := 0
	for part in parts:
		var samples := part as PackedFloat32Array
		total += samples.size()
	var result := PackedFloat32Array()
	result.resize(total)
	var offset := 0
	for part in parts:
		var samples := part as PackedFloat32Array
		for i in samples.size():
			result[offset + i] = samples[i]
		offset += samples.size()
	return result


func _mix(a: PackedFloat32Array, b: PackedFloat32Array) -> PackedFloat32Array:
	var count := maxi(a.size(), b.size())
	var result := PackedFloat32Array()
	result.resize(count)
	for i in count:
		var va := a[i] if i < a.size() else 0.0
		var vb := b[i] if i < b.size() else 0.0
		result[i] = (va + vb) * 0.85
	return result


func _delay(samples: PackedFloat32Array, seconds: float) -> PackedFloat32Array:
	var silence := int(seconds * MIX_RATE)
	var result := PackedFloat32Array()
	result.resize(silence + samples.size())
	for i in samples.size():
		result[silence + i] = samples[i]
	return result


func _to_stream(samples: PackedFloat32Array) -> AudioStreamWAV:
	var data := PackedByteArray()
	data.resize(samples.size() * 2)
	for i in samples.size():
		var value := int(clampf(samples[i], -1.0, 1.0) * 32000.0)
		data.encode_s16(i * 2, value)
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = MIX_RATE
	stream.stereo = false
	stream.data = data
	return stream
