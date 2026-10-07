"""教師内部予測時計と固定IPA/HTS対応を検査する。音響正解認定ではない。"""
from paths import *
import re,numpy as np
from scipy.io import wavfile
MAP={'ɯ':'u','ɨ':'u','ɡ':'g','ɾ':'r','ɕ':'sh','ʥ':'j','ʨ':'ch','ʦ':'ts','ʣ':'z','ɸ':'f','β':'w','j':'y','ʔ':'cl','ɴ':'N','ŋ':'N'}
IGNORE=set(' .,!?:;()“”«»—…"')

def units(ipa,durations):
 if len(durations)!=len(ipa)+2 or any(int(x)!=x or x<1 for x in durations):raise ValueError('内部予測token時計不一致')
 items=[];clock=int(durations[0]);i=0
 while i<len(ipa):
  char_start=i;c=ipa[i];start=clock;clock+=int(durations[i+1]);i+=1
  if c in IGNORE:continue
  if c=='ː':
   if not items or items[-1]['phone'] not in 'aeiou':raise ValueError('長音の直前母音が不明')
   phone=items[-1]['phone']
  else:
   phone=MAP.get(c,c)
   if c in ['ɲ','ç']:phone=('n' if c=='ɲ' else 'h')+('' if i<len(ipa) and ipa[i]=='i' else 'y')
   if i<len(ipa) and ipa[i]=='ʲ':
    clock+=int(durations[i+1]);i+=1
    if i>=len(ipa):raise ValueError('palatalの後続母音が不明')
    if ipa[i]!='i':phone+='y'
   allowed={'a','i','u','e','o','N','cl','b','d','g','p','t','k','m','n','r','s','z','f','h','w','y','sh','ch','ts','j','by','dy','gy','py','ty','ky','my','ny','ry','hy'}
   if phone not in allowed:raise ValueError('未対応IPA '+repr(c)+' → '+phone)
  items.append(dict(phone=phone,start_frame=start,end_frame=clock,start_seconds=start*.025,end_seconds=clock*.025,source_IPA_slice=ipa[char_start:i]))
 return items

def align(row,meta,nsamples):
 d=meta['predicted_duration_frames'];assert sum(d)*600==nsamples,'内部25ms/frameと実波形sample数が不一致'
 phone_units=units(meta['phonemes'],d);labels=[dict(label_index=i,phone=re.search(r'\-([^+]+)\+',l)[1]) for i,l in enumerate(row['full_context_labels'])];spoken=[r for r in labels if r['phone'] not in ['sil','pau']]
 if len(spoken)!=len(phone_units):return dict(passed=False,reason='全音素数不一致',HTS=[x['phone'] for x in spoken],teacher_normalized=[x['phone'] for x in phone_units],clock_exact=True)
 mapped=[]
 for a,t in zip(spoken,phone_units):
  expected=a['phone'].lower() if a['phone'] in ['A','I','U','E','O'] else a['phone'];nasal=expected=='N' and t['phone'] in ['m','n']
  if expected!=t['phone'] and not nasal:return dict(passed=False,reason='全音素順序に非同値',HTS=[x['phone'] for x in spoken],teacher_normalized=[x['phone'] for x in phone_units],clock_exact=True)
  mapped.append(dict(a,**{k:v for k,v in t.items() if k!='phone'},teacher_phone=t['phone'],nasal_context_assimilation=nasal))
 return dict(passed=True,matched=mapped,clock_exact=True,phoneme_order_exact_under_fixed_equivalences=True,predicted_clock_not_acoustic_ground_truth=True)

def tests():
 assert [r['phone'] for r in units('kʲi noː.',[1]*10)]==['k','i','n','o','o']
 try:units('☃',[1,1,1])
 except ValueError:pass
 else:raise AssertionError('未知IPAを拒否')
 fake={'full_context_labels':['xx-sil+a=xx','xx-a+sil=xx','xx-sil+xx=xx']};m={'phonemes':'i','predicted_duration_frames':[1,1,1]};assert not align(fake,m,1800)['passed']
 return dict(palatal_and_long_vowel_clock=True,unknown_symbol_rejected=True,non_equivalent_sequence_rejected=True,fixture_not_quality_evidence=True)

def main():
 b=Budget();old=read(SRES/'protocol.json');used=read(SRES/'training-contract.json')['used'];lookup={r['id']:r for r in old['training_rows']};rows=[]
 with b.job(NAME,'audit','教師時計/全音素対応の負例fixtureを確認',reserve_bytes=10000) as j:b.save(HERE/'alignment-self-test.json',tests(),j)
 for u in used:
  r=lookup[u['id']]
  with b.job(NAME,'dsp','固定教師clock/IPA全列照合 '+r['id'],reserve_bytes=200000) as j:
   assert digest(REPO/r['teacher_metadata'])==r['teacher_metadata_sha256'] and digest(REPO/r['teacher_wav'])==r['teacher_wav_sha256'] and digest(REPO/r['source_training_input'])==r['source_sha256']
   meta=read(REPO/r['teacher_metadata']);fs,x=wavfile.read(REPO/r['teacher_wav']);assert fs==24000 and meta['text']==r['text']
   try:value=align(r,meta,len(x))
   except (ValueError,AssertionError) as exc:value=dict(passed=False,reason=repr(exc),clock_exact=False)
   value.update(id=r['id'],text=r['text'],length=r['length'],teacher_metadata_sha256=r['teacher_metadata_sha256'],teacher_wav_sha256=r['teacher_wav_sha256'],source_snapshot_sha256=r['source_sha256']);b.save(HERE/'alignment'/(r['id']+'.json'),value,j);rows.append(dict(row=r,result=value))
  print(r['id'],value['passed'],value.get('reason',''),flush=True)
 b.save(HERE/'alignment-manifest.json',dict(rows=rows,training_total=17,aligned=sum(r['result']['passed'] for r in rows),alignment_not_acoustic_ground_truth=True,target_gate_not_yet_evaluated=True,fit_performed=False,quality_certified=False));print(b.reconcile(),flush=True)
if __name__=='__main__':main()
