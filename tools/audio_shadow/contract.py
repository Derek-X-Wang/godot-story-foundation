"""Standard-library contract and cosine ranking; never a quality/approval gate."""
import hashlib
import json
import math
from pathlib import Path
import re

MODEL_FILES = frozenset(('config.json', 'preprocessor_config.json', 'model.safetensors',
    'merges.txt', 'vocab.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json'))
PACKAGES = frozenset(('torch', 'transformers', 'numpy', 'tokenizers', 'safetensors', 'huggingface-hub'))


def require(value, message):
    if not value: raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def load(path):
    require(Path(path).stat().st_size <= 1024*1024, 'lock exceeds 1 MiB')
    def pairs(values):
        d={}
        for k,v in values:
            require(k not in d, 'duplicate JSON key');d[k]=v
        return d
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def text(value):
    return isinstance(value,str) and 0<len(value.strip())<=4096


def number(value):
    try: return type(value) in (int,float) and math.isfinite(value)
    except OverflowError: return False


def hash_value(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def validate(lock):
    require(isinstance(lock,dict) and set(lock)=={'schema_version','model','packages','labels','assets'}, 'lock fields mismatch')
    require(type(lock['schema_version']) is int and lock['schema_version']==1, 'lock schema must be 1')
    model=lock['model']
    require(isinstance(model,dict) and set(model)=={'id','revision','files'}, 'model fields mismatch')
    require(text(model['id']) and text(model['revision']), 'model identity/revision required')
    require(isinstance(model['files'],dict) and set(model['files'])==MODEL_FILES and all(hash_value(h) for h in model['files'].values()), 'exact supported model file hashes required')
    require(isinstance(lock['packages'],dict) and set(lock['packages'])==PACKAGES and all(text(v) for v in lock['packages'].values()), 'exact package versions required')
    labels=lock['labels'];require(isinstance(labels,list) and 2<=len(labels)<=64,'2..64 labels required')
    ids=[]
    for label in labels:
        require(isinstance(label,dict) and set(label)=={'id','text'} and text(label['id']) and text(label['text']), 'label id/text required')
        ids.append(label['id'])
    require(len(ids)==len(set(ids)), 'duplicate label id')
    require(isinstance(lock['assets'],list) and 1<=len(lock['assets'])<=64,'1..64 assets required')
    assets=[];count=0
    for a in lock['assets']:
        require(isinstance(a,dict) and set(a)=={'id','path','sha256','expected_label','windows'}, 'asset fields mismatch')
        require(text(a['id']) and text(a['path']) and hash_value(a['sha256']), 'asset id/path/hash required')
        require(a['expected_label'] is None or a['expected_label'] in ids, 'expected label absent from candidates')
        require(isinstance(a['windows'],list) and 1<=len(a['windows'])<=16, '1..16 windows required')
        for w in a['windows']:
            require(isinstance(w,dict) and set(w)=={'start_seconds','duration_seconds'}, 'window fields mismatch')
            require(number(w['start_seconds']) and 0<=w['start_seconds']<=86400, 'invalid start time')
            require(number(w['duration_seconds']) and 0<w['duration_seconds']<=10, 'window duration must be (0,10] seconds')
        count+=len(a['windows']);assets.append(a['id'])
    require(len(assets)==len(set(assets)) and count<=256, 'duplicate asset or more than 256 windows')
    return lock


def rank(labels, text_vectors, audio_vector, expected_label=None):
    require(len(labels)==len(text_vectors) and len(labels)>=2, 'label/vector count mismatch')
    require(len({x['id'] for x in labels})==len(labels), 'duplicate label id')
    require(expected_label is None or expected_label in [x['id'] for x in labels], 'unknown expected label')
    require(isinstance(audio_vector,list) and 0<len(audio_vector)<=16384, 'invalid embedding size')
    def unit(v):
        require(isinstance(v,list) and len(v)==len(audio_vector) and all(number(x) for x in v),'nonfinite or mismatched embedding')
        scale=max(abs(x) for x in v);require(scale>0,'zero embedding')
        scaled=[x/scale for x in v];norm=math.sqrt(sum(x*x for x in scaled))
        return [x/norm for x in scaled]
    a=unit(audio_vector)
    values=[max(-1.,min(1.,sum(x*y for x,y in zip(a,unit(v))))) for v in text_vectors]
    order=sorted(range(len(values)),key=lambda k:(-values[k],k))
    top=[labels[i]['id'] for i in order if values[i]==values[order[0]]]
    return {'cosine_similarity':{label['id']:v for label,v in zip(labels,values)},
            'ranking':[labels[i]['id'] for i in order], 'top_minus_second':values[order[0]]-values[order[1]],
            'hint':'expected_label_not_top' if expected_label is not None and expected_label not in top else 'none',
            'hint_is_rejection':False}


def report(lock, rows, *, evidence_kind, versions):
    validate(lock)
    require(evidence_kind in ('synthetic_embedding_fixture','local_clap_inference'), 'unknown evidence kind')
    expected=[(a,i) for a in lock['assets'] for i in range(len(a['windows']))]
    require(len(rows)==len(expected), 'partial runs cannot produce completed report')
    for row,(a,i) in zip(rows,expected):
        require(row['asset_id']==a['id'] and row['window_index']==i, 'row identity/order mismatch')
    return {'schema_version':'audio-semantic-shadow.v1','status':'completed','mode':'shadow',
            'gating':False,'quality_approval':False,'perception_verified':False,
            'listening_status':'not_assessed','evidence_kind':evidence_kind,
            'lock_sha256':hashlib.sha256(canonical(lock)).hexdigest(),
            'model':lock['model'],'packages':versions,'labels':lock['labels'],
            'method':{'sample_rate_hz':48000,'channels':1,'sample_format':'float32',
                      'normalization':'PCM scale only; no loudness normalization',
                      'embedding_normalization':'L2; cosine similarity, not probability',
                      'seed':0,'cpu_threads':2,'batch_size':1,'short_window':'model-owned repeatpad/fusion'},
            'assets':[{k:v for k,v in a.items() if k!='path'} for a in lock['assets']], 'rows':rows,
            'limits':['Cosine ranking is relative to these labels, not probability or quality.',
                      'Overlapping windows are not independent samples.',
                      'A mismatch hint cannot automatically approve or reject an asset.',
                      'No listening, source rights, browser playback or user preference is established.']}
