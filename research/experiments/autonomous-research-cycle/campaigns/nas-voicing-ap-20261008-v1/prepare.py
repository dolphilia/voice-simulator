"""入力履歴・共有ランタイム・ゲート・ソースを、最初の波形前に固定する。"""
from paths import *
import argparse
import json
import re
import subprocess
import unicodedata


def norm(value):
    return re.sub(r'[\W_]', '', unicodedata.normalize('NFKC', value))


def collect(value, texts, labels):
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            texts.add(norm(value['text']))
        if value.get('full_context_labels'):
            labels.add(tuple(value['full_context_labels']))
        for item in value.values():
            collect(item, texts, labels)
    elif isinstance(value, list):
        for item in value:
            collect(item, texts, labels)


def prepare():
    b = Budget()
    b.recover()
    reg = read(HERE / 'registration.json')
    assert digest(ROOT / 'voicing-ap-candidate-pool-0001.json') == reg['input_pool_sha256']
    with b.job(NAME, 'setup', '入力履歴と共有資産を波形前固定', reserve_bytes=4_000_000) as job:
        bundle = HERE / 'runtime-bundle'
        mapping = {n: SOURCE / n for n in (
            'local_renderer.py', 'local_hts-v2.dylib', 'source_renderer.py', 'counter.dylib', 'counter.c')}
        mapping.update({n: TIMING / n for n in ('timing_engine.py', 'timing.dylib', 'timing.c')})
        mapping.update({n: BUNDLE / n for n in (
            'japanese_frontend.py', 'mei_normal.htsvoice', 'acoustics.py', 'LICENSE-HTSVOICE')})
        mapping.update({n: HERE / n for n in ('runtime.py', 'runtime_batch.py', 'controls.py', 'voicing_world.py')})
        mapping['calibration.py'] = ROOT / 'absolute-f0-preparation-0002.py'
        mapping['world_renderer2.py'] = WORLD / 'world_renderer2.py'
        mapping['LICENSE-WORLD.txt'] = WORLD / 'upstream/LICENSE-WORLD.txt'
        for path in (WORLD / 'packages-v2').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                mapping['packages-v2/' + str(path.relative_to(WORLD / 'packages-v2'))] = path
        for name, source in mapping.items():
            b.write(bundle / name, source.read_bytes(), job)
        b.save(bundle / 'manifest.json', dict(files={n: digest(bundle / n) for n in mapping},
            shared_assets=True, final_non_neural=True, utterance_tables=0,
            waveform_lookup=0, neural_model=0, quality_certified=False), job)
    # 初期化前に外部TMPを指定した子で辞書による入力照合を行う。
    with b.job(NAME, 'setup', '新入力16の非衝突・ラベル上限確認', reserve_bytes=12_000_000) as job:
        with b.workspace(job, '辞書初期化と入力履歴の照合') as (work, env):
            result = subprocess.run([str(PYTHON), '-B', str(HERE / 'prepare.py'), '--inputs'],
                env=env, text=True, stdout=subprocess.PIPE, check=True)
        value = json.loads(result.stdout)
        b.save(HERE / 'novelty-audit.json', value['audit'], job)
        b.save(HERE / 'protocol.json', dict(registration_sha256=digest(HERE / 'registration.json'),
            rows=value['rows'], variants=reg['variants'], conditions=reg['conditions'],
            expected_records=160, protected_confirmation_opened=False,
            no_optimization_after_first_audio=True, quality_certified=False), job)
        b.save(HERE / 'engine-contract.json', read(PREVIOUS / 'engine-contract.json'), job)
    sources = sorted(p for p in HERE.glob('*.py'))
    with b.job(NAME, 'setup', '実行契約・固定一時方針を波形前封印', reserve_bytes=200_000) as job:
        b.save(HERE / 'execution-contract.json', dict(
            protocol_sha256=digest(HERE / 'protocol.json'),
            registration_sha256=digest(HERE / 'registration.json'),
            source_hashes={p.name: digest(p) for p in sources},
            runtime_manifest_sha256=digest(bundle / 'manifest.json'),
            engine_contract_sha256=digest(HERE / 'engine-contract.json'),
            output_gain=.25, native_half_tone='12*log2(requestedHz/220)',
            absolute_calibration='補完後の有声LF0へ一律log偏移、原有声相対輪郭保持',
            fill_rule=reg['voicing_rule'], AP_rule=reg['AP_rule'],
            factor_baseline_byte_exact=True, source_AP_commit=reg['AP_source_commit'],
            waveform_transfer='pipe/メモリ。子の一時音声ファイルなし。',
            tmp_maximum_bytes=8_000_000, tmp_maximum_write_bytes=16_000_000,
            fixed_before_first_wave=True, quality_certified=False), job)
    print('入力16・共有bundle・生成前契約の固定完了', flush=True)
    print(b.reconcile(), flush=True)


def inputs():
    import os
    import sys
    import tempfile
    assert Path(tempfile.gettempdir()).resolve() == Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0, str(HERE / 'runtime-bundle'))
    from japanese_frontend import analyze
    import pyopenjtalk
    history = dict(read(PREVIOUS / 'novelty-audit.json')['history_reference_hashes'])
    for directory in (ROOT / 'campaigns').iterdir():
        if directory == HERE:
            continue
        for name in ['protocol.json']:
            path = directory / name
            if path.exists():
                history[str(path.relative_to(REPO))] = digest(path)
    for name in ['protocol.json', 'novelty-audit.json']:
        path = PREVIOUS / name
        history[str(path.relative_to(REPO))] = digest(path)
    texts, labels = set(), set()
    for name, expected in history.items():
        assert not re.search('splits|protected|holdout|final-confirm', name, re.I)
        assert digest(REPO / name) == expected, name
        collect(read(REPO / name), texts, labels)
    pool = read(ROOT / 'voicing-ap-candidate-pool-0001.json')
    rows, audit = [], []
    for length in ['short', 'long']:
        selected = []
        for text in pool['candidate_pool_' + length]:
            row = analyze(text)
            collision = norm(text) in texts or tuple(row['full_context_labels']) in labels
            valid = 3 <= len(row['full_context_labels']) <= 122
            chosen = not collision and valid and len(selected) < 8
            audit.append(dict(text=text, length=length, collision=collision,
                label_count=len(row['full_context_labels']), selected=chosen))
            if chosen:
                selected.append(row)
                texts.add(norm(text))
                labels.add(tuple(row['full_context_labels']))
        assert len(selected) == 8, '生成前に入力不足で停止'
        for group, row in enumerate(selected):
            row.update(id='vap-fresh-' + str(len(rows)).zfill(2), length=length,
                challenge_group=group, cohort='prospective_once', kana=pyopenjtalk.g2p(row['text'], kana=True))
            rows.append(row)
    print(json.dumps(dict(rows=rows, audit=dict(history_reference_hashes=history,
        pool_checked_before_output=audit, selected_rows=[dict(id=r['id'], text=r['text'], kana=r['kana'])
        for r in rows], protected_confirmation_opened=False, final_quality_independence_claim=False)),
        ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', action='store_true')
    args = parser.parse_args()
    inputs() if args.inputs else prepare()
