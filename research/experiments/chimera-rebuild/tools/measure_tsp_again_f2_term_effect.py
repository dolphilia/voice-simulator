"""1録音のF2を差し替え、上流TSPの話者集約と診断費用を照合する。"""

import argparse
from collections import defaultdict
from difflib import unified_diff
import gzip
import json
import math
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-again-f2-term-effect.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_again_f2_term_probe.rs'
ALIGNMENT = UPSTREAM / 'tools/tsp/alignment.tsv.gz'
ENTRY = Path('crates/chimera-cli/src/main.rs')


def checked_corpus(settings, archive_config, scratch, *, all_annotated=False):
    cohort = settings['cohort']
    by_speaker = defaultdict(set)
    with gzip.open(ALIGNMENT, 'rt') as stream:
        for line in stream:
            uid, kind, _, _, label = line.rstrip('\n').split('\t')
            if uid[:2] in cohort and kind == 'phone' and (all_annotated or label == 'EH1'):
                by_speaker[uid[:2]].add(uid)
    if any((sorted(by_speaker[speaker]) if all_annotated else sorted(by_speaker[speaker])[:len(ids)]) != ids
           for speaker, ids in cohort.items()):
        raise ValueError('録音IDが事前登録の選び方と一致しません')
    archive = Path(archive_config['archive_path'])
    if archive.stat().st_size != archive_config['archive_bytes'] or sha256(archive) != archive_config['sha256']:
        raise ValueError('外部ディスクのTSP録音アーカイブが登録版と一致しません')
    destination = scratch / 'dataset'
    hashes = {}
    with ZipFile(archive) as source:
        for speaker, ids in cohort.items():
            for uid in ids:
                member = f'48k/{speaker}/{uid}.wav'
                path = destination / member
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as start, path.open('xb') as output:
                    shutil.copyfileobj(start, output)
                hashes[uid] = sha256(path)
    return destination, hashes


def prepare_tsp_probe(scratch, out, execute, probe, command, entry_name, *, cache_path_change=None):
    checkout, archive = scratch / 'upstream', scratch / 'upstream.tar'
    checkout.mkdir()
    execute(['git', 'archive', 'HEAD'], cwd=UPSTREAM, stdout=archive)
    execute(['tar', '-xf', str(archive), '-C', str(checkout)])
    module = checkout / tsp.TSP_SOURCE
    source = module.read_text()
    patched = source
    if cache_path_change is not None:
        old, new = cache_path_change
        if source.count(old) != 1:
            raise ValueError('上流MFAの保存先を1か所に特定できません')
        patched = source.replace(old, new)
    patched += f'\ninclude!("{probe.name}");\n'
    module.write_text(patched)
    shutil.copyfile(probe, module.with_name(probe.name))
    entry = checkout / ENTRY
    main = entry.read_text()
    dispatch = '        ["compare", "tsp", ..]'
    if main.count(dispatch) != 1:
        raise ValueError('上流TSPのCLI入口が1つに定まりません')
    updated = main.replace(dispatch, f'        ["{command}", path] => '
                            f'compare::tsp::{entry_name}(path),\n' + dispatch)
    entry.write_text(updated)
    changes = ((tsp.TSP_SOURCE, source, patched), (ENTRY, main, updated))
    (out / 'probe.patch').write_text(''.join(
        line for name, a, b in changes for line in unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                                               fromfile=f'a/{name}', tofile=f'b/{name}')))
    return checkout


def native_probe(cfg, scratch, out, execute, request, *, collect_only=False):
    old = ('    let home = std::env::var("HOME").map_err(|e| format!("HOME: {e}"))?;\n'
           '    let cache = format!("{home}/.cache/chimera-mfa");')
    new = ('    let cache = std::env::var("CHIMERA_RESEARCH_MFA_CACHE")'
           '.map_err(|e| format!("CHIMERA_RESEARCH_MFA_CACHE: {e}"))?;')
    command, entry = (('research-f2-collect', 'research_tsp_f2_collect') if collect_only
                      else ('research-again-f2', 'research_tsp_again_f2_term'))
    checkout = prepare_tsp_probe(scratch, out, execute, PROBE, command, entry, cache_path_change=(old, new))
    root = Path(cfg['environment_root'])
    model = root / 'downloads/english_us_arpa.zip'
    if sha256(model) != cfg['model_sha256']:
        raise ValueError('MFAの音響モデルが登録版と一致しません')
    cache = scratch / 'mfa-cache'
    acoustic = cache / 'mfa/pretrained_models/acoustic'
    acoustic.mkdir(parents=True)
    (cache / 'env').symlink_to(root / 'env', target_is_directory=True)
    (cache / 'root').symlink_to(root / 'root', target_is_directory=True)
    (acoustic / model.name).symlink_to(model)
    version_path = out / 'mfa-version.txt'
    execute([str(root / 'env/bin/mfa'), 'version'], stdout=version_path)
    if version_path.read_text().strip() != cfg['version']:
        raise ValueError('MFAの版が登録値と一致しません')
    request_path = scratch / 'request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False))
    result = out / 'native.json'
    execute(['/usr/bin/env', f'CHIMERA_RESEARCH_MFA_CACHE={cache}', 'OMP_NUM_THREADS=1', 'OPENBLAS_NUM_THREADS=1',
             'cargo', 'run', '--locked', '--offline', '--release', '--target-dir', str(scratch / 'target'),
             '-p', 'chimera-cli', '--', command, str(request_path)], cwd=checkout, stdout=result)
    return tsp.read(result)


def collect_cohort(case, archive_config, aligner, out, execute, *, female, held=False, all_annotated=False):
    collection = out / 'collection'
    collection.mkdir()
    with TemporaryDirectory(prefix='tsp-f2-train-addition-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        dataset, hashes = checked_corpus(case, archive_config, scratch, all_annotated=all_annotated)
        (collection / 'recordings.json').write_text(json.dumps(
            {'archive_sha256': archive_config['sha256'], 'wav_sha256': hashes}, indent=2) + '\n')
        corpus = {'recordings': sorted(hashes), 'dataset_dir': str(dataset), 'synth_dir': str(scratch / 'synth-mfa'),
                  'female': female, 'held': held}
        return native_probe(aligner, scratch, collection, execute, corpus, collect_only=True)


def speaker_samples(correspondence, speaker, ipa):
    return [(uid, row['slot'], row['recording_f2_hz'])
            for uid, utt in correspondence.items() if utt['speaker'] == speaker
            for row in utt['tokens'] if row['ipa'] == ipa and row['stressed'] and row['recording_f2_hz'] is not None]


def summarize_samples(samples, min_tokens, centre=None, spread=0.07):
    if len(samples) < min_tokens:
        return {'support': len(samples), 'median_hz': None, 'log2_hz': None, 'cost': None}
    frequency = median(samples)
    value = math.log2(frequency)
    cost = max(0, abs(value - centre) / spread - 1) if centre is not None else None
    return {'support': len(samples), 'median_hz': frequency, 'log2_hz': value, 'cost': cost}


def independent_evaluation(settings, native, replacements):
    ipa, target = settings['ipa'], settings['target']
    corr = native['correspondence']
    minimum = settings['minimum_tokens']
    training = {name: summarize_samples([f for _, _, f in speaker_samples(corr, name, ipa)], minimum)
                for name in settings['cohort'] if name != target['speaker']}
    supported = [v['log2_hz'] for v in training.values() if v['log2_hz'] is not None]
    centre = median(supported) if len(supported) >= settings['minimum_training_speakers'] else None
    dev = [value - centre for value in supported] if centre is not None else []
    mad = 1.4826 * median(abs(v - median(dev)) for v in dev) if dev else None
    spread = max(0.07, mad) if mad is not None else 0.07
    samples = speaker_samples(corr, target['speaker'], ipa)
    key = target['utterance'], native['target_slot']
    original, = (f for uid, slot, f in samples if (uid, slot) == key)
    other = [f for uid, slot, f in samples if (uid, slot) != key]
    changes = {'default': original, 'before': replacements[0], 'after': replacements[1], 'missing': None}
    conditions = {name: summarize_samples(other + ([f] if f is not None else []), minimum, centre, spread)
                  for name, f in changes.items()}
    values = [f for _, _, f in samples]
    support_controls = {str(n): summarize_samples(values[:n], minimum, centre, spread) for n in (2, 3)}
    prefix_ids = set(settings['cohort'][target['speaker']][:2])
    prefix = summarize_samples([f for uid, _, f in samples if uid in prefix_ids], minimum, centre, spread)
    return {'training': training, 'reference': [centre, spread, mad], 'conditions': conditions,
            'support_controls': support_controls, 'first_two_recordings': prefix}, changes


def agrees(native, independent, limit):
    return all((native[key] is None if value is None else
                native[key] is not None and abs(native[key] - value) <= limit)
               for key, value in independent.items() if key in native)


def measure(case, paths, archive_config, aligner, out, execute):
    settings = case['measurement']
    target = settings['target']
    sweep = tsp.read(paths['sweep'])
    frequencies = [next(row['f2_hz'] for row in sweep['median_rows'] if row['coefficient'] == coefficient)
                   for coefficient in settings['coefficients']]
    with TemporaryDirectory(prefix='tsp-term-probe-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        dataset, hashes = checked_corpus(settings, archive_config, scratch)
        request = {'recordings': sorted(hashes), 'dataset_dir': str(dataset), 'synth_dir': str(scratch / 'synth-mfa'),
                   'target_id': target['utterance'], 'target_speaker': target['speaker'],
                   'target_interval': target['phone_seconds'], 'replacements_hz': frequencies,
                   'ipa': settings['ipa'], 'term': settings['term']}
        native = native_probe(aligner, scratch, out, execute, request)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    independent, changes = independent_evaluation(settings, native, frequencies)
    (out / 'recordings.json').write_text(json.dumps({'archive_sha256': archive_config['sha256'], 'wav_sha256': hashes},
                                                   indent=2) + '\n')
    limit = settings['tolerance']
    check_reference = (tsp.max_error(independent['reference'], native['reference']) <= limit
                       and all(agrees(native['training'][name], value, limit) for name, value in independent['training'].items()))
    native_conditions = native['conditions']
    check_values = all(agrees(native_conditions[name]['human_term'], value, limit)
                       for name, value in independent['conditions'].items())
    check_controls = (all(agrees(native['support_controls'][name], value, limit)
                          for name, value in independent['support_controls'].items())
                      and agrees(native['first_two_recordings'], independent['first_two_recordings'], limit)
                      and native['four_speaker_reference'][0] is None
                      and all(row['four_training_speakers']['cost'] is None for row in native_conditions.values()))
    baseline = native_conditions['default']
    scored_groups = ('level', 'sibilants', 'timing')
    same_grade = all(row['held_synth_report'] == baseline['held_synth_report']
                     and row['held_human_score_report'] == baseline['held_human_score_report']
                     and all(row['human_term']['groups'][key] == baseline['human_term']['groups'][key]
                             for key in scored_groups)
                     for row in native_conditions.values())
    measured = native['correspondence'][target['utterance']]['tokens'][native['target_slot']]
    checks = {
        'fixed_recordings_and_target_pair': set(hashes) == set(native['correspondence'])
            and hashes[target['utterance']] == sha256(paths['target_wav'])
            and measured['ipa'] == settings['ipa'] and measured['stressed']
            and tsp.max_error(measured['recording_interval'], target['phone_seconds']) <= 1e-6,
        'registered_f2_inputs_and_support_limits': all(row['input_f2_hz'] == changes[name]
            for name, row in native_conditions.items())
            and native['minimum_tokens'] == settings['minimum_tokens']
            and native['minimum_training_speakers'] == settings['minimum_training_speakers'],
        'independent_reference_and_f2_cost': check_reference and check_values,
        'support_and_training_count_controls': check_controls,
    }
    before, after = (independent['conditions'][name]['median_hz'] for name in ('before', 'after'))
    return {'checks': checks, 'predictions': {
                'speaker_median_change_smaller_than_token_change': abs(after - before) < abs(frequencies[1] - frequencies[0]),
                'training_reference_and_scored_groups_unchanged': same_grade and check_reference,
                'two_tokens_leave_f2_cost_missing': native['first_two_recordings']['cost'] is None
                    and native['support_controls']['2']['cost'] is None and native['support_controls']['2']['support'] == 2,
            },
            'independent': independent, 'input_f2_hz': changes,
            'conditions': {name: row['human_term'] for name, row in native_conditions.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('上流の作業用に CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    sweep, prior = (tsp.open_run(case[part], revision) for part in ('sweep', 'alignment_reference'))
    prior_case, prior_snapshot = saved_case(prior, CASE.with_name(case['alignment_reference']['case'] + '.json'))
    archive_case = CASE.with_name(case['archive_case'])
    archive_config = tsp.read(archive_case)['reference']
    uid = case['measurement']['target']['utterance']
    paths = {'sweep': tsp.verified_path(sweep, 'summary.json'),
             'target_wav': tsp.verified_path(prior, f'artifacts/corpus/recording/{uid}/{uid}.wav')}
    sources = (tsp.TSP_SOURCE, ENTRY, 'crates/chimera-cli/src/compare.rs', 'tools/tsp/sentences.tsv',
               prior_case['aligner']['configuration'])
    inputs = [CASE, Path(__file__).resolve(), PROBE, prior_snapshot, archive_case, ALIGNMENT, *paths.values(),
              sweep[0] / 'manifest.json', prior[0] / 'manifest.json', *(UPSTREAM / name for name in sources)]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'aligner': prior_case['aligner']}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, paths, archive_config, prior_case['aligner'], out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
