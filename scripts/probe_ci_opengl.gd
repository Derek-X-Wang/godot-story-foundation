extends SceneTree
## Readiness only. The full portrait GPU assertions run separately.

func _initialize() -> void:
	var adapter := RenderingServer.get_video_adapter_name()
	var version := RenderingServer.get_video_adapter_api_version()
	var display := DisplayServer.get_name()
	var renderer := RenderingServer.get_current_rendering_method()
	if display.to_lower() != "x11" or renderer != "gl_compatibility" or adapter.is_empty() or version.is_empty():
		printerr("Expected real X11 Compatibility context, got %s/%s, adapter=%s, API=%s" % [
			display, renderer, adapter, version,
		])
		quit(1)
		return
	print("CI OpenGL ready: %s, API %s" % [adapter, version])
	quit()
