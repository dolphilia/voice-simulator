"""探索損失へ使用していないASRで教師と各方式の内容を監査する。"""
import json
import os
import sys
import time
from budget import Budget, ROOT, RESULT, save, digest

OLD = ROOT.parent/'autonomous-speech-synthesis'
sys.path.insert(0,str(OLD))
from diagnostics import normalize_text, edit_distance


def main():
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    from faster_whisper import WhisperModel
    import pyopenjtalk
    budget = Budget()
    with budget.job('setup','取得済みASRのローカル読込',1_000_000):
        model = WhisperModel('base',device='cpu',compute_type='int8',cpu_threads=4,
                             download_root=str(OLD/'.cache/ai/whisper'),local_files_only=True)
    rows = json.loads((RESULT/'splits.json').read_text())['rows']
    controls = {r['id']:r for r in json.loads((RESULT/'teacher-controls-v2.json').read_text())['rows']}
    sources=[]
    for row in rows:
        teacher = json.loads((ROOT/controls[row['id']]['teacher_source']).read_text())
        fitted = json.loads((RESULT/'fitted'/row['id']/'summary.json').read_text())
        variants = {'teacher':teacher['wav'],'handwritten':fitted['handwritten']['wav'],
                    'reference_fitted':fitted['fit']['best']['wav']}
        for name in ('direct_non_neural','neural_control','distilled_non_neural'):
            path = RESULT/'comparisons'/name/f'{row["id"]}.json'
            variants[name] = json.loads(path.read_text())['wav']
        sources.extend({'id':row['id'],'split':row['split'],'text':row['text'],'variant':name,'wav':path}
                       for name,path in variants.items())
    for row in sources:
        path = RESULT/'content'/row['variant']/f'{row["id"]}.json'
        if path.exists():
            if json.loads(path.read_text())['wav_sha256'] != digest(ROOT/row['wav']):
                raise ValueError('評価済み波形が変わりました')
            continue
        with budget.job('ai',f'{row["variant"]}/{row["id"]}',500_000) as ticket:
            start = time.monotonic()
            # 正解文・音素を認識器へ渡さない。
            segments, info = model.transcribe(str(ROOT/row['wav']),language='ja',beam_size=5,
                        initial_prompt=None,condition_on_previous_text=False,vad_filter=False)
            hyp = ''.join(segment.text for segment in segments)
            reference = normalize_text(pyopenjtalk.g2p(row['text'],kana=True))
            predicted = normalize_text(pyopenjtalk.g2p(hyp,kana=True)) if hyp else ''
            errors = edit_distance(reference,predicted)
            save(path,{**row,'hypothesis':hyp,'reference_kana':reference,'predicted_kana':predicted,
                       'errors':errors,'characters':len(reference),'kana_cer':errors/max(1,len(reference)),
                       'seconds':time.monotonic()-start,'ticket':ticket['id'],
                       'wav_sha256':digest(ROOT/row['wav']),'engine':'faster-whisper-base CPU int8',
                       'used_in_acoustic_optimization':False,'perception_qualification':False})
            print(json.dumps({'id':row['id'],'variant':row['variant'],'kana_cer':errors/max(1,len(reference))},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
