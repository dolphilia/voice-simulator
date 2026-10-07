"""HMM未知4文のピーク超過を、最終実行版と同じ一様利得で検証する。"""
import json
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest
from hts_transfer import render_hts
from fit_controls import measure,loss
from acoustics import evaluate


def main():
    import pyopenjtalk
    budget=Budget();out=RESULT/'hts-transfer-gain-v2'
    with budget.job('setup','HMM出力利得の修正検証を固定',1000000):
        save(out/'protocol.json',{'source_protocol_sha256':digest(RESULT/'hts-transfer/protocol.json'),
             'scope':'同じ4文への工学修正。モデル再学習・調整なし。独立品質確認ではない',
             'gain':'min(1,0.95/max(abs(audio))) を全波形に適用。最終runtime v2と同じ',
             'render_calls':16,'expected_changed_waves':6,'expected_additional_ai_calls':12,
             'reuse':'同じWAVハッシュの過去ASRを再利用し、異なる波形だけを両方式で再評価',
             'allocation':'残る13 AI枠を修正前後の内容比較へ配分。runtime2文の内容検査は見送り、失敗した1 AI予約は消費のまま残す'})
    voice=Path(pyopenjtalk.__file__).parent/'htsvoice/mei_normal.htsvoice'
    changed=0
    for row in json.loads((RESULT/'hts-transfer/protocol.json').read_text())['rows']:
        target=json.loads((RESULT/'hts-transfer'/row['id']/'teacher.json').read_text())['measurement']
        for name in ['baseline','direct_non_neural','neural_control','distilled']:
            prior=json.loads((RESULT/'hts-transfer'/row['id']/f'{name}.json').read_text())
            settings=prior.get('settings',{'speed':1.,'half_tone':0.})
            with budget.job('render',f'HMM利得修正/{name}/{row["id"]}',2000000):
                audio=render_hts(row,voice,settings['speed'],settings['half_tone'])
                raw_peak=float(np.max(np.abs(audio)));gain=min(1.,.95/raw_peak)
                audio*=gain
                measured=measure(audio);evaluation=evaluate(audio,{},24000)
                if not evaluation['E0_pass']:raise ValueError('利得修正後もE0不通過')
                path=out/row['id']/f'{name}.json';path.parent.mkdir(parents=True,exist_ok=True)
                wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
                sha=digest(path.with_suffix('.wav'));changed+=sha!=prior['sha256']
                save(path,{'id':row['id'],'text':row['text'],'settings':settings,'raw_peak':raw_peak,'output_gain':gain,
                    'measurement':measured,'objective':loss(measured,target),'evaluation':evaluation,
                    'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':sha,'prior_wav_sha256':prior['sha256'],
                    'same_wav_as_prior':sha==prior['sha256'],'runtime_neural_controller':name=='neural_control'})
    save(out/'render-summary.json',{'changed_waves':changed,'unchanged_waves':16-changed})
    if changed!=6:raise RuntimeError('変更波形数が予約前提と違うためAI評価開始前に停止')
    print(json.dumps({'changed':changed,'unchanged':16-changed}))


if __name__=='__main__':main()
