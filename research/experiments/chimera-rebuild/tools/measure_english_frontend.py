"""英語発音の参照データ、句の時刻・F0、既存音素でのPCMを比較する。"""

import argparse
import gzip
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE/'cases/english-frontend.json'
AUDIO_CASE = WORKSPACE/'cases/english-mom-pop.json'
PROBE = WORKSPACE/'tools/upstream_english_probe.rs'
DICT = WORKSPACE/'data/cmudict.txt.gz'
DICT_LICENSE = WORKSPACE/'data/CMUDICT-LICENSE.txt'
FIXTURE = UPSTREAM/'crates/chimera/tests/golden'
CLI = ['cargo','run','--locked','--release','-p','vocal-cli','--']
SUITES = ('english','golden_phonetics_text')


def planned_symbol(part):
    segment = part['segment']
    kind = part['manner'] or '?'
    row = {'ipa':segment['ipa'],'kind':kind,'t0':part['start_seconds'],'t1':part['end_seconds']}
    if kind=='vowel':
        row['stress']=segment.get('stress',0)
    return row


def parts(entry):
    return [{
        'phrase':{k:p[k] for k in ('words','segments','intonation','pause')},
        'pitch':[{**g,'targets':{'f0':g['targets']['f0_hz']}} for g in p['pitch']],
        'segments':[planned_symbol(s) for s in p['timing']['segments']],
        **{k:p[k] for k in ('start_seconds','end_seconds','shown')},
    } for p in entry['phrases']]


def words_only(data):
    return [{'w':row['word'],'lts':row['lts'],
             **{key:{mode:row[key][mode]['segments'] for mode in ('reduce','full')} for key in ('dict','noDict')}}
            for row in data['words']]


def compare_frontend(data, upper, cases, tolerance):
    entries=[]
    for local,remote,example in zip(data['entries'],upper['entries'],cases,strict=True):
        observed={k:local[k] for k in ('id','dictionary','shown','end_seconds','render_end_seconds')}
        observed['phrases']=parts(local)
        mismatch,err=timing.compare(observed,remote,tolerance)
        expected=example.get('expect')
        registered=None
        if expected is not None:
            seen=[]
            for p,exp in zip(local['phrases'],expected,strict=True):
                observed_prediction={**p,'last_pitch_hz': p['pitch'][-1]['targets']['f0_hz'] if p['pitch'] else None}
                seen.append({k:observed_prediction[k] for k in exp})
            registered,_=timing.compare(seen,expected,tolerance)
        next_start=.05
        boundaries=[]
        for p in local['phrases']:
            boundaries.append(len(p['words'])==sum(s.get('wordEnd',False) for s in p['segments'])
                              and len(p['words'])==len(p['sources'])
                              and math.isclose(p['start_seconds'],next_start,rel_tol=0,abs_tol=tolerance))
            next_start=p['end_seconds']+p['pause']
        tail=abs(local['render_end_seconds']-local['end_seconds']-.3)<=tolerance
        entries.append({'id':example['id'],'first_upstream_difference':mismatch,'prediction_difference':registered,
                        'maximum_checked_numeric_error':err,'boundaries_and_tail':all(boundaries) and tail,
                        'passed':mismatch is None and registered is None and all(boundaries) and tail})
    return entries


def compare_typescript(data, original, word_fixture, phrase_fixture, tolerance):
    local_words=words_only(data)[len(original['words']):]
    local_arpa=data['arpabet'][len(original['arpabet']):]
    local_phrases=data['entries'][len(original['inputs']):]
    expected_phrases=[p[key] for p in phrase_fixture for key in ('dict','noDict')]
    actual_phrases=[[p['phrase'] for p in parts(row)] for row in local_phrases]
    paths={}
    for label,actual,expected in [('words',local_words,word_fixture['words']),
                                  ('arpabet',local_arpa,word_fixture['arpabet']),
                                  ('phrases',actual_phrases,expected_phrases)]:
        paths[label]=timing.compare(actual,expected,tolerance)[0]
    return paths


def audio_check(artifacts, execute):
    folder=artifacts/'english-audio'
    folder.mkdir()
    case=timing.read(AUDIO_CASE)
    limits=case['measurement']
    settings,trace,files,upper,upper_pcm,ref=voice.capture(
        AUDIO_CASE,limits['host_block_frames'],folder,execute,SUITES,
    )
    plan=timing.read(ref)
    value={**settings,'speech':{'utterances':[{'segments':row['timing']['segments']}
                                              for row in settings['speech']['phrases']]}}
    _,evidence=speech.compare_plans(value,plan,1e-12)
    frames=settings['output_frames']
    a,b=voice.load_trace(trace,frames),voice.load_trace(upper,frames)
    first,state=voice.compare_traces(a,b,{'geometry_absolute_tolerance':limits['geometry_absolute_tolerance'],
                                         'audio_state_peak_relative_tolerance':limits['trace_peak_relative_tolerance']})
    wav,csv=files[0]
    rate,pcm=wavfile.read(wav)
    expected=np.fromfile(upper_pcm,dtype='<f4')
    if pcm.shape!=expected.shape or len(pcm)!=frames or not all(np.isfinite(x).all() for x in (pcm,expected)):
        raise ValueError('英語音声のフレーム数または有限性が基準と異なります')
    delta=abs(pcm.astype('f8')-expected)
    bad=np.flatnonzero(delta>limits['pcm_absolute_tolerance'])
    pitches=[row['pitch'][-1]['targets']['f0_hz'] for row in settings['speech']['phrases']]
    pitch=timing.compare(pitches,limits['pitch_targets_hz'],1e-12)[0]
    stem=folder/'upstream-native'
    native_log=folder/'upstream-native.log'
    text=case['speech_voice']['input']['text']
    execute(['cargo','run','--locked','--release','-p','chimera-cli','--','render','text',str(stem),text,'male','--float'],
            cwd=UPSTREAM,stdout=native_log)
    native_rate,native_wav=wavfile.read(stem.with_suffix('.wav'))
    native_shown=native_log.read_text().splitlines()[0]
    shown=settings['speech']['shown']
    time=settings['speech']['render_end_seconds']-settings['speech']['end_seconds']
    return {
        'checks':{'planned_gestures':evidence['passed'],'trace':first is None,'deterministic_pcm':not bad.size,
                  'expected_shown_pitch_and_tail':shown==limits['expected_summary'] and pitch is None and abs(time-limits['tail_seconds'])<1e-12,
                  'same_host_partition_output':all(sha256(w)==sha256(wav) and sha256(c)==sha256(csv) for w,c in files[1:]),
                  'native_text_cli_shown_and_length':native_rate==rate and len(native_wav)==frames and native_shown==shown,
                  'frames':frames==plan['output_frames']},
        'frames':frames,'shown':shown,'pitch_targets_hz':pitches,'plan':evidence,'first_trace_difference':first,
        'trace_error':state,'pcm_max_abs_error':float(delta.max()),'native_shown':native_shown,
        'pcm_first_frame_over_tolerance':int(bad[0]) if bad.size else None,
    }


def measure(case, artifacts, execute):
    word_fixture=timing.read(FIXTURE/'phonetics-g2p.json')
    phrase_fixture=timing.read(FIXTURE/'phonetics-phrases.json')
    input_=case['english_text']
    cases=[*input_['inputs']]
    for i,phrase in enumerate(phrase_fixture):
        for loaded in (True,False):
            cases.append({'id':f'typescript-{i}-{"dict" if loaded else "rules"}','text':phrase['text'],'dictionary':loaded})
    shaped={**case,'english_text':{'inputs':cases,'words':input_['words']+[row['w'] for row in word_fixture['words']],
                                  'arpabet':input_['arpabet']+[row['p'] for row in word_fixture['arpabet']]}}
    input_path=artifacts/'all-inputs.json'
    input_path.write_text(json.dumps(shaped,ensure_ascii=False,indent=2)+'\n')
    observed,upper=artifacts/'frontend.json',artifacts/'upstream-frontend.json'
    info=artifacts/'settings.json'
    execute([*CLI,'inspect',str(input_path)],stdout=info)
    execute([*CLI,'render',str(input_path),str(observed)])
    d=artifacts/'dictionary.tsv'
    d.write_bytes(gzip.decompress((UPSTREAM/'public/data/cmudict.txt.gz').read_bytes()))
    probe=shared.build_upstream_probe(PROBE,artifacts,execute,extra_libraries=('serde_json',))
    execute([str(probe),str(input_path),str(d)],cwd=UPSTREAM,stdout=upper)
    raw,remote=timing.read(observed),timing.read(upper)
    tolerance=case['measurement']['plan_absolute_tolerance']
    entries=compare_frontend(raw,remote,cases,tolerance)
    fixture_count={ 'words':len(word_fixture['words']),'arpabet':len(word_fixture['arpabet']),'phrases':len(phrase_fixture)}
    fixture_diffs=compare_typescript(raw,input_,word_fixture,phrase_fixture,tolerance)
    word_diff=timing.compare(words_only(raw),remote['words'],tolerance)[0]
    arpa_diff=timing.compare(raw['arpabet'],remote['arpabet'],tolerance)[0]
    single=artifacts/'single-text.json'
    execute([*CLI,'english','Mom? Pop.'],stdout=single)
    example=next(row for row in raw['entries'] if row['id']=='question-fall')
    direct={key:value for key,value in example.items() if key not in ('id','dictionary')}
    checks={
        'dictionary_asset_and_license':sha256(DICT)==sha256(UPSTREAM/'public/data/cmudict.txt.gz')
        and sha256(DICT_LICENSE)==sha256(UPSTREAM/'public/data/CMUDICT-LICENSE.txt')
        and timing.read(info)['dictionary_entries']==case['measurement']['dictionary_entries'],
        'all_frontend_phrases_and_predictions':all(row['passed'] for row in entries),
        'all_upstream_word_and_arpabet_results':word_diff is None and arpa_diff is None,
        'typescript_fixture_exact': not any(fixture_diffs.values())
        and all(case['measurement'][f'typescript_fixture_{key}']==n for key,n in fixture_count.items()),
        'standalone_english_cli':timing.read(single)==direct,
    }
    audio=audio_check(artifacts,execute)
    checks['audio']=all(audio['checks'].values())
    return {'checks':checks,'phrase_count':len(entries),'word_count':len(raw['words']),'arpabet_count':len(raw['arpabet']),
            'typescript_cases':fixture_count,'typescript_first_differences':fixture_diffs,
            'first_word_difference':word_diff,'first_arpabet_difference':arpa_diff,
            'maximum_checked_plan_numeric_difference':max(row['maximum_checked_numeric_error'] for row in entries),
            'first_failed_phrases':[row for row in entries if not row['passed']][:20],
            'audio':audio}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case=timing.read(CASE)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision!=case['upstream_revision'] or subprocess.check_output(
            ['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    inputs=[CASE,AUDIO_CASE,PROBE,voice.PROBE,DICT,DICT_LICENSE,Path(__file__).resolve(),Path(voice.__file__),
            Path(speech.__file__),Path(timing.__file__),Path(shared.__file__),WORKSPACE/'tools/upstream_baseline.py',
            *shared.candidate_sources()]
    references=['public/data/cmudict.txt.gz','public/data/CMUDICT-LICENSE.txt',
                'crates/chimera/tests/golden/phonetics-phrases.json','crates/chimera/tests/golden/phonetics-g2p.json',
                'crates/chimera/src/phonetics/english.rs','crates/chimera/src/phonetics/planner.rs',
                'crates/chimera-cli/src/render.rs']
    manifest={'case_id':case['id'],'upstream_revision':revision,
              'upper_source_sha256':{name:sha256(UPSTREAM/name) for name in references}}
    return shared.record_measurement(args.run_id,CASE,inputs,manifest,
        lambda artifacts,execute:measure(case,artifacts,execute),command=None)


if __name__=='__main__':
    raise SystemExit(main())
