"""初波形前のASR固定件数だけを64→96へ別版で修正。元契約/生成条件を保持。"""
import argparse,ast,hashlib
from pathlib import Path
from budget import ROOT,read,digest
import radiated_waveguide_comparison_20261009 as e

def register():
    b=e.Budget();b.recover();assert not b.snapshot()['jobs'];assert not (e.HERE/'protocol.json').exists() and not (e.HERE/'render-manifest.json').exists()
    old=(e.HERE/'asr_worker.py').read_text();new=old.replace('64音声','96音声').replace("'/64'","'/96'").replace('assert len(rows) == 64','assert len(rows) == 96').replace('ai_calls=64','ai_calls=96');ast.parse(new)
    assert new!=old and 'assert len(rows) == 96' in new and 'ai_calls=96' in new
    with e.job(b,'setup','波形前にASRの固定件数だけ96へ修正した別版を登録',size=1000000) as j:
        b.write(e.HERE/'asr_worker-v2.py',new.encode(),j)
        b.save(e.HERE/'asr-count-amendment-v2.json',dict(original_controller_sha256=digest(ROOT/'radiated_waveguide_comparison_20261009.py'),effective_runner_sha256=digest(Path(__file__)),original_ASR_source_sha256=digest(e.HERE/'asr_worker.py'),effective_ASR_source_sha256=digest(e.HERE/'asr_worker-v2.py'),only_fixed_record_count_docstring_progress_and_AI_count_changed=True,new_waveforms=0,new_AI=0,source_generation_and_inputs_and_gates_unchanged=True,old_sources_and_contracts_kept=True,quality_goal_completed=False),j)
    print('初出力前のASR件数修正別版を登録',flush=True)
def asr(engine):
    a=read(e.HERE/'asr-count-amendment-v2.json');assert digest(Path(__file__))==a['effective_runner_sha256'] and digest(e.HERE/'asr_worker-v2.py')==a['effective_ASR_source_sha256']
    original=(ROOT/'radiated_waveguide_comparison_20261009.py').read_text();node=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='asr')
    source=ast.get_source_segment(original,node).replace("HERE/'asr_worker.py'","HERE/'asr_worker-v2.py'");scope=dict(vars(e));exec(compile(source,str(Path(__file__)),'exec'),scope);scope['asr'](engine)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','asr']);p.add_argument('--engine',choices=['whisper','reazon']);a=p.parse_args()
    if a.stage=='register':register()
    else:asr(a.engine)
