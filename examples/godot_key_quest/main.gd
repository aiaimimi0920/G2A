extends Node2D
## 引擎拥有世界状态；Python sidecar 仅管理协议、认证与行动领取。

const KEY_POSITION := Vector2(690, 280)
const START_POSITION := Vector2(230, 280)

var fox_position := START_POSITION
var key_taken := false
var executions := 0
var chat_received := false
var status_text := "Connecting to the companion..."
var endpoint := ""
var session_path := ""
var admin_token := ""
var output_path := ""
var cursor := 0
var stopping := false
var claimed: Dictionary = {}


func _ready() -> void:
	endpoint = OS.get_environment("G2A_ENDPOINT")
	session_path = "/sessions/" + OS.get_environment("G2A_SESSION")
	admin_token = OS.get_environment("G2A_GAME_TOKEN")
	output_path = OS.get_environment("G2A_EVIDENCE")
	# 此示例仅连接启动器交给游戏的回环 sidecar，不接受远端下载或 URL 凭据。
	var origin_pattern := RegEx.new()
	origin_pattern.compile("^http://127\\.0\\.0\\.1:[0-9]{1,5}$")
	if origin_pattern.search(endpoint) == null or admin_token.is_empty():
		_fail("Missing trusted loopback launch configuration")
		return
	_run.call_deferred()
	var watchdog := Timer.new()
	watchdog.wait_time = 20.0
	watchdog.one_shot = true
	watchdog.timeout.connect(_watchdog)
	add_child(watchdog)
	watchdog.start()


func _draw() -> void:
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(36, 56), "G2A / GODOT KEY QUEST", HORIZONTAL_ALIGNMENT_LEFT, -1, 28)
	draw_rect(Rect2(60, 140, 760, 240), Color(0.13, 0.18, 0.25), true)
	draw_circle(Vector2(140, 280), 24, Color(0.35, 0.65, 1.0))
	draw_string(font, Vector2(110, 335), "Player")
	draw_circle(fox_position, 20, Color(1.0, 0.55, 0.2))
	draw_string(font, fox_position + Vector2(-35, 55), "Companion")
	if not key_taken:
		draw_circle(KEY_POSITION, 12, Color(1.0, 0.85, 0.25))
		draw_line(KEY_POSITION, KEY_POSITION + Vector2(34, 0), Color(1.0, 0.85, 0.25), 6)
	draw_string(font, Vector2(60, 425), status_text, HORIZONTAL_ALIGNMENT_LEFT, 760, 20)
	draw_string(
		font, Vector2(60, 470), "Game authority -> claim -> world check -> movement -> result"
	)


func _watchdog() -> void:
	if not stopping:
		_fail("Game interaction timed out")


func _call(path: String, body: Variant = null, expected_errors: Array = []) -> Dictionary:
	var request := HTTPRequest.new()
	request.timeout = 4.0
	request.max_redirects = 0
	request.body_size_limit = 262144
	add_child(request)
	var headers := PackedStringArray(
		["Content-Type: application/json", "Authorization: Bearer " + admin_token]
	)
	var method := HTTPClient.METHOD_GET if body == null else HTTPClient.METHOD_POST
	var payload := "" if body == null else JSON.stringify(body)
	var error := request.request(endpoint + path, headers, method, payload)
	if error != OK:
		request.queue_free()
		_fail("HTTP request could not start")
		return {}
	var response: Array = await request.request_completed
	request.queue_free()
	if response[0] != HTTPRequest.RESULT_SUCCESS:
		_fail("Game transport or protocol operation failed")
		return {}
	var parsed: Variant = JSON.parse_string(response[3].get_string_from_utf8())
	if not parsed is Dictionary:
		_fail("Invalid game-side response")
		return {}
	if response[1] != 200:
		var code: String = str(parsed.get("error", {}).get("code", ""))
		if code in expected_errors:
			return {"_protocol_error": code}
		_fail("Unexpected game protocol rejection")
		return {}
	return parsed


func _send(id: String, type: String, data: Dictionary) -> Dictionary:
	return await _call(
		session_path + "/events", {"id": id, "type": type, "sender": "key-quest", "data": data}
	)


func _run() -> void:
	await _send(
		"hall-1",
		"game.context",
		{
			"summary": "The player holds the monsters back; a key is visible in the hall.",
			"facts": {"room": "hall", "key_visible": true},
			"provenance": {"kind": "shared_experience", "source_id": "hall-1", "player_id": "alice"}
		}
	)
	while not stopping:
		var page := await _call(session_path + "/events?cursor=" + str(cursor))
		if page.is_empty():
			return
		cursor = int(page["cursor"])
		for entry in page["events"]:
			var message: Dictionary = entry["message"]
			if message["type"] == "chat.message" and message["sender"] == "fox":
				chat_received = true
				status_text = "Companion: " + str(message["data"]["text"])
				queue_redraw()
			if message["type"] == "action.request":
				await _execute(message)
		if page["session"]["state"] == "closed":
			await _finish()
			return
		await get_tree().create_timer(0.03).timeout


func _execute(message: Dictionary) -> void:
	var id: String = message["id"]
	if claimed.has(id):
		return
	var action := await _call(session_path + "/actions/" + id + "/claim", {}, ["not_executable"])
	if action.is_empty():
		return
	claimed[id] = true
	if action.has("_protocol_error"):
		var current := await _call(session_path + "/actions/" + id)
		if current.get("state") == "pending" and current.get("cancel_requested", false):
			await _report(id, "cancelled", {"reason": "cancelled_before_execution"})
		status_text = "Game did not execute a cancelled, expired or revoked action."
		queue_redraw()
		return
	# 协议许可不是世界条件。执行前由引擎再次判断房间、钥匙和场景状态。
	if (
		action["action"] != "find-key"
		or action["arguments"].get("room") != "hall"
		or key_taken
		or OS.get_environment("G2A_BLOCKED_KEY") == "1"
	):
		status_text = "Game rejected the action: the key is inaccessible."
		queue_redraw()
		await _report(id, "failed", {"reason": "world_condition"})
		return
	executions += 1
	var tween := create_tween()
	tween.tween_method(_move_fox, fox_position, KEY_POSITION, 0.8)
	await tween.finished
	# 动画不是事务。保留已经发生的移动，但拾取前再次检查终态和取消。
	var current := await _call(session_path + "/actions/" + id)
	if current.get("state") != "executing":
		status_text = "Session ended: movement occurred, but the key was not acquired."
		queue_redraw()
		return
	if current.get("cancel_requested", false):
		await _report(id, "cancelled", {"reason": "cancelled_before_pickup"})
		return
	key_taken = true
	status_text = "Key acquired. The game confirms the result to the companion."
	queue_redraw()
	await _report(id, "succeeded", {"item": "gold-key"})


func _move_fox(position_value: Vector2) -> void:
	fox_position = position_value
	queue_redraw()


func _report(id: String, state: String, details: Dictionary) -> void:
	# 会话可能在效果生效与回报之间结束；不伪造回滚，也不因此崩溃。
	await _call(
		session_path + "/events",
		{
			"id": "result-" + id,
			"type": "action.result",
			"sender": "key-quest",
			"data": {"request_id": id, "status": state, "details": details}
		},
		["session_closed", "action_terminal"]
	)


func _finish() -> void:
	stopping = true
	var screenshot := OS.get_environment("G2A_SCREENSHOT")
	if not screenshot.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		if get_viewport().get_texture().get_image().save_png(screenshot) != OK:
			_fail("Screenshot write failed")
			return
	var evidence := FileAccess.open(output_path, FileAccess.WRITE)
	if evidence == null:
		_fail("Evidence write failed")
		return
	evidence.store_string(
		JSON.stringify(
			{
				"engine": Engine.get_version_info()["string"],
				"key_taken": key_taken,
				"executions": executions,
				"chat_received": chat_received,
				"fox_x": fox_position.x,
				"session_closed": true
			}
		)
	)
	evidence.close()
	get_tree().quit(0)


func _fail(message: String) -> void:
	stopping = true
	push_error(message)
	get_tree().quit(1)
