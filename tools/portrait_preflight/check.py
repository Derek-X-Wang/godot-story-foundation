"""Read-only six-layer QA. Does not infer anatomy, aesthetics or auto-segment."""
import argparse,json,time
from pathlib import Path
from PIL import Image
LAYERS=('base','half','closed','eye-clear-plate','iris-layer','eye-aperture-mask')
def check(folder):
    start=time.perf_counter();errors=[];warnings=[];images={}
    for name in LAYERS:
        try:
            with Image.open(folder/(name+'.png')) as im:
                im.load()
                if im.format != 'PNG':
                    errors.append(f'{name}: expected PNG format')
                images[name]=im.convert('RGBA')
        except (OSError,ValueError) as exc:errors.append(f'{name}: unreadable PNG ({type(exc).__name__})')
    sizes={im.size for im in images.values()}
    if len(sizes)>1:errors.append('layer dimensions differ')
    try:
        cfg=json.loads((folder/'config.json').read_text())
        if 'base' in images and cfg.get('width')!=images['base'].width:errors.append('config width mismatches base')
    except (OSError,ValueError,AttributeError,UnicodeError):errors.append('configuration missing or invalid')
    base=images.get('base');alpha_bbox=None
    if base:
        alpha=base.getchannel('A');alpha_bbox=alpha.getbbox()
        if not alpha_bbox:errors.append('base is entirely transparent')
        if alpha.getextrema()[0]==255:errors.append('base is fully opaque: transparent cutout required')
        if alpha_bbox and (alpha_bbox[0]==0 or alpha_bbox[1]==0 or alpha_bbox[2]==base.width or alpha_bbox[3]==base.height):
            warnings.append('nontransparent pixels touch canvas edge; inspect possible crop')
    for name in ('iris-layer','eye-aperture-mask'):
        im=images.get(name)
        if im and im.getchannel('A').getbbox() is None:errors.append(name+': empty alpha')
    metadata=folder/'iris-layer.png.import'
    if not metadata.exists():errors.append('iris import metadata absent: RGB preservation unverified')
    else:
        try:
            pairs=[]
            section=None
            for raw in metadata.read_text().splitlines():
                line=raw.strip()
                if line.startswith('[') and line.endswith(']'):
                    section=line
                elif section=='[params]' and line.startswith('process/') and '=' in line:
                    pairs.append(line.split('=',1))
            for key in ('process/fix_alpha_border','process/premult_alpha'):
                values=[v.strip() for k,v in pairs if k.strip()==key]
                if values!=['false']:errors.append(key+': expected exactly one false import setting')
        except (OSError,UnicodeError):errors.append('iris import metadata unreadable')
    return {'character':folder.name,'passed':not errors,'errors':errors,'warnings':warnings,'dimensions':sorted(sizes),'alpha_bbox':alpha_bbox,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'scope':'structural PNG/import QA only; not full-body recognition or naturalness approval'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);a=p.parse_args()
    results=[check(f) for f in a.folders];print(json.dumps(results,indent=2));raise SystemExit(0 if all(r['passed'] for r in results) else 1)
