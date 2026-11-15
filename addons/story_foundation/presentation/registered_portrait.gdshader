shader_type canvas_item;
render_mode unshaded;
uniform sampler2D base_tex:filter_linear,repeat_disable;
uniform sampler2D half_tex:filter_linear,repeat_disable;
uniform sampler2D closed_tex:filter_linear,repeat_disable;
uniform sampler2D plate_tex:filter_linear,repeat_disable;
uniform sampler2D iris_tex:filter_linear,repeat_disable;
uniform sampler2D mask_tex:filter_linear,repeat_disable;
uniform vec2 canvas_size;
uniform vec4 chest;
uniform vec4 eye_a;
uniform vec4 eye_b;
uniform vec4 gaze_rect_a;
uniform vec4 gaze_rect_b;
uniform float breath=0.0;
uniform float blink=0.0;
uniform float gaze_x=0.0;
uniform float source_scale=1.0;
float fade(float v){return smoothstep(0.0,1.0,v);}
bool inside(vec2 p,vec4 r){return p.x>=floor(r.x)&&p.y>=floor(r.y)&&p.x<ceil(r.x+r.z)&&p.y<ceil(r.y+r.w);}
float eyelid_weight(vec2 p,vec4 e){float d=length((p-e.xy)/e.zw);return 1.0-smoothstep(.75,1.0,d);}
void fragment(){
 vec2 p=UV*canvas_size-vec2(.5);
 vec4 base=texture(base_tex,UV);
 float d=length((p-chest.xy)/chest.zw);float w=1.0-fade(d);
 vec2 offset=vec2((p.x-chest.x)*.025*w*breath,-5.0*w*breath*source_scale);
 vec4 outc=texture(base_tex,(p-offset+vec2(.5))/canvas_size);
 float ew=max(eyelid_weight(p,eye_a),eyelid_weight(p,eye_b));
 vec3 eye=blink<=.5?mix(base.rgb,texture(half_tex,UV).rgb,blink*2.0):mix(texture(half_tex,UV).rgb,texture(closed_tex,UV).rgb,blink*2.0-1.0);
 outc.rgb=mix(outc.rgb,eye,ew);
 if(inside(p,gaze_rect_a)||inside(p,gaze_rect_b)){
  vec4 iris=texture(iris_tex,UV-vec2(gaze_x,0.0)/canvas_size);
  vec3 target=mix(texture(plate_tex,UV).rgb,iris.rgb,iris.a);
  outc.rgb=mix(outc.rgb,target,texture(mask_tex,UV).a*(1.0-blink));
 }
 COLOR=outc;
}
