"""Generate a synthetic review site from existing public sprite fixtures only."""
import argparse
from pathlib import Path
from ..characters.pipeline import build as character
from ..manifest import canonical, digest
from .build import build


def create(output: Path) -> None:
    # Output must be new; never touch the game's website or an earlier example.
    output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[3]
    assets=[]
    for name in ('narrow','broad'):
        folder=output/name
        record=character(repo/f'examples/art/characters/{name}.json',folder)
        image={'path':f'{name}/atlas.png','sha256':digest(folder/'atlas.png')}
        assets.append({'asset_id':record['asset_id'],'kind':'animation','label':f'{name}: original sprite fixture','image':image,'atlas':{'path':f'{name}/atlas.json','sha256':digest(folder/'atlas.json')}})
    # A whole-sheet still exercises character/scene viewing without inventing art.
    for kind in ('character','scene'):
        assets.append({'asset_id':f'fixture_{kind}_still','kind':kind,'label':f'{kind} viewer test — sprite sheet stand-in, NOT production art','image':image})
    index=output/'review-index.json';index.write_bytes(canonical({'title':'Synthetic resource review fixture','assets':assets}))
    build(index,output/'site')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    create(p.parse_args().output)
