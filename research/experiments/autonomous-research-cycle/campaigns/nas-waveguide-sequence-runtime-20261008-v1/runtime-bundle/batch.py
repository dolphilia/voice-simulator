"""入力JSONからの生成だけ。隔離時も評価器や過去音声を読み込まない。"""
import sys,json,tempfile,os,hashlib
from pathlib import Path
from scipy.io import wavfile
from sequence_tract import generate,OUTFS
work=Path(sys.argv[1]);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
requests=json.loads(sys.stdin.read());rows=[]
for row in requests:
 audio,meta,*_=generate(row['request']);p=work/(row['id']+'.wav');wavfile.write(p,OUTFS,audio.astype('float32'))
 rows.append(dict(id=row['id'],wav_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),meta=meta))
print(json.dumps(dict(rows=rows,calls=sum(r['meta']['source_and_block_render_calls'] for r in rows),HMM=False,neural_inference=False,recorded_audio=False,utterance_lookup=False)))
