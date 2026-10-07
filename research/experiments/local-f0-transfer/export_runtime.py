"""固定16係数の非ニューラルbundleと新2文の依存遮断比較を作る。"""
import json
import shutil
import subprocess
import sys
from campaign import LocalBudget, ROOT, RESULT, BUNDLE, PILOT, OLD, EXT, FACT, FRES, REPO, read, save, digest


def collect(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            found.add(value['text'])
        found.update(t for t in value.get('tests', []) if isinstance(t, str))
        for v in value.values():
            found.update(collect(v))
    elif isinstance(value, list):
        for v in value:
            found.update(collect(v))
    return found


def main():
    b = LocalBudget()
    bundle, out = RESULT/'bundle', RESULT/'runtime-audit'
    with b.job('setup', '局所16係数の非ニューラルbundleと未知文を固定', 3_000_000):
        bundle.mkdir(exist_ok=False)
        out.mkdir(exist_ok=False)
        for name in ('acoustics.py', 'acoustic_control.py', 'japanese_frontend.py', 'mei_normal.htsvoice',
                     'LICENSE-HTSVOICE', 'HTS-PROVENANCE.json'):
            shutil.copyfile(BUNDLE/name, bundle/name)
        for name in ('local_control.py', 'local_renderer.py', 'local_hts-v2.dylib', 'runtime.py', 'shim.c'):
            shutil.copyfile(ROOT/name, bundle/name)
        for name in ('direct_non_neural', 'distilled_non_neural'):
            shutil.copyfile(RESULT/'models'/(name+'.json'), bundle/(name+'.json'))
        shutil.copyfile(ROOT/'vendor/HTS_engine.h', bundle/'HTS_engine.h')
        (bundle/'README.md').write_text('# 局所F0の非ニューラル研究版\n\n固定16係数回帰、辞書・アクセント規則、HMMと非ニューラル合成器で入力文から局所F0を計算する。教師音声・ニューラル重み・発話別軌跡を同梱しない。\n\n`runtime.py --text TEXT --model direct_non_neural --pitch-reference 220 --speed 1 --output output.wav`。蒸留回帰は`distilled_non_neural`。1〜120音素、F0参照140〜320、速度0.75〜1.3。局所補正は±3半音、対象音素単純平均の発話内中心化。1実行1生成。\n\n現在はmacOS arm64、固定版pyopenjtalk 0.4.1・既存辞書・NumPy・SciPyで検証。対応版HTSヘッダとBSD通知、Mei音源のCC BY 3.0通知を同梱。Python依存とHTS共有ライブラリは別途必要。品質未認定。内容・自然さの一般保証はない。\n')
        save(bundle/'PROVENANCE.json', {'models_sha256': {n: digest(RESULT/'models'/(n+'.json')) for n in ('direct_non_neural', 'distilled_non_neural')},
            'coefficients_per_model': 16, 'model_size_not_proportional_to_training_texts': True,
            'teacher_audio_included': False, 'neural_weights_included': False, 'per_utterance_lookup': False,
            'training_contract_sha256': digest(RESULT/'training-contract.json'), 'runtime_neural': False})
        files = {p.name: digest(p) for p in bundle.iterdir() if p.is_file()}
        save(bundle/'manifest.json', {'files': files, 'bytes': sum((bundle/n).stat().st_size for n in files),
            'required_runtime': {'pyopenjtalk_version': '0.4.1', 'hts_binary_sha256': read(RESULT/'source-provenance.json')['binary_sha256']},
            'quality_certified': False})
        tests = [{'text': '針が曲がる。', 'pitch_reference': 180., 'speed': .85},
                 {'text': '深い森の中で静かな泉を見つけました。', 'pitch_reference': 260., 'speed': 1.15}]
        known = collect(read(RESULT/'protocol.json'))
        for path in read(RESULT/'protocol.json')['history']:
            known.update(collect(read(REPO/path)))
        assert not {t['text'] for t in tests}&known
        prior = PILOT/'results/nas-pilot-20261002-v1'
        profile = (prior/'hts-runtime-audit-v2/profile.sb').read_text()
        denied = [PILOT, EXT, FACT, ROOT.parent/'acoustic-revision-content-evaluation']
        denied.extend(ROOT.glob('*.py'))
        denied.extend(p for p in RESULT.iterdir() if p not in (bundle, out))
        profile += '\n(deny file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in denied)+')\n'
        (out/'profile.sb').write_text(profile)
        shutil.copyfile(PILOT/'runtime_probe.py', out/'probe.py')
        forbidden = [prior/'teacher/development-00.wav', RESULT/'models/neural.pt',
                     RESULT/'training-inputs/development/development-00.json', ROOT/'local_control.py']
        assert all(p.is_file() for p in forbidden)
        save(out/'probe-inputs.json', {'files': [str(p) for p in forbidden]})
        save(out/'contract.json', {'tests': tests, 'models': ['direct_non_neural', 'distilled_non_neural'],
            'planned_render_calls': 8, 'synthesis_calls_per_run': 1, 'text_collisions': [],
            'profile_sha256': digest(out/'profile.sb'), 'bundle_manifest_sha256': digest(bundle/'manifest.json'),
            'content_evaluation': False, 'quality_certified': False})
    with b.job('audit', '局所bundleの禁止依存・教師・開発資料・ネットワーク拒否を確認', 1_000_000):
        process = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(out/'profile.sb'), sys.executable,
            '-I', str(out/'probe.py'), '--inputs', str(out/'probe-inputs.json')], text=True, capture_output=True, timeout=60)
        save(out/'probe-result.json', {'returncode': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr})
        process.check_returncode()
        assert json.loads(process.stdout)['passed']
    rows = []
    contract = read(out/'contract.json')
    for model in contract['models']:
        for i, test in enumerate(contract['tests']):
            pair = []
            for isolated in (False, True):
                label = f'{model}-{i}-'+('isolated' if isolated else 'normal')
                with b.job('render', '局所bundle単独実行/'+label, 2_000_000):
                    cmd = [sys.executable, '-I', str(bundle/'runtime.py'), '--text', test['text'], '--model', model,
                           '--pitch-reference', str(test['pitch_reference']), '--speed', str(test['speed']),
                           '--output', str(out/(label+'.wav'))]
                    if isolated:
                        cmd = ['/usr/bin/sandbox-exec', '-f', str(out/'profile.sb'), *cmd]
                    process = subprocess.run(cmd, text=True, capture_output=True, timeout=120)
                    save(out/(label+'.json'), {'returncode': process.returncode, 'stdout': process.stdout,
                        'stderr': process.stderr, 'wav_sha256': digest(out/(label+'.wav')) if (out/(label+'.wav')).exists() else None})
                    process.check_returncode()
                    pair.append(json.loads(process.stdout))
            rows.append({'model': model, 'text': test['text'], 'same_float32': pair[0]['sha256_float32'] == pair[1]['sha256_float32'], 'runs': pair})
            print(model, i, '通常・隔離照合完了', flush=True)
    passed = all(r['same_float32'] and all(x['E0_pass'] and not x['forbidden_imports'] and x['synthesis_calls'] == 1 for x in r['runs']) for r in rows)
    save(RESULT/'runtime-audit.json', {'passed': passed, 'rows': rows, 'quality_certified': False,
        'bundle_manifest_sha256': digest(bundle/'manifest.json'), 'content_evaluated': False})
    assert passed


if __name__ == '__main__':
    main()
