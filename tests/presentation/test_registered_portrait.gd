extends SceneTree
const P=preload('res://addons/story_foundation/presentation/registered_portrait.gd')
var failures=0
var count=0
func check(v:bool):
	count+=1
	if not v:failures+=1;push_error('registered portrait check '+str(count))
func fixture(size:Vector2i)->Dictionary:
	var image=Image.create(size.x,size.y,false,Image.FORMAT_RGBA8)
	image.fill(Color(0.4,0.6,0.7,1))
	var tex=ImageTexture.create_from_image(image)
	return {'base_tex':tex,'half_tex':tex,'closed_tex':tex,'plate_tex':tex,'iris_tex':tex,'mask_tex':tex}
func definition()->Dictionary:
	return {'width':64,'height':96,'sourceHeight':96,'chest':[32,40,10,12],
	'eyes':[[25,20,4,3],[39,20,4,3]],'eyeRegions':[[21,17,8,6],[35,17,8,6]],
	'breathing':{'amplitude':0.5,'periodSeconds':4},
	'blink':{'starts':[1.6,5.6],'closeSeconds':0.1,'holdSeconds':0.1,'openSeconds':0.3}}
func _init():call_deferred('run')
func run():
	var p=P.new();root.add_child(p);await process_frame
	check(p.clock==0);p.sample(NAN);check(p.clock==0)
	var d=definition();var layers=fixture(Vector2i(64,96))
	check(p.configure(d,layers));p.pause_motion()
	d.breathing.amplitude=3;check(p.cfg.breathing.amplitude==0.5)
	p.sample(1);check(abs(p.mat.get_shader_parameter('breath')-0.5)<0.00001)
	check(p.mat.get_shader_parameter('canvas_size')==Vector2(64,96))
	var bad_scale=definition();bad_scale.sourceHeight=1.0e-300;check(not p.configure(bad_scale,layers))
	var bad_period=definition();bad_period.breathing.periodSeconds=1.0e-300;check(not p.configure(bad_period,layers))
	p.sample(1.0e100);check(is_finite(p.mat.get_shader_parameter('breath')));p.sample(1)
	var tiny_region=definition();tiny_region.chest[2]=1.0e-300;check(not p.configure(tiny_region,layers))
	var tiny_blink=definition();tiny_blink.blink.openSeconds=1.0e-300;check(not p.configure(tiny_blink,layers))
	var previous=p.mat
	for key in layers.keys():
		var bad=layers.duplicate();bad.erase(key);check(not p.configure(definition(),bad));check(p.mat==previous)
	check(not p.configure(definition(),fixture(Vector2i(63,96))))
	for field in ['width','height','sourceHeight','chest','eyes','eyeRegions','blink','breathing']:
		var bad=definition();bad.erase(field);check(not p.configure(bad,layers))
	for t in [NAN,INF,-1.0,1.0e308]:p.sample(t);check(p.clock==1)
	p.advance_motion(0.5);check(p.clock==1)
	p.resume_motion();p.advance_motion(0.5);check(p.clock==1.5)
	p.sample(1.75);check(p.mat.get_shader_parameter('blink')==1)
	check(p.position==Vector2.ZERO and p.rotation==0)
	p.free();print('REGISTERED_PORTRAIT ',count,' checks, ',failures,' failures');quit(1 if failures else 0)
