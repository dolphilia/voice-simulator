"""単独軸の実行bundleを作り、未知2文の通常・隔離実行を比較する。"""
import json
import shutil
import subprocess
import sys
from campaign import FactorialBudget, ROOT, RESULT, BUNDLE, PILOT, CONTENT, EXT, read, save, digest


def collect_texts(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            found.add(value['text'])
        found.update(t for t in value.get('tests', []) if isinstance(t, str))
        for item in value.values():
            found.update(collect_texts(item))
    elif isinstance(value, list):
        for item in value:
            found.update(collect_texts(item))
    return found


def main():
    budget = FactorialBudget()
    bundle, out = RESULT/'solo-bundle', RESULT/'solo-runtime-audit'
    if not (bundle/'manifest.json').exists():
        with budget.job('setup', '単独軸の非ニューラルbundleと隔離契約を固定', 3_000_000):
            bundle.mkdir(exist_ok=False)
            out.mkdir(exist_ok=False)
            names = ['acoustics.py', 'japanese_frontend.py', 'hts_core.py', 'acoustic_control.py',
                     'mei_normal.htsvoice', 'LICENSE-HTSVOICE', 'HTS-PROVENANCE.json', 'direct_non_neural.json']
            for name in names:
                shutil.copyfile(BUNDLE/name, bundle/name)
            shutil.copyfile(ROOT/'controlled_axes.py', bundle/'controlled_axes.py')
            shutil.copyfile(ROOT/'solo_runtime.py', bundle/'runtime.py')
            (bundle/'README.md').write_text('# 単独軸の非ニューラル研究版\n\n固定20係数回帰とHMMで、任意入力文の解析・校正・初回生成・一回補正を実行する。教師波形、ニューラル重み、発話別設定は同梱しない。\n\n`runtime.py --text TEXT --variant direct_f0_only --pitch-reference 180 --speed 0.85 --output output.wav`。速度単独は`direct_duration_only`。1〜120音素、F0参照140〜320、速度0.75〜1.3。参照F0は相対指定であり絶対F0を保証しない。1実行3生成。Python・NumPy・SciPy・pyopenjtalkと辞書が必要。Mei音源の出典・CC BY 3.0は同梱文書参照。\n\n内容・自然さの資格を得た製品版ではない。\n')
            save(bundle/'PROVENANCE.json', {'original_bundle_manifest_sha256': digest(BUNDLE/'manifest.json'),
                'axis_source_sha256': digest(ROOT/'controlled_axes.py'), 'control_coefficients': 20,
                'teacher_audio_included': False, 'neural_weights_included': False,
                'per_utterance_lookup_included': False, 'runtime_neural': False, 'quality_certified': False})
            files = {p.name: digest(p) for p in bundle.iterdir() if p.is_file()}
            save(bundle/'manifest.json', {'files': files, 'bytes': sum((bundle/n).stat().st_size for n in files)})
            tests = [{'text': '鍵が落ちた。', 'pitch_reference': 180., 'speed': .85},
                     {'text': '丘の上から街全体を見渡しました。', 'pitch_reference': 260., 'speed': 1.15}]
            from campaign import REPO
            protocol = read(RESULT/'protocol.json')
            known = set().union(*(collect_texts(read(REPO/p)) for p in protocol['history']), collect_texts(protocol),
                                collect_texts(read(BUNDLE.parent/'runtime-audit/contract.json')))
            assert not {t['text'] for t in tests}&known
            prior = PILOT/'results/nas-pilot-20261002-v1'
            profile = (prior/'hts-runtime-audit-v2/profile.sb').read_text()
            denied = [PILOT, EXT, CONTENT, ROOT/'preparation-20261003-v1', ROOT/'preparation-20261003-v2']
            denied.extend(ROOT.glob('*.py'))
            denied.extend(p for p in RESULT.iterdir() if p not in (bundle, out))
            profile += '\n(deny file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in denied)+')\n'
            (out/'profile.sb').write_text(profile)
            shutil.copyfile(PILOT/'runtime_probe.py', out/'probe.py')
            forbidden = [prior/'teacher/development-00.wav', BUNDLE.parent/'models/neural_control.pt',
                         BUNDLE.parent/'targets.json', ROOT/'controlled_axes.py']
            assert all(p.is_file() for p in forbidden)
            save(out/'probe-inputs.json', {'files': [str(p) for p in forbidden]})
            save(out/'contract.json', {'tests': tests, 'models': ['direct_f0_only', 'direct_duration_only'],
                'known_text_count': len(known), 'text_collisions': [], 'planned_synthesis_calls': 24,
                'synthesis_calls_per_run': 3, 'profile_sha256': digest(out/'profile.sb'),
                'bundle_manifest_sha256': digest(bundle/'manifest.json'), 'quality_certified': False,
                'no_asr_evaluation': True, 'no_model_or_axis_changes_after_asr': True})
    contract = read(out/'contract.json')
    assert digest(out/'profile.sb') == contract['profile_sha256']
    assert digest(bundle/'manifest.json') == contract['bundle_manifest_sha256']
    probes = [read(p) for p in out.glob('probe-result*.json')]
    probe_passed = any(p['returncode'] == 0 and json.loads(p['stdout'])['passed'] for p in probes)
    if not probe_passed:
        with budget.job('audit', '単独軸の禁止ファイル・依存・ネットワーク遮断を確認', 1_000_000):
            p = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(out/'profile.sb'), sys.executable,
                '-I', str(out/'probe.py'), '--inputs', str(out/'probe-inputs.json')], capture_output=True, text=True, timeout=60)
            save(out/f'probe-result-{len(probes)+1}.json', {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
            p.check_returncode()
            assert json.loads(p.stdout)['passed']
    rows = []
    for variant in contract['models']:
        for i, test in enumerate(contract['tests']):
            pair = []
            for isolated in (False, True):
                label = f'{variant}-{i}-'+('isolated' if isolated else 'normal')
                path = out/(label+'.json')
                if not path.exists():
                    with budget.job('render', '単独軸実行/'+label, 2_000_000, count=3):
                        cmd = [sys.executable, '-I', str(bundle/'runtime.py'), '--text', test['text'],
                               '--variant', variant, '--pitch-reference', str(test['pitch_reference']),
                               '--speed', str(test['speed']), '--output', str(out/(label+'.wav'))]
                        if isolated:
                            cmd = ['/usr/bin/sandbox-exec', '-f', str(out/'profile.sb'), *cmd]
                        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        save(path, {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
                                    'wav_sha256': digest(out/(label+'.wav')) if (out/(label+'.wav')).exists() else None})
                        p.check_returncode()
                record = read(path)
                assert record['returncode'] == 0 and digest(out/(label+'.wav')) == record['wav_sha256']
                pair.append(json.loads(record['stdout']))
            rows.append({'variant': variant, 'text': test['text'],
                         'same_float32': pair[0]['sha256_float32'] == pair[1]['sha256_float32'], 'runs': pair})
            print(variant, i, '通常・隔離の照合完了', flush=True)
    passed = all(r['same_float32'] and all(x['E0_pass'] and not x['forbidden_imports'] and x['synthesis_calls'] == 3 for x in r['runs']) for r in rows)
    save(RESULT/'solo-runtime-audit.json', {'passed': passed, 'rows': rows, 'quality_certified': False,
        'bundle_manifest_sha256': digest(bundle/'manifest.json'), 'content_evaluated': False})
    assert passed


if __name__ == '__main__':
    main()
