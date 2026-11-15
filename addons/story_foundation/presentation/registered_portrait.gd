extends Sprite2D
const Schedule=preload("registered_portrait_schedule.gd")
var clock:=0.0
var paused:=false
var cfg:Dictionary # Internal copied definition; callers should not mutate it.
var mat:ShaderMaterial
## Consumer supplies registered Texture2D layers and copied numeric definitions.
## No private asset paths, name lookup, segmentation, or file import.
func configure(definition:Dictionary, layers:Dictionary)->bool:
	var candidate=definition
	if not validate_config(candidate):return false
	var textures={}
	for key in ['base_tex','half_tex','closed_tex','plate_tex','iris_tex','mask_tex']:
		if not layers.has(key) or not layers[key] is Texture2D:return false
		var tex:Texture2D=layers[key]
		if tex.get_width()!=int(candidate.width) or tex.get_height()!=int(candidate.height):return false
		textures[key]=tex

	# Commit only after every layer and field passes preflight.
	cfg=candidate.duplicate(true)
	mat=ShaderMaterial.new();mat.shader=preload('registered_portrait.gdshader')
	for key in textures:mat.set_shader_parameter(key,textures[key])
	texture=textures.base_tex
	material=mat;centered=false
	var s:float=float(cfg.height)/cfg.sourceHeight
	mat.set_shader_parameter('canvas_size',Vector2(cfg.width,cfg.height))
	mat.set_shader_parameter('source_scale',s)
	mat.set_shader_parameter('chest',v4(cfg.chest)*s)
	mat.set_shader_parameter('eye_a',v4(cfg.eyes[0])*s)
	mat.set_shader_parameter('eye_b',v4(cfg.eyes[1])*s)
	mat.set_shader_parameter('gaze_rect_a',v4(cfg.eyeRegions[0])*s)
	mat.set_shader_parameter('gaze_rect_b',v4(cfg.eyeRegions[1])*s)
	clock=0.0;paused=false;sample(0)
	return true

static func number(v)->bool:
	return (v is float or v is int) and is_finite(float(v))

static func positive(v)->bool:
	return number(v) and v>0

static func region(v)->bool:
	if not v is Array or v.size()!=4:return false
	for n in v:
		if not number(n):return false
	return v[0]>=0 and v[1]>=0 and v[2]>=0.001 and v[3]>=0.001 and v.max()<=1000000

static func validate_config(c:Dictionary)->bool:
	for k in ['width','height','sourceHeight','chest','eyes','eyeRegions','blink','breathing']:
		if not c.has(k):return false
	if not positive(c.width) or c.width!=int(c.width) or not positive(c.sourceHeight):return false
	if not positive(c.height) or c.height!=int(c.height):return false
	if c.width>16384 or c.height>16384 or c.sourceHeight<0.001 or c.sourceHeight>1000000:return false
	if not region(c.chest):return false
	for key in ['eyes','eyeRegions']:
		if not c[key] is Array or c[key].size()!=2:return false
		for r in c[key]:
			if not region(r):return false
	if not c.breathing is Dictionary or not c.blink is Dictionary:return false
	var b=c.breathing
	if not b.has('amplitude') or not number(b.amplitude) or b.amplitude<0 or b.amplitude>1000 or not b.has('periodSeconds') or not positive(b.periodSeconds) or b.periodSeconds<0.001:return false
	b=c.blink
	for k in ['closeSeconds','holdSeconds','openSeconds']:
		if not b.has(k) or not positive(b[k]) or b[k]<0.001:return false
	if not b.has('starts') or not b.starts is Array:return false
	var previous=-1.0
	var duration=b.closeSeconds+b.holdSeconds+b.openSeconds
	for t in b.starts:
		if not number(t) or t<0 or t+duration>8.0 or (previous>=0 and t<previous+duration):return false
		previous=t
	return true

func v4(a):return Vector4(a[0],a[1],a[2],a[3])
func sample(t:float):
	if mat == null or cfg.is_empty() or not is_finite(t) or t < 0 or not is_finite(t * TAU):
		return
	clock=t
	var c:=0.0
	for st in cfg.blink.starts:
		var d:float=fposmod(t,8.0)-st
		var b=cfg.blink
		if d>=0 and d<b.closeSeconds:c=smoothstep(0,b.closeSeconds,d)
		elif d>=b.closeSeconds and d<b.closeSeconds+b.holdSeconds:c=1
		elif d>=b.closeSeconds+b.holdSeconds and d<b.closeSeconds+b.holdSeconds+b.openSeconds:c=1-smoothstep(0,b.openSeconds,d-b.closeSeconds-b.holdSeconds)
	mat.set_shader_parameter('blink',c)
	mat.set_shader_parameter('breath',sin(fposmod(t,cfg.breathing.periodSeconds)/cfg.breathing.periodSeconds*TAU)*cfg.breathing.amplitude)
	mat.set_shader_parameter('gaze_x',Schedule.sample(t,Vector2(2.5*float(cfg.height)/cfg.sourceHeight,0),true).x)
func _process(delta):
	advance_motion(delta)
func pause_motion():paused=true
func resume_motion():paused=false
func advance_motion(delta:float):
	if not paused and is_finite(delta) and delta>0:sample(clock+delta)
