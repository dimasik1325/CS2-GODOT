class_name Skins
extends RefCounted
## Каталог скинов и система редкости для кейсов. Все скины — наборы цветов
## и свойств материалов, применяемых к процедурным моделям оружия.

const RARITY_NAMES: Array[String] = ["Mil-Spec", "Restricted", "Classified", "Covert", "Extraordinary"]
const RARITY_COLORS: Array[Color] = [
	Color(0.29, 0.41, 1.0),   # Mil-Spec — синий
	Color(0.53, 0.28, 1.0),   # Restricted — фиолетовый
	Color(0.83, 0.18, 0.9),   # Classified — розовый
	Color(0.92, 0.29, 0.29),  # Covert — красный
	Color(1.0, 0.84, 0.0),    # Extraordinary (нож) — золото
]
const RARITY_WEIGHTS: Array[float] = [0.45, 0.30, 0.17, 0.075, 0.005]

const CASE_PRICE := 500
const CASE_NAME := "Procedural Case"

# Поля скина: id, weapon, name, rarity, body / accent / metal (цвета),
# metalness, roughness (применяются ко всему оружию).
const CATALOG: Array[Dictionary] = [
	# AK-47.
	{"id": "ak_redline", "weapon": "AK-47", "name": "Redline", "rarity": 0,
		"body": Color(0.55, 0.1, 0.08), "accent": Color(0.12, 0.12, 0.13), "metal": Color(0.2, 0.2, 0.22), "metalness": 0.5, "roughness": 0.5},
	{"id": "ak_blue_lam", "weapon": "AK-47", "name": "Blue Laminate", "rarity": 0,
		"body": Color(0.16, 0.32, 0.55), "accent": Color(0.35, 0.28, 0.18), "metal": Color(0.25, 0.25, 0.27), "metalness": 0.5, "roughness": 0.55},
	{"id": "ak_safari", "weapon": "AK-47", "name": "Safari Mesh", "rarity": 0,
		"body": Color(0.52, 0.48, 0.35), "accent": Color(0.4, 0.37, 0.27), "metal": Color(0.3, 0.3, 0.3), "metalness": 0.4, "roughness": 0.8},
	{"id": "ak_neon", "weapon": "AK-47", "name": "Neon Rider", "rarity": 1,
		"body": Color(0.0, 0.75, 0.5), "accent": Color(0.1, 0.12, 0.25), "metal": Color(0.35, 0.4, 0.8), "metalness": 0.6, "roughness": 0.4},
	{"id": "ak_phoenix", "weapon": "AK-47", "name": "Phoenix Marking", "rarity": 1,
		"body": Color(0.6, 0.3, 0.05), "accent": Color(0.85, 0.55, 0.1), "metal": Color(0.22, 0.2, 0.18), "metalness": 0.5, "roughness": 0.5},
	{"id": "ak_vulcan", "weapon": "AK-47", "name": "Vulcan", "rarity": 2,
		"body": Color(0.15, 0.45, 0.85), "accent": Color(0.92, 0.94, 0.98), "metal": Color(0.4, 0.5, 0.7), "metalness": 0.7, "roughness": 0.3},
	{"id": "ak_asiimov", "weapon": "AK-47", "name": "Asiimov", "rarity": 3,
		"body": Color(0.9, 0.88, 0.85), "accent": Color(0.95, 0.45, 0.05), "metal": Color(0.15, 0.15, 0.16), "metalness": 0.4, "roughness": 0.45},
	{"id": "ak_gold", "weapon": "AK-47", "name": "Gold Arbitration", "rarity": 4,
		"body": Color(0.85, 0.65, 0.2), "accent": Color(0.7, 0.5, 0.15), "metal": Color(0.9, 0.72, 0.3), "metalness": 1.0, "roughness": 0.25},
	# Glock-18.
	{"id": "glock_twilight", "weapon": "Glock-18", "name": "Twilight", "rarity": 0,
		"body": Color(0.2, 0.22, 0.4), "accent": Color(0.35, 0.35, 0.5), "metal": Color(0.25, 0.25, 0.3), "metalness": 0.5, "roughness": 0.55},
	{"id": "glock_sand", "weapon": "Glock-18", "name": "Sand Dune", "rarity": 0,
		"body": Color(0.7, 0.6, 0.42), "accent": Color(0.5, 0.42, 0.3), "metal": Color(0.3, 0.3, 0.3), "metalness": 0.4, "roughness": 0.7},
	{"id": "glock_water", "weapon": "Glock-18", "name": "Water Elemental", "rarity": 1,
		"body": Color(0.1, 0.4, 0.75), "accent": Color(0.3, 0.75, 0.95), "metal": Color(0.2, 0.3, 0.5), "metalness": 0.55, "roughness": 0.45},
	{"id": "glock_urban", "weapon": "Glock-18", "name": "Urban Hazard", "rarity": 2,
		"body": Color(0.75, 0.75, 0.72), "accent": Color(0.9, 0.6, 0.05), "metal": Color(0.3, 0.3, 0.32), "metalness": 0.5, "roughness": 0.5},
	{"id": "glock_fade", "weapon": "Glock-18", "name": "Fade", "rarity": 3,
		"body": Color(0.95, 0.4, 0.75), "accent": Color(0.5, 0.2, 0.9), "metal": Color(0.85, 0.75, 0.5), "metalness": 0.85, "roughness": 0.3},
	{"id": "glock_gold", "weapon": "Glock-18", "name": "Gold Moss", "rarity": 4,
		"body": Color(0.85, 0.65, 0.2), "accent": Color(0.4, 0.45, 0.25), "metal": Color(0.9, 0.72, 0.3), "metalness": 1.0, "roughness": 0.25},
	# Knife.
	{"id": "knife_urban", "weapon": "Knife", "name": "Urban Masked", "rarity": 0,
		"body": Color(0.25, 0.26, 0.28), "accent": Color(0.35, 0.36, 0.38), "metal": Color(0.55, 0.57, 0.6), "metalness": 0.7, "roughness": 0.5},
	{"id": "knife_boreal", "weapon": "Knife", "name": "Boreal Forest", "rarity": 0,
		"body": Color(0.2, 0.35, 0.22), "accent": Color(0.3, 0.25, 0.15), "metal": Color(0.5, 0.52, 0.55), "metalness": 0.7, "roughness": 0.5},
	{"id": "knife_ultraviolet", "weapon": "Knife", "name": "Ultraviolet", "rarity": 1,
		"body": Color(0.35, 0.2, 0.6), "accent": Color(0.15, 0.1, 0.3), "metal": Color(0.6, 0.5, 0.8), "metalness": 0.75, "roughness": 0.4},
	{"id": "knife_crimson", "weapon": "Knife", "name": "Crimson Web", "rarity": 2,
		"body": Color(0.45, 0.05, 0.05), "accent": Color(0.2, 0.02, 0.02), "metal": Color(0.7, 0.6, 0.6), "metalness": 0.75, "roughness": 0.4},
	{"id": "knife_doppler", "weapon": "Knife", "name": "Doppler", "rarity": 3,
		"body": Color(0.1, 0.15, 0.5), "accent": Color(0.4, 0.1, 0.7), "metal": Color(0.8, 0.8, 0.95), "metalness": 0.95, "roughness": 0.2},
	{"id": "knife_fade", "weapon": "Knife", "name": "Fade", "rarity": 3,
		"body": Color(0.9, 0.45, 0.15), "accent": Color(0.95, 0.75, 0.3), "metal": Color(0.95, 0.85, 0.9), "metalness": 0.95, "roughness": 0.22},
	{"id": "knife_gold", "weapon": "Knife", "name": "Golden Doe", "rarity": 4,
		"body": Color(0.85, 0.65, 0.2), "accent": Color(0.6, 0.45, 0.12), "metal": Color(0.92, 0.75, 0.3), "metalness": 1.0, "roughness": 0.2},
]


static func get_skin(skin_id: String) -> Dictionary:
	for skin in CATALOG:
		if String(skin["id"]) == skin_id:
			return skin
	return {}


static func get_default_skin(weapon: String) -> Dictionary:
	return {"id": "", "weapon": weapon, "name": "Default", "rarity": -1,
		"body": Color.WHITE, "accent": Color.WHITE, "metal": Color.WHITE,
		"metalness": -1.0, "roughness": -1.0}


static func skins_for_weapon(weapon: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for skin in CATALOG:
		if String(skin["weapon"]) == weapon:
			result.append(skin)
	return result


static func random_skin_of_rarity(rarity: int) -> Dictionary:
	var pool: Array[Dictionary] = []
	for skin in CATALOG:
		if int(skin["rarity"]) == rarity:
			pool.append(skin)
	if pool.is_empty():
		return {}
	return pool[randi() % pool.size()]


## Взвешенный выбор редкости, затем случайный скин этой редкости.
static func case_roll() -> Dictionary:
	var roll := randf()
	var acc := 0.0
	var rarity := 0
	for i in RARITY_WEIGHTS.size():
		acc += RARITY_WEIGHTS[i]
		if roll <= acc:
			rarity = i
			break
	return random_skin_of_rarity(rarity)


static func case_roll_visual() -> Dictionary:
	# Для «декоративных» карточек в ленте открытия (любая редкость, любой скин).
	return random_skin_of_rarity(randi() % RARITY_NAMES.size())
