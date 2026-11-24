class_name SaveManager
extends Node
## Экономика и прогресс: деньги, инвентарь скинов, статистика.
## Всё сохраняется в user://save.cfg. Доступен через SaveManager.instance.

static var instance: SaveManager

signal money_changed(amount: int)

const SAVE_PATH := "user://save.cfg"
const START_MONEY := 1000

var money: int = START_MONEY
var owned: PackedStringArray = PackedStringArray()
var equipped: Dictionary = {}   # weapon_name -> skin_id (String)
var total_kills: int = 0
var total_deaths: int = 0
var cases_opened: int = 0
var match_wins: int = 0


func _enter_tree() -> void:
	SaveManager.instance = self
	_load()


func _exit_tree() -> void:
	if SaveManager.instance == self:
		SaveManager.instance = null


func add_money(amount: int) -> void:
	money = maxi(0, money + amount)
	money_changed.emit(money)
	_save()


func try_spend(amount: int) -> bool:
	if money < amount:
		return false
	money -= amount
	money_changed.emit(money)
	_save()
	return true


func add_kill() -> void:
	total_kills += 1
	_save()


func add_death() -> void:
	total_deaths += 1
	_save()


func add_case_opened() -> void:
	cases_opened += 1
	_save()


func add_match_win() -> void:
	match_wins += 1
	_save()


func own_skin(skin_id: String) -> void:
	if skin_id == "" or owned.has(skin_id):
		return
	owned.append(skin_id)
	_save()


func is_owned(skin_id: String) -> bool:
	return owned.has(skin_id)


func equip_skin(weapon: String, skin_id: String) -> void:
	if skin_id == "":
		equipped.erase(weapon)
	else:
		equipped[weapon] = skin_id
	_save()


func get_equipped(weapon: String) -> String:
	var value: Variant = equipped.get(weapon, "")
	if value is String:
		return value
	return ""


func _save() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("economy", "money", money)
	cfg.set_value("economy", "owned", owned)
	cfg.set_value("economy", "equipped", equipped)
	cfg.set_value("stats", "total_kills", total_kills)
	cfg.set_value("stats", "total_deaths", total_deaths)
	cfg.set_value("stats", "cases_opened", cases_opened)
	cfg.set_value("stats", "match_wins", match_wins)
	cfg.save(SAVE_PATH)


func _load() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SAVE_PATH) != OK:
		return
	money = int(cfg.get_value("economy", "money", money))
	var owned_value: Variant = cfg.get_value("economy", "owned", PackedStringArray())
	if owned_value is PackedStringArray:
		owned = owned_value
	var equipped_value: Variant = cfg.get_value("economy", "equipped", {})
	if equipped_value is Dictionary:
		equipped = equipped_value
	total_kills = int(cfg.get_value("stats", "total_kills", 0))
	total_deaths = int(cfg.get_value("stats", "total_deaths", 0))
	cases_opened = int(cfg.get_value("stats", "cases_opened", 0))
	match_wins = int(cfg.get_value("stats", "match_wins", 0))
