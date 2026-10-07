"""旧既定波形を再測定し、HMM状態平均と実波形DIOの局所形状差を記録する。"""
import sys
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, RESULT, LRES, PILOT, read, save, digest
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld

def main():
    with LocalBudget().job('audit','既存8波形の状態平均と実波形の測定量差を点検',1000000):
        sources={r['text']:r for r in [read(p) for p in (LRES/'training-inputs/selection').glob('*.json')]}
        output=[]
        for d in read(LRES/'protocol.json')['development_rows']:
            training=sources[d['text']]
            path=LRES/'render'/d['id']/'neutral/native.wav'
            metadata=read(path.with_suffix('.json'))
            assert digest(path)==metadata['wav_sha256']
            fs,audio=wavfile.read(path)
            f0,t=pyworld.dio(audio.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
            f0=pyworld.stonemask(audio.astype(float),f0,t,fs)
            durations=np.array(training['snapshot']['duration']); boundaries=np.r_[0,np.cumsum(durations)]*.005
            pairs=[]
            for p in training['phones']:
                lo=p['label_index']*5; hi=lo+5
                mask=(t>=boundaries[lo])&(t<boundaries[hi]); voiced=f0[mask & (f0>=70) & (f0<=800)]
                if len(voiced)<3 or len(voiced)<mask.sum()*.5: continue
                pairs.append({'label_index':p['label_index'],'phone':p['phone'],
                    'teacher_log_f0':p['teacher_log_f0'],'state_log_f0':p['baseline_log_f0'],
                    'wave_log_f0':float(np.log(np.median(voiced))),'frames':len(voiced)})
            state=np.array([p['state_log_f0'] for p in pairs]); wave=np.array([p['wave_log_f0'] for p in pairs]); teacher=np.array([p['teacher_log_f0'] for p in pairs])
            delta=((state-state.mean())-(wave-wave.mean()))*12/np.log(2)
            teacher_center=(teacher-teacher.mean())*12/np.log(2)
            output.append({'text':d['text'],'source_wav_sha256':digest(path),'source_training_input_id':training['id'],
                'usable_common_phones':len(pairs),'teacher_target_phones':len(training['phones']),'pairs':pairs,
                'state_minus_wave_centered_half_tone_rmse':float(np.sqrt(np.mean(delta**2))),
                'state_minus_wave_centered_half_tone_max_abs':float(np.max(abs(delta))),
                'teacher_minus_state_centered_half_tone_mse':float(np.mean((teacher_center-(state-state.mean())*12/np.log(2))**2)),
                'teacher_minus_wave_centered_half_tone_mse':float(np.mean((teacher_center-(wave-wave.mean())*12/np.log(2))**2))})
        save(RESULT/'measurement-audit.json',{'rows':output,'new_wave_calls':0,'new_ai_calls':0,'new_fit_calls':0,
            'source_waveforms':'旧選別8文の既定波形。新規比較群の生成も再利用調整もなし。',
            'boundaries':'保存済みHMM状態継続長。実波形の人手音素境界ではない。',
            'interpretation':'状態平均と波形DIOの差の診断。DIO精度・境界ずれ・MLPG・励起の原因は分離しない。',
            'selection_not_retuned':True,'quality_certified':False})
    print([(r['usable_common_phones'],round(r['state_minus_wave_centered_half_tone_rmse'],3)) for r in output])

if __name__=='__main__': main()
