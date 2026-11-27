"""英語の歌詞・歌唱音符・母音と子音の時刻を固定上流と独立計算に照合する。"""

import argparse
import gzip
import json
from pathlib import Path
import re
import subprocess

import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE/'cases/song-plan.json'
PROBE = WORKSPACE/'tools/upstream_song_probe.rs'
GOLDEN = UPSTREAM/'crates/chimera/tests/golden/phonetics-syllables.json'
DICT = WORKSPACE/'data/cmudict.txt.gz'
CLI = ['cargo','run','--locked','--release','-p','vocal-cli','--']


def augment(case, fixture):
    source = case['song_plan']
    extras = [{'id':f'golden-{i}-{mode}','text':row['text'],'dictionary':mode=='dict'}
              for i,row in enumerate(fixture['lyrics']) for mode in ('dict','noDict')]
    return {**case,'song_plan':{**source,'lyric_cases':source['lyric_cases']+extras,
                              'spelling_cases':[{k:row[k] for k in ('word','n')} for row in fixture['spelling']],
                              'syllable_words':[row['w'] for row in fixture['syllabify']]}}


def segments(plan):
    result = []
    for phrase in plan['phrases']:
        for item in phrase['timing']['segments']:
            row = {'ipa':item['segment']['ipa'], 'kind':item['manner'] or '?',
                   't0':item['start_seconds'], 't1':item['end_seconds']}
            if row['kind']=='vowel':
                row['stress'] = item['segment'].get('stress',0)
            result.append(row)
    return result


def compare_score(candidate, upper, case, limits):
    tolerance = limits['seconds_and_pitch_tolerance']
    plan = candidate['plan']
    output_segments = segments(plan)
    pitch = [{**g,'targets':{'f0':g['targets']['f0_hz']}} for p in plan['phrases'] for g in p['pitch']]
    observed = {'id':candidate['id'],'syllables':candidate['syllables'],'segments':output_segments,'pitch':pitch,
                'end':plan['end_seconds']}
    upper_difference, error = timing.compare(observed,upper,tolerance)
    notes = plan['notes']
    expected = case['expected']
    registered_items = {
        'nucleus_seconds':[n['nucleus_start_seconds'] for n in notes],
        'phrase_ends_seconds':[p['timing']['end_seconds'] for p in plan['phrases']],
        'segments':[[s['ipa'],s['t0'],s['t1']] for s in output_segments],
        'lyric_indices':[n['lyric_index'] for n in notes],
    }
    exact = {k:v for k,v in expected.items() if k in registered_items}
    prediction, _ = timing.compare({k:registered_items[k] for k in exact},exact,tolerance)
    # 拍は累積秒ではなく、拍数の合計から直接求める。
    offsets = [case['start_seconds']+60/case['bpm']*sum(n['beats'] for n in case['notes'][:i])
               for i in range(len(notes)+1)]
    hz = [limits['pitch_reference_hz']*2**((n['midi']-69)/12) for n in case['notes']]
    independent_reference = {'spans':list(map(list,zip(offsets[:-1],offsets[1:],strict=True))),'hz':hz,
                             'nominal_end':offsets[-1]}
    independent = {'spans':[[n['beat_seconds'],n['beat_end_seconds']] for n in notes],
                   'hz':[n['f0_hz'] for n in notes],'nominal_end':plan['nominal_end_seconds']}
    independent_difference, numeric = timing.compare(independent,independent_reference,tolerance)
    nucleus_lengths = [n['nucleus_end_seconds']-n['nucleus_start_seconds'] for n in notes]
    delays = [n['nucleus_start_seconds']-n['beat_seconds'] for n in notes]
    lower_limit = expected.get('minimum_nucleus_seconds')
    constrained = lower_limit is None or (min(nucleus_lengths)>=lower_limit-tolerance
                                           and max(delays)<=limits['maximum_fast_accumulated_delay_seconds'])
    return {'id':candidate['id'],'first_upstream_difference':upper_difference,'upstream_numeric_error':error,
            'first_registered_difference':prediction,'independent_beat_and_f0_difference':independent_difference,
            'independent_numeric_error':numeric,'nucleus_delay_seconds':delays,'nucleus_durations_seconds':nucleus_lengths,
            'segments':len(output_segments),'unavailable_speech_symbols':plan['unavailable_speech_symbols'],
            'passed':upper_difference is None and prediction is None and independent_difference is None and constrained
            and abs(plan['render_end_seconds']-plan['end_seconds']-.4)<=tolerance}


def registered_lyrics(observed, inputs):
    for line, sample in zip(observed,inputs):
        syllables = line['syllables']
        if 'expected' in sample:
            actual = [{**{k:s[k] for k in ('text','wordEnd','phraseEnd')},
                       'onset':[p['ipa'] for p in s['onset']], 'nucleus':s['nucleus']['ipa'],
                       'coda':[p['ipa'] for p in s['coda']]} for s in syllables]
            diff, _ = timing.compare(actual,sample['expected'],0.)
            if diff is not None:
                return {'id':sample['id'],'difference':diff}
        if 'expected_melismas' in sample:
            marked = [i for i,s in enumerate(syllables) if s.get('melisma')]
            if marked!=sample['expected_melismas']:
                return {'id':sample['id'],'melismas':marked}
    return None


def measure(case, artifacts, execute):
    fixture = timing.read(GOLDEN)
    source = augment(case,fixture)
    case_path = artifacts/'all-inputs.json'
    case_path.write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
    dict_path = artifacts/'dictionary.tsv'
    dict_path.write_bytes(gzip.decompress(DICT.read_bytes()))
    local = artifacts/'candidate.json'
    inspection = artifacts/'inspect.json'
    upper = artifacts/'upstream.json'
    execute([*CLI,'inspect',str(case_path)],stdout=inspection)
    execute([*CLI,'render',str(case_path),str(local)])
    execute(['cargo','test','--locked','-p','chimera','--test','sing_fast','--test','rising','--test','golden_phonetics_text'],
            cwd=UPSTREAM,stdout=artifacts/'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE,artifacts,execute,extra_libraries=('serde_json',))
    execute([str(probe),str(case_path),str(dict_path)],cwd=UPSTREAM,stdout=upper)
    candidate, baseline = timing.read(local),timing.read(upper)
    limits = case['measurement']
    reports = [compare_score(a,b,c,limits) for a,b,c in zip(candidate['scores'],baseline['scores'],
                                                          case['song_plan']['scores'],strict=True)]
    nregistered = len(case['song_plan']['lyric_cases'])
    fixture_lyrics = [row[mode] for row in fixture['lyrics'] for mode in ('dict','noDict')]
    observed_lyrics = [row['syllables'] for row in candidate['lyric_cases'][nregistered:]]
    groups = {'lyric_cases':(observed_lyrics,fixture_lyrics),
              'spellings':(candidate['spelling_cases'],fixture['spelling']),
              'words':(candidate['syllable_words'],fixture['syllabify'])}
    compared = {k:len(a) for k,(a,_) in groups.items()}
    diffs = {k:timing.compare(a,b,0.)[0] for k,(a,b) in groups.items()}
    upstream_lyrics = {k:timing.compare(candidate[k],baseline[k],0.)[0] for k in
                       ('lyric_cases','spelling_cases','syllable_words')}
    predictions = registered_lyrics(candidate['lyric_cases'],case['song_plan']['lyric_cases'])
    return {'checks':{'same_inspect_and_render':sha256(inspection)==sha256(local),
                      'score_timing_and_targets':all(row['passed'] for row in reports),
                      'lyrics_against_upstream_rust':all(v is None for v in upstream_lyrics.values()),
                      'typescript_lyrics_spelling_syllables':all(v is None for v in diffs.values())
                      and compared==limits['expected_golden_counts'], 'registered_lyrics':predictions is None,
                      'same_fixed_dictionary':sha256(DICT)==sha256(UPSTREAM/'public/data/cmudict.txt.gz')},
            'score_cases':reports,'fixture_counts':compared,'fixture_differences':diffs,
            'upstream_frontend_differences':upstream_lyrics,'registered_lyrics_difference':predictions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = timing.read(CASE)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision!=case['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [CASE,PROBE,Path(__file__).resolve(),Path(timing.__file__),Path(shared.__file__),
               WORKSPACE/'tools/upstream_baseline.py',DICT,DICT.with_name('CMUDICT-LICENSE.txt'),*shared.candidate_sources()]
    upstream_files = ['src/phonetics/sing.rs','src/phonetics/syllables.rs','src/phonetics/planner.rs',
                      'src/phonetics/inventory.rs','src/math.rs','tests/sing_fast.rs','tests/rising.rs',
                      'tests/golden/phonetics-syllables.json']
    meta = {'case_id':case['id'],'upstream_revision':revision,
            'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera'/name) for name in upstream_files}}
    return shared.record_measurement(args.run_id,CASE,sources,meta,lambda artifacts,execute:measure(case,artifacts,execute),command=None)


if __name__=='__main__':
    raise SystemExit(main())
