"""窓整合調波・保存24信号を各一回測定し、開発後に固定確認を実施。"""
from scipy.io import wavfile
from meter_io import *
from window_meter import WindowConsistentHarmonic

def main():
    p=verify_protocol();b=LocalBudget();m=load_metrics();out=[]
    with b.job('setup','固定測定器と調波投影辞書を初期化',1_000_000):
        meters={'window_harmonic':WindowConsistentHarmonic()}
        save(RESULT/'dictionary-audit.json',{'frequencies':len(meters['window_harmonic'].freq),'rank_valid':bool(meters['window_harmonic'].rank_ok.all()),
            'saved_dictionary_bytes':0,'basis_contains_reference_f0_or_mask':False,'new_wave_measurements':0})
    for phase in ('development','confirmation'):
        for method in p['methods']:
            part=[]
            if phase=='confirmation':
                gate=read(RESULT/f'{method}-development.json')['all_passed']
            else:gate=False
            for row in [r for r in p['rows'] if r['design']['phase']==phase]:
                design=row['design'];rec={'id':design['id'],'phase':phase,'method':method,'status':'failed','new_measurement_calls':0,
                    'confirmation_qualification_eligible':gate if phase=='confirmation' else None,'runtime_neural':False}
                try:
                    with b.job('audit',f"meter::{method}::{design['id']}",150_000):
                        wav=REPO/row['wav'];assert digest(wav)==row['wav_sha256'];fs,audio=wavfile.read(wav);assert fs==24000
                        rec['new_measurement_calls']=1
                        # 測定器はWAV配列だけを受け取る。正解・設計・分割の受け渡しは禁止。
                        f,t,diagnostic=meters[method].measure(audio)
                        dest=RESULT/'measurement'/method/f"{design['id']}.npz"
                        write_checked(dest,npz_bytes(f0=f,times=t,**diagnostic))
                        metrics=m.evaluate(design,f,t)
                        invalid=diagnostic['invalid_frames'].tolist()
                        # エネルギーゼロなどは不正測定フレーム。UVへ読み替えて合格させない。
                        integrity=len(invalid)==0
                        rec.update(status='completed',metrics=metrics,invalid_measurement_frames=invalid,
                            measurement_integrity_pass=integrity,qualification_pass=metrics['passed'] and integrity,
                            npz=str(dest.relative_to(REPO)),npz_sha256=digest(dest))
                except Exception as exc:rec['error']=repr(exc)
                dest=RESULT/'measurement'/method/f"{design['id']}.json";save(dest,rec);part.append(rec)
                out.append({'id':design['id'],'phase':phase,'method':method,'record':str(dest.relative_to(REPO)),'sha256':digest(dest),
                    'new_measurement_calls':rec['new_measurement_calls']})
                print({'phase':phase,'method':method,'id':design['id'],'status':rec['status'],'passed':rec.get('qualification_pass',False)},flush=True)
            base=m.aggregate(part)
            base['engineering_and_grid_passed']=base['passed'];base['passed']=sum(r.get('qualification_pass',False) for r in part)
            base['all_passed']=len(part)==12 and base['passed']==12
            base['integrity_failures']=[r['id'] for r in part if r.get('measurement_integrity_pass') is False]
            base['confirmation_qualification_eligible']=gate if phase=='confirmation' else None
            save(RESULT/f'{method}-{phase}.json',base)
    forbidden=[n for n in sys.modules if n.split('.')[0] in ('torch','tensorflow','transformers','pyworld','pyopenjtalk')];assert not forbidden
    save(RESULT/'measurement-manifest.json',{'rows':out,'new_measurement_calls':sum(r['new_measurement_calls'] for r in out),
        'forbidden_imports':forbidden,'runtime_neural':False,'quality_certified':False})
if __name__=='__main__':main()
