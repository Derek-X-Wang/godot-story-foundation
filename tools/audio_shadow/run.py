"""Explicit offline CLAP runner. No downloader, installer, model service or gate."""
import argparse
import array
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import contract as C


def resolve_model(model_dir, lock):
    root=model_dir.resolve()
    C.require(root.is_dir(),'model directory missing')
    # Reject unrecorded loadable files rather than allowing implicit loader fallback.
    allowed=C.MODEL_FILES|{'README.md','LICENSE','LICENSE.txt','LICENSE-Apache-2.0.txt'}
    C.require(all(p.is_file() and not p.is_symlink() and p.name in allowed for p in root.iterdir()), 'unsupported file/subdirectory/symlink in model directory')
    for name,h in lock['model']['files'].items():
        p=root/name;C.require(p.is_file() and not p.is_symlink() and C.sha(p)==h,'model file missing or hash mismatch: '+name)
    return root


def decode(path, ffmpeg, target):
    # Bounded temporary file avoids unbounded stdout/full-clip memory allocation.
    cap=256*1024*1024
    r=subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-protocol_whitelist','file,pipe',
        '-i',str(path),'-map','0:a:0','-vn','-sn','-dn','-ac','1','-ar','48000',
        '-f','f32le','-c:a','pcm_f32le','-fs',str(cap),str(target)],timeout=120,capture_output=True)
    C.require(r.returncode==0,'audio decode failed')
    C.require(target.exists() and 0<target.stat().st_size<cap and target.stat().st_size%4==0,'empty, truncated or capped PCM')
    values=array.array('f');values.frombytes(target.read_bytes())
    if sys.byteorder!='little':values.byteswap()
    C.require(all(C.number(x) for x in values),'nonfinite decoded PCM')
    return values


def run(lock, model_dir, base_dir, ffmpeg):
    C.validate(lock);root=resolve_model(model_dir,lock)
    versions={k:importlib.metadata.version(k) for k in C.PACKAGES}
    C.require(versions==lock['packages'],'installed dependency versions differ from lock; no install attempted')
    paths=[(base_dir/a['path']).resolve() for a in lock['assets']]
    for path,a in zip(paths,lock['assets']):
        C.require(path.is_file() and C.sha(path)==a['sha256'],'asset missing/hash mismatch')
    # Set before optional imports. This is application-layer offline enforcement,
    # not a substitute for an OS network/resource sandbox with hostile dependencies.
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
        HF_HUB_DISABLE_IMPLICIT_TOKEN='1',DO_NOT_TRACK='1',TOKENIZERS_PARALLELISM='false',
        OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
    def deny_network(event,args):
        if event in ('socket.connect','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr'):
            raise RuntimeError('network access prohibited by offline runner')
    sys.addaudithook(deny_network)
    import numpy as np
    import torch
    from transformers import ClapModel,ClapFeatureExtractor,RobertaTokenizerFast
    C.require(torch.version.cuda is None,'CPU-only torch build required')
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    torch.manual_seed(0);np.random.seed(0);torch.use_deterministic_algorithms(True)
    model=ClapModel.from_pretrained(str(root),local_files_only=True,use_safetensors=True,trust_remote_code=False).to('cpu').eval()
    extractor=ClapFeatureExtractor.from_pretrained(str(root),local_files_only=True)
    tokenizer=RobertaTokenizerFast.from_pretrained(str(root),local_files_only=True)
    C.require(extractor.sampling_rate==48000,'unsupported model sample rate')
    texts=[x['text'] for x in lock['labels']]
    # Fail rather than silently truncate caller labels into different prompts.
    tokens=tokenizer(texts,return_tensors='pt',padding=True,truncation=False)
    C.require(tokens['input_ids'].shape[1]<=77,'label exceeds supported 77 tokens')
    with torch.inference_mode(): text_vectors=model.get_text_features(**tokens).tolist()
    rows=[]
    for a,path in zip(lock['assets'],paths):
        with tempfile.TemporaryDirectory(prefix='audio-shadow-pcm-') as d:
            pcm=decode(path,ffmpeg,Path(d)/'audio.f32le')
            for i,w in enumerate(a['windows']):
                start=round(w['start_seconds']*48000);n=round(w['duration_seconds']*48000)
                C.require(n>0 and start+n<=len(pcm),'requested window exceeds decoded audio; no shortened crop')
                torch.manual_seed(0);np.random.seed(0)
                inputs=extractor(np.asarray(pcm[start:start+n],dtype=np.float32),sampling_rate=48000,return_tensors='pt')
                with torch.inference_mode(): embedding=model.get_audio_features(**inputs)[0].tolist()
                rows.append({'asset_id':a['id'],'window_index':i,'decoded_window_frames':n,
                    **C.rank(lock['labels'],text_vectors,embedding,a['expected_label'])})
        C.require(C.sha(path)==a['sha256'],'asset changed during inference')
    resolve_model(root,lock) # Bind completion to unchanged model/tokenizer/config bytes.
    return C.report(lock,rows,evidence_kind='local_clap_inference',versions=versions)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('lock',type=Path);p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--base-dir',type=Path,default=Path.cwd());p.add_argument('--ffmpeg',default='ffmpeg')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
    try:
        C.require(not args.output.exists() and not args.output.is_symlink(),'output must be new; preserve previous evidence')
        lock=C.validate(C.load(args.lock))
        result=run(lock,args.model_dir,args.base_dir,args.ffmpeg)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive create prevents replacing a file appearing during inference.
        with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
        return 0
    except (ValueError,OSError,RuntimeError,ImportError,subprocess.SubprocessError) as e:
        print('audio_shadow: '+str(e),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
