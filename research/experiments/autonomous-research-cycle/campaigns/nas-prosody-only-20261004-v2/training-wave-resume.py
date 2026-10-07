"""訓練代理lossと実波形の教師形状距離を別々に保存する限定診断。"""
from run import *

def main():
 b=Budget();p=read(HERE/'protocol.json');manifest=read(SRES/'target-manifest.json');original=read(SRES/'protocol.json')
 used={r['id'] for r in read(SRES/'training-contract.json')['used']};selected=[]
 for length in ['short','long']:selected.extend([r for r in original['training_rows'] if r['id'] in used and r['length']==length][:2])
 assert len(selected)==4
 with b.job(NAME,'setup','先頭短2長2の実波形追加診断を生成前固定',reserve_bytes=20000) as j:
  if (HERE/'training-wave-contract.json').exists():assert [r['id'] for r in read(HERE/'training-wave-contract.json')['selected']]==[r['id'] for r in selected]
  else:
   b.save(HERE/'training-wave-contract.json',{'selected':[{'id':r['id'],'text':r['text'],'length':r['length']} for r in selected],'selection':'訓練の固定順で各長さ先頭2。確認ASR前、損失や波形結果による選別なし','new_renders':8,'new_DSP':24,'local_limits_unchanged':True,'training_only_not_confirmation':True,'thresholds_unchanged':True},j)

 out=[]
 for row in selected:
  item=next(r for r in manifest['rows'] if r['id']==row['id']);searchpath=REPO/item['source_search'];assert digest(searchpath)==item['source_sha256']
  source=read(searchpath);supportpath=searchpath.parent.parent/'inverse-render'/row['id']/'support-contract.json';support=read(supportpath)
  before=read(REPO/row['source_training_input'])['snapshot'];native=source['native']
  for method in ['direct_prosody','distilled_prosody']:
   base=HERE/'training-wave'/row['id']/method;model=read(HERE/'models'/(method+'.json'))
   with b.job(NAME,'render','訓練波形 '+row['id']+'/'+method,reserve_bytes=3_000_000) as j:
    with StateEngine(row,BUNDLE/'mei_normal.htsvoice',speed=1.,half_tone=0.) as e:
     assert json.loads(json.dumps(e.snapshot()))==before;engine_before=e.snapshot()
     delta,phones=deltas(row,before,lambda x:predict(model,x));e.modify(delta);invariant(engine_before,e.snapshot(),delta);raw,lf0=e.generate()
    peak=float(np.max(abs(raw)));gain=min(1.,.95/peak) if peak else 1.;audio=(raw*gain).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1
    wav=io.BytesIO();wavfile.write(wav,24000,audio);b.write(base.with_suffix('.wav'),wav.getvalue(),j)
   with b.job(NAME,'dsp','訓練波形DIO/ACF/E0 '+row['id']+'/'+method,count=3,reserve_bytes=200000) as j:
    eligible=[q['label_index'] for q in describe(row) if q['phone'] in ELIGIBLE]
    value=measure(audio,lf0,before['duration'],support['indices'],eligible);f0,t=value.pop('f0'),value.pop('times');found,missing=extract_local(f0,t,before,support['indices'])
    complete=not missing and [r['label_index'] for r in found]==support['indices']
    mse=float(np.mean((centered_semitones([r['wave_log_f0'] for r in found])-np.asarray(support['teacher_shape_semitones']))**2)) if complete else None
    record={'id':row['id'],'method':method,'length':row['length'],'wav':str(base.with_suffix('.wav').relative_to(REPO)),'wav_sha256':digest(base.with_suffix('.wav')),'teacher_support':str(supportpath.relative_to(REPO)),'teacher_support_sha256':digest(supportpath),'support_complete':complete,'missing_support':missing,'wave_mse_to_teacher':mse,'saved_native_mse':native['wave_mse'],'below_native':mse is not None and mse<native['wave_mse'],'measurement':value,'training_only':True,'quality_certified':False}
    b.save(base.with_suffix('.json'),record,j);out.append(record)
 b.save(HERE/'training-wave-summary.json',{'rows':out,'new_render':8,'new_DSP':24,'teacher_target_waveform_diagnostic':True,'not_independent_confirmation':True,'no_selection_or_training_after_wave':True,'quality_certified':False})
 print({'training_wave_checks':len(out),'below_native':sum(r['below_native'] for r in out)},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
