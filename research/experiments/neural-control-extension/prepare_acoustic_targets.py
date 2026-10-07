"""VTL指令時間と混同しない教師データを既存WAVから作る。再学習しない。"""
import json
import sys
import numpy as np
from scipy.io import wavfile
from post_analysis import PostBudget, POST, ROOT, PILOT, PRIOR, RESULT, save, digest
from teacher_alignment import align_saved
sys.path.insert(0, str(PILOT/'.cache/packages'))
import pyworld


def check_alignment():
    def t(chars):
        return {'phonemes':chars,'predicted_duration_frames':[1]*(len(chars)+2),'duration_seconds':len(chars)+2.}
    cases = [(['w','a'],'βa'),(['sh','i','N','b','u','N'],'ɕimbɯɴ'),(['y','a','N','d','a'],'janda'),(['o','o'],'oː')]
    for phones, chars in cases:
        result, _, _ = align_saved({'phonemes':phones},t(chars))
        assert [r['phone'] for r in result] == phones
        assert result[0]['start'] == 1 and result[-1]['end'] == len(chars)+1
    for phones, chars in [(['h','a','k','o'],'bako'),(['N','k','a'],'nka'),(['a'],'ai')]:
        try:
            align_saved({'phonemes':phones},t(chars))
        except ValueError:
            pass
        else:
            raise AssertionError('誤読・未許可の同一視を拒否しませんでした')
    return {'accepted_equivalences':len(cases),'rejected_mismatches':3,'synthetic_metadata_only':True}


def main():
    budget = PostBudget()
    with budget.job('audit', '保存済み教師の時間・F0を合成器固有の指令値から分離', 3000000):
        tests = check_alignment()
        rows = json.loads((RESULT/'protocol.json').read_text())['rows']
        sources = [(row, voice, RESULT/'teacher'/voice/(row['id']+'.json')) for voice in ['jf_alpha','jf_gongitsune'] for row in (rows if voice=='jf_alpha' else rows[:8])]
        output = []
        for row, voice, path in sources:
            teacher = json.loads(path.read_text())
            wav = ROOT/teacher['wav']
            if digest(wav) != teacher['wav_sha256']:
                raise ValueError('教師波形のハッシュ不一致')
            rec = {'id':row['id'],'voice':voice,'text':row['text'],'teacher_record':str(path.relative_to(ROOT)),
                   'teacher_sha256':digest(path),'wav_sha256':teacher['wav_sha256']}
            try:
                items, gaps, equivalences = align_saved(row,teacher)
            except ValueError as e:
                output.append({**rec,'status':'unavailable','reason':str(e)})
                continue
            fs, audio = wavfile.read(wav)
            x = audio.astype(np.float64)/(32768 if audio.dtype == np.int16 else 1)
            f0, time = pyworld.dio(x,fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
            f0 = pyworld.stonemask(x,f0,time,fs)
            phones = []
            for interval in items:
                mask = (time>=interval['start'])&(time<interval['end'])
                voiced = f0[mask&(f0>0)]
                phones.append({**interval,'teacher_internal_duration_seconds':interval['end']-interval['start'],
                               'measured_f0_hz':float(np.median(voiced)) if len(voiced) else None,
                               'f0_available_frames':len(voiced),'interval_frames':int(mask.sum()),
                               'f0_interpolated':False})
            output.append({**rec,'status':'available','phones':phones,'equivalences':equivalences,'gaps':gaps})
        forbidden = [name for name in sys.modules if name.split('.')[0] in ('torch','tensorflow','transformers','onnxruntime','sherpa_onnx','faster_whisper')]
        if forbidden:
            raise RuntimeError('追記解析にニューラル推論モジュールを検出: '+repr(forbidden))
        save(POST/'teacher-targets-v3.json', {'schema_version':3,'rows':output,'tests':tests,
            'quantity_contract':{'teacher_internal_duration_seconds':'保存済みニューラル教師のtoken時刻由来。実波形の独立した音素境界ではない',
                                 'measured_f0_hz':'DIO/StoneMask 70–800Hzで保存済み波形を測定。未検出をnullとし無声区間へ補間しない',
                                 'renderer_actuator_controls':'含めない。VTL指令値は別フィールド・別校正として扱う'},
            'symbol_mapping_source':str(PILOT/'.cache/packages/misaki/cutlet.py'),
            'symbol_mapping_source_sha256':digest(PILOT/'.cache/packages/misaki/cutlet.py'),
            'new_ai_inference':0,'new_generation':0,'new_training':0,'neural_imports':forbidden,
            'quality_certified':False,'future_use':'開発候補資料。既存評価の合否を改訂せず、これらを新規の未使用確認文として数えない'})
        print(json.dumps({'available':sum(r['status']=='available' for r in output),'unavailable':[(r['id'],r['voice'],r['reason']) for r in output if r['status']=='unavailable'],'tests':tests},ensure_ascii=False))


if __name__ == '__main__':
    main()
