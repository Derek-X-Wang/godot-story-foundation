/* Optional read-only browser adapter. No storage, network calls, engine or CMS. */
'use strict';
const Preview = (() => {
  function frameAt(tag, elapsed) {
    const total = tag.durations_ms.reduce((a,b)=>a+b,0);
    if (!tag.loop && elapsed >= total) return tag.start+tag.count-1;
    let t = tag.loop ? Math.max(0,elapsed)%total : Math.max(0,elapsed);
    for(let i=0;i<tag.count;i++) {if(t<tag.durations_ms[i])return tag.start+i;t-=tag.durations_ms[i];}
    return tag.start+tag.count-1;
  }
  function link(asset,tag,frame,point) {
    const p=new URLSearchParams({asset:asset.asset_id,version:asset.version,tag:tag||'',frame:String(frame)});
    if(point){p.set('x',point[0]);p.set('y',point[1]);}return '#'+p;
  }
  function resolve(data,hash) {
    const p=new URLSearchParams(hash.replace(/^#/,''));
    const asset=p.get('asset');
    const index=asset===null?0:data.assets.findIndex(a=>a.asset_id===asset&&a.version===p.get('version'));
    if(index<0)throw Error('Requested asset/version is absent. No substitute version was selected.');
    const a=data.assets[index], tags=a.atlas?.tags||[];
    const tag=tags.length?(p.has('tag')?tags.find(t=>t.name===p.get('tag')):tags[0]):null;
    if(tags.length&&!tag)throw Error('Requested animation tag is absent.');
    const frame=p.has('frame')?Number(p.get('frame')):(tag?.start||0);
    if(!Number.isInteger(frame)||frame<(tag?.start||0)||frame>=(tag?tag.start+tag.count:1))throw Error('Requested frame is outside this animation.');
    const rect=a.atlas?.frames[frame].rect||[0,0,a.width,a.height];
    let point=null;
    if(p.has('x')||p.has('y')) {point=[Number(p.get('x')),Number(p.get('y'))];if(!p.has('x')||!p.has('y')||!point.every(Number.isInteger)||point[0]<0||point[1]<0||point[0]>=rect[2]||point[1]>=rect[3])throw Error('Requested pixel is outside the frame.');}
    return {index,tag,frame,point};
  }
  function feedback(a,tag,frame,point,url,notes) {return `Asset: ${a.asset_id}\nVersion (content SHA-256): ${a.version}\nKind: ${a.kind}\nTag: ${tag||'(still)'}\nFrame (zero-based): ${frame}\nPixel (frame-local): ${point?point.join(', '):'(not selected)'}\nPreview: ${url}\nRequested change / observation: ${notes}\nAcceptance: not determined by preview`;}
  return {frameAt,link,resolve,feedback};
})();
if(typeof module!=='undefined')module.exports=Preview;
if(typeof document!=='undefined') (()=>{
  const $=id=>document.getElementById(id), data=window.PREVIEW;
  let state, image, playing=false, start=0, base=0, generation=0;
  const stop=()=>{playing=false;$('play').textContent='Play';};
  const current=()=>data.assets[state.index];
  function updateLink(){const a=current();$('direct').href=Preview.link(a,state.tag?.name,state.frame,state.point);}
  function draw(){if(!image||!image.complete||!image.naturalWidth)return;const a=current(),r=a.atlas?.frames[state.frame].rect||[0,0,a.width,a.height],c=$('canvas');c.width=r[2];c.height=r[3];c.style.width=r[2]*Number($('scale').value)+'px';c.style.height=r[3]*Number($('scale').value)+'px';c.getContext('2d').drawImage(image,...r,0,0,r[2],r[3]);$('position').textContent=`Frame ${state.frame}${state.tag?' / '+(state.tag.start+state.tag.count-1):''}`;updateLink();}
  function select(){stop();const a=current();$('identity').textContent=`${a.asset_id} · ${a.kind} · version ${a.version}`;$('assets').value=state.index;$('tags').replaceChildren();for(const t of a.atlas?.tags||[]){const o=new Option(t.name,t.name);$('tags').add(o);}if(state.tag)$('tags').value=state.tag.name;for(const id of ['tags','play','prev','next'])$(id).disabled=!state.tag;$('error').textContent='';const gen=++generation;image=new Image();image.onload=()=>{if(gen===generation)draw();};image.onerror=()=>{if(gen===generation)$('error').textContent='Preview image failed to load; no visual acceptance established.';};image.src=a.image;}
  function load(){try{state=Preview.resolve(data,location.hash);select();}catch(e){stop();image=null;$('canvas').width=0;$('error').textContent=e.message;for(const id of ['tags','play','prev','next','feedback','copy'])$(id).disabled=true;}}
  $('title').textContent=data.title;data.assets.forEach((a,i)=>$('assets').add(new Option(`${a.label} [${a.kind}] · ${a.version.slice(0,10)}`,i)));
  $('assets').onchange=()=>{const a=data.assets[Number($('assets').value)];location.hash=Preview.link(a,a.atlas?.tags[0].name,a.atlas?.tags[0].start||0,null);};
  $('tags').onchange=()=>{stop();state.tag=current().atlas.tags.find(t=>t.name===$('tags').value);state.frame=state.tag.start;state.point=null;draw();};
  $('scale').onchange=draw;
  for(const [id,delta] of [['prev',-1],['next',1]])$(id).onclick=()=>{stop();state.frame=Math.max(state.tag.start,Math.min(state.tag.start+state.tag.count-1,state.frame+delta));state.point=null;draw();};
  $('play').onclick=()=>{if(playing){stop();return;}playing=true;state.point=null;start=performance.now();base=state.tag.durations_ms.slice(0,state.frame-state.tag.start).reduce((a,b)=>a+b,0);$('play').textContent='Pause';};
  function tick(now){if(playing){state.frame=Preview.frameAt(state.tag,base+now-start);draw();if(!state.tag.loop&&base+now-start>=state.tag.durations_ms.reduce((a,b)=>a+b,0))stop();}requestAnimationFrame(tick);}
  $('canvas').onclick=e=>{stop();const r=$('canvas').getBoundingClientRect();state.point=[Math.min($('canvas').width-1,Math.floor((e.clientX-r.left)*$('canvas').width/r.width)),Math.min($('canvas').height-1,Math.floor((e.clientY-r.top)*$('canvas').height/r.height))];updateLink();};
  $('feedback').onclick=()=>{$('output').value=Preview.feedback(current(),state.tag?.name,state.frame,state.point,$('direct').href,$('notes').value);};
  $('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('output').value);$('error').textContent='Feedback copied; send it through your existing review channel.';}catch(_){$('output').focus();$('output').select();$('error').textContent='Automatic clipboard unavailable. Copy the selected feedback text manually.';}};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});window.addEventListener('blur',stop);window.addEventListener('hashchange',load);load();requestAnimationFrame(tick);
})();
