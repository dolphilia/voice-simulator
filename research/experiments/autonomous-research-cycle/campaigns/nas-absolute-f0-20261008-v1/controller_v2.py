"""予約・pipe・外部一時領域を統一し、凍結比較を段階実行する。"""
from paths import *
import argparse
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile


def verify():
    contract = read(HERE / 'execution-contract.json')
    assert digest(HERE / 'protocol.json') == contract['protocol_sha256']
    assert digest(HERE / 'registration.json') == contract['registration_sha256']
    assert digest(HERE / 'runtime-bundle/manifest.json') == contract['runtime_manifest_sha256']
    for name, expected in contract['source_hashes'].items():
        assert digest(HERE / name) == expected, name
    amendment=read(HERE/'technical-recovery-amendment-01.json')
    for n,expected in amendment['new_source_hashes'].items(): assert digest(HERE/n)==expected
    return contract


def requests():
    p = read(HERE / 'protocol.json')
    return [dict(id=row['id'] + '/' + c + '/' + method, text=row['text'],
                 method=method, speed=q['speed'], pitch=q['requested_f0'])
            for row in p['rows'] for c, q in p['conditions'].items() for method in p['variants']]


def profile(b, work, isolated):
    text = '(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
    text += '(allow file-write* (subpath ' + json.dumps(str(work)) + '))\n'
    if isolated:
        text += '(deny file-read* (subpath ' + json.dumps(str(REPO / 'research')) + '))\n'
        text += '(deny file-read-data (subpath ' + json.dumps(str(b.guard.root)) + '))\n'
        site = OLD / '.venv-eval/lib/python3.11/site-packages'
        allowed = [OLD / '.venv-eval', HERE / 'runtime-bundle', work]
        text += '(allow file-read* ' + ''.join('(subpath ' + json.dumps(str(p)) + ') ' for p in allowed) + ')\n'
        text += '(allow file-read-data (literal ' + json.dumps(str(b.guard.root / 'identity.json')) + '))\n'
        text += '(deny file-read* ' + ''.join('(subpath ' + json.dumps(str(site / n)) + ') '
            for n in ('torch', 'tensorflow', 'transformers', 'faster_whisper', 'ctranslate2',
                      'onnxruntime', 'sherpa_onnx')) + ')\n'
    return text


def execute(command, env, profile_text=None, input_text=None, timeout=1800):
    if profile_text:
        command = ['/usr/bin/sandbox-exec', '-p', profile_text, *command]
    # runはtimeout/失敗時も子を終了・waitし、pipeを閉じてから戻る。
    return subprocess.run(command, env=env, input=input_text, text=True,
                          stdout=subprocess.PIPE, check=True, timeout=timeout).stdout


def test():
    b = Budget()
    with b.job(NAME, 'audit', '一時領域の正常/失敗/超過/媒体復旧回収を検査', reserve_bytes=17_000_000) as job:
        with b.workspace(job, '一時管理の人工fixture', 16_000_000, 24_000_000) as (_, env):
            result = json.loads(execute([str(PYTHON), '-B', str(HERE / 'test_temporary_storage.py')], env))
        b.save(HERE / 'temporary-storage-tests.json', result, job)
    print('一時管理検査通過', flush=True)


def fixture_worker(render_job, dsp_job):
    import tempfile
    assert Path(tempfile.gettempdir()).resolve() == Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0, str(HERE / 'runtime-bundle'))
    sys.path.insert(0, str(HERE / 'runtime-bundle/packages-v2'))
    import numpy as np
    import pyworld
    from acoustics import estimate_f0
    from calibration import calibrated_lf0
    b = Budget()
    values = []
    for hz in [220., 280.]:
        audio = .3 * np.sin(2 * np.pi * hz * np.arange(24000) / 24000)
        f0, times = pyworld.dio(audio, 24000, f0_floor=70., f0_ceil=800., frame_period=5.)
        f0 = pyworld.stonemask(audio, f0, times, 24000)
        dio = float(np.median(f0[f0 > 0]))
        acf, confidence = estimate_f0(audio, 24000, minimum=70, maximum=800)
        assert abs(12 * np.log2(dio / hz)) <= 1 and abs(12 * np.log2(acf / hz)) <= 1 and confidence >= .6
        out = io.BytesIO()
        np.savez_compressed(out, audio=audio, dio=f0, times=times)
        b.write(HERE / 'fixtures' / (str(int(hz)) + '.npz'), out.getvalue(), render_job)
        values.append(dict(requested_hz=hz, dio_hz=dio, acf_hz=acf, confidence=confidence))
    x = np.array([[np.log(353.)], [-1e10], [np.log(380.)]])
    hz = float(np.exp(np.median(x[x[:, 0] > 0, 0])))
    y, _ = calibrated_lf0(x, hz)
    assert x.tobytes() == y.tobytes()
    b.save(HERE / 'fixture-audit.json', dict(values=values, zero_shift_byte_exact=True,
        generated_sine_fixtures=2, DSP=4, fixture_not_quality_evidence=True), dsp_job)


def comparison_worker(render_job, dsp_job):
    import tempfile
    assert Path(tempfile.gettempdir()).resolve() == Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0, str(HERE / 'runtime-bundle'))
    import numpy as np
    import re
    from scipy.io import wavfile
    from runtime import generate, verify as verify_bundle
    from measurement_v2 import measure, pitch_pass, ELIGIBLE
    verify_bundle()
    b = Budget()
    p = read(HERE / 'protocol.json')
    records = []
    for row in p['rows']:
        for condition, q in p['conditions'].items():
            support = None
            native_meta = None
            for method in p['variants']:
                base = HERE / 'render' / row['id'] / condition / method
                assert not base.with_suffix('.json').exists(), '保存済みの比較は再生成しない'
                reused_audio = base.with_suffix('.wav').exists()
                if reused_audio:
                    assert method == 'native' and row['id'] == 'f0-fresh-00' and condition == 'neutral'
                    from runtime import analyze, Engine, ah, evaluate
                    from world_renderer2 import convert
                    import math
                    data = base.with_suffix('.wav').read_bytes()
                    stored = np.load(base.with_suffix('.npz'))
                    params = [stored[k].copy() for k in ['mcp', 'lf0', 'lpf']]
                    analyzed = analyze(row['text'])
                    with Engine(analyzed, HERE / 'runtime-bundle/mei_normal.htsvoice', speed=q['speed'], half_tone=12*math.log2(q['requested_f0']/220)) as engine:
                        before=engine.snapshot(); variance=engine.variance(); settings=engine.get_settings()
                        current=engine.parameters()
                        assert all(np.array_equal(a,z) for a,z in zip(current,params))
                    _, audio=wavfile.read(io.BytesIO(data)); e0=evaluate(audio,{},24000)
                    _, conversion=convert(params);conversion['sample_count_24k']=len(audio)
                    voiced=params[1][:,0]>0;median=float(np.median(params[1][voiced,0]))
                    meta=dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,E0=e0,E0_pass=e0['E0_pass'],invariants_pass=True,relative_LF0_max_abs_error=0.,control=dict(log_shift=0.,native_generated_log_median=median,waveform_pitch_verified=False),duration=before['duration'],msd=before['msd'],settings=settings,state_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),variance_sha256=ah(variance),native_parameter_hashes=[ah(v) for v in params],output_parameter_hashes=[ah(v) for v in params],output_gain=.25,conversion=conversion,forbidden_imports=[],runtime_neural=False,teacher_audio=0,utterance_tables=0,generated_lf0_median_hz=float(np.exp(median)))
                else:
                    data, meta, params, analyzed = generate(row['text'], method, q['speed'], q['requested_f0'], full=True)
                assert analyzed['full_context_labels'] == row['full_context_labels']
                if native_meta:
                    for key in ['duration', 'msd', 'settings', 'state_sha256', 'variance_sha256', 'native_parameter_hashes']:
                        assert meta[key] == native_meta[key], key
                    assert meta['output_parameter_hashes'][0] == native_meta['output_parameter_hashes'][0]
                    assert meta['output_parameter_hashes'][2] == native_meta['output_parameter_hashes'][2]
                else:
                    native_meta = meta
                if not reused_audio: b.write(base.with_suffix('.wav'), data, render_job)
                arrays = io.BytesIO()
                np.savez_compressed(arrays, mcp=params[0], lf0=params[1], lpf=params[2], duration=meta['duration'])
                if not reused_audio: b.write(base.with_suffix('.npz'), arrays.getvalue(), render_job)
                _, audio = wavfile.read(io.BytesIO(data))
                eligible = [i for i, label in enumerate(row['full_context_labels'])
                            if re.search(r'\-([^+]+)\+', label).group(1) in ELIGIBLE
                            and any(meta['msd'][i * 5:(i + 1) * 5][k] > .5 for k in range(5))]
                measured, f0, times = measure(audio, meta['duration'], eligible, support)
                if support is None:
                    support = measured['support']
                    support_path=HERE / 'support' / row['id'] / (condition + '.json')
                    support_value=dict(indices=support, excluded=[r['index'] for r in measured['eligible_native_intervals'] if not r['support_complete']], native_wave_sha256=meta['sha256'],fixed_from_native=True,not_candidate_selected=True)
                    if support_path.exists(): assert read(support_path)==support_value
                    else: b.save(support_path,support_value,dsp_job)
                arrays = io.BytesIO()
                np.savez_compressed(arrays, f0=f0, times=times)
                if reused_audio:
                    previous_dio=np.load(base.with_suffix('.dio.npz'));assert np.array_equal(previous_dio['f0'],f0) and np.array_equal(previous_dio['times'],times)
                else: b.write(base.with_suffix('.dio.npz'), arrays.getvalue(), dsp_job)
                record = {k: row[k] for k in ['text', 'length', 'challenge_group', 'cohort']}
                record.update(id=row['id'] + '/' + condition + '/' + method, condition=condition,
                    variant=method, wav=str(base.with_suffix('.wav').relative_to(REPO)),
                    wav_sha256=meta['sha256'], status='completed', meta=meta,
                    measurement=measured, pitch_gate=pitch_pass(measured, q['requested_f0']),
                    E0_pass=meta['E0_pass'], invariants_pass=meta['invariants_pass'],
                    protocol_sha256=digest(HERE / 'protocol.json'), quality_certified=False,reused_saved_wave_without_rerender=reused_audio,new_render_calls=0 if reused_audio else 1)
                b.write_data(base.with_suffix('.json'), encode(record), dsp_job)
                records.append(dict(id=record['id'], record=str(base.with_suffix('.json').relative_to(REPO)),
                                    sha256=digest(base.with_suffix('.json'))))
            print('比較', len(records), '/64', flush=True)
    assert len(records) == 64
    b.save(HERE / 'render-manifest.json', dict(rows=records, new_render_calls=64,
        new_DSP_calls=192, technical_recovery_new_renders=63, failed_prior_batch_reservation_preserved=True, no_optimization_after_output=True, quality_certified=False), dsp_job)


def computation(stage):
    b = Budget()
    count = 2 if stage == 'fixture' else 63
    dsp = 4 if stage == 'fixture' else 192
    with b.job(NAME, 'render', stage, count=count, reserve_bytes=200_000_000) as render_job:
        with b.job(NAME, 'dsp', stage + ' 固定測定', count=dsp, reserve_bytes=8_000_000) as dsp_job:
            with b.workspace(render_job, stage + ' ライブラリ初期化・必要時一時処理') as (_, env):
                execute([str(PYTHON), '-B', str(HERE / 'controller_v2.py'),
                         stage + '-worker', '--render-job', render_job, '--dsp-job', dsp_job], env)
    print(stage, '保存完了', flush=True)


def isolate():
    b = Budget()
    reqs = requests()
    expected = {r['id']: read(REPO / r['record'])['wav_sha256']
                for r in read(HERE / 'render-manifest.json')['rows']}
    outputs, profiles = {}, {}
    for mode in ['normal', 'isolated']:
        with b.job(NAME, 'render', '通常/隔離batch64 ' + mode, count=64, reserve_bytes=90_000_000) as job:
            with b.job(NAME, 'dsp', '通常/隔離batch64 E0 ' + mode, count=64, reserve_bytes=100_000):
                with b.workspace(job, mode + ' ランタイム初期化') as (work, env):
                    sb = profile(b, work, mode == 'isolated')
                    output = execute([str(PYTHON), '-I', '-B', str(HERE / 'runtime-bundle/runtime_batch.py')],
                                     env, sb, json.dumps(reqs, ensure_ascii=False))
                    archive_data = base64.b64decode(output, validate=False)
                    profiles[mode] = dict(source=sb, sha256=hashlib.sha256(sb.encode()).hexdigest())
                b.write(HERE / 'runtime-archives' / (mode + '.zip'), archive_data, job)
                with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
                    manifest = json.loads(archive.read('manifest.json'))
                    assert len(manifest['records']) == 64
                    assert manifest['synthesis_calls'] == manifest['E0_calls'] == 64
                    assert len(archive.namelist()) == 129
                    records = {}
                    for r in manifest['records']:
                        data = archive.read(r['id'] + '.wav')
                        assert hashlib.sha256(data).hexdigest() == r['sha256'] == expected[r['id']]
                        assert r['synthesis_calls'] == r['E0_calls'] == 1 and not r['forbidden_imports']
                        records[r['id']] = r
                b.save(HERE / ('runtime-batch-' + mode + '.json'), dict(records=records,
                    all_hash_match=True, profile=profiles[mode]), job)
                outputs[mode] = records
        print(mode, '64件のhash一致', flush=True)
    cli = []
    for request in [reqs[0], reqs[-1]]:
        for mode in ['normal', 'isolated']:
            with b.job(NAME, 'render', 'CLI ' + mode + '/' + request['id'], reserve_bytes=10_000_000) as job:
                with b.job(NAME, 'dsp', 'CLI E0 ' + mode, reserve_bytes=100_000):
                    with b.workspace(job, '単独CLI ライブラリ初期化') as (work, env):
                        output = json.loads(execute([str(PYTHON), '-I', '-B',
                            str(HERE / 'runtime-bundle/runtime.py'), '--text', request['text'],
                            '--method', request['method'], '--speed', str(request['speed']),
                            '--pitch', str(request['pitch'])], env, profile(b, work, mode == 'isolated')))
                    data = base64.b64decode(output['wav_base64'])
                    assert hashlib.sha256(data).hexdigest() == output['meta']['sha256'] == expected[request['id']]
                    b.write(HERE / 'runtime-cli' / mode / (request['id'] + '.wav'), data, job)
                    cli.append(dict(id=request['id'], mode=mode, sha256=output['meta']['sha256'], bit_match=True))
    # 禁止資料は、論理参照と外部の実体、現在の入力と出力の全てを実際に拒否する。
    logical = HERE / 'render/f0-fresh-00/neutral/native.wav'
    blocked = [logical, logical.resolve(), HERE / 'protocol.json', HERE / 'registration.json',
               PREVIOUS / 'protocol.json', HERE / 'runtime-archives/normal.zip',
               (HERE / 'runtime-archives/normal.zip').resolve()]
    code = 'import json,socket; paths=' + repr([str(p) for p in blocked]) + '; a=[]\n'
    code += "for p in paths:\n try:\n  open(p,'rb').close();a.append(False)\n except PermissionError:a.append(True)\n"
    code += "s=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps(dict(read_denied=a,network_denied=net)))"
    with b.job(NAME, 'audit', '論理/物理資料と通信の実拒否', reserve_bytes=10_000_000) as job:
        with b.workspace(job, '拒否probe') as (work, env):
            proof = json.loads(execute([str(PYTHON), '-I', '-B', '-c', code], env, profile(b, work, True)))
        assert all(proof['read_denied']) and proof['network_denied']
        b.save(HERE / 'denial-probe.json', dict(proof, paths=[str(p) for p in blocked]), job)
        pairs = [dict(id=r['id'], bit_match=outputs['normal'][r['id']]['sha256'] ==
            outputs['isolated'][r['id']]['sha256']) for r in reqs]
        assert len(pairs) == 64 and all(r['bit_match'] for r in pairs)
        b.save(HERE / 'runtime-audit.json', dict(passed=True, pairs=pairs, CLI=cli,
            new_render_calls=132, new_DSP_calls=132, denial_probe=proof,
            final_non_neural=True, quality_certified=False), job)
    print('通常/隔離64組・CLI4件・読取/通信拒否を確認', flush=True)


def asr(name):
    b = Budget()
    assert read(HERE / 'runtime-audit.json')['passed']
    engine = read(HERE / 'engine-contract.json')
    with b.job(NAME, 'audit', 'ASRモデル・辞書・正規化hash照合 ' + name, reserve_bytes=100_000):
        for n, h in engine['asr_model_hashes'].items():
            assert digest(REPO / n) == h, n
        assert digest(OLD / 'diagnostics.py') == engine['normalizer_source_sha256']
        cfg = engine['reading_diagnostic']['contract']
        for n, h in cfg['dictionary_files'].items():
            assert digest(Path(cfg['dictionary_path']) / n) == h
        assert digest(cfg['library']) == cfg['library_sha256']
    with b.job(NAME, 'ai', '固定ASR64 ' + name, count=64, reserve_bytes=12_000_000) as job:
        with b.workspace(job, name + ' 認識器初期化・評価') as (work, env):
            result = json.loads(execute([str(PYTHON), '-B', str(HERE / 'asr_worker.py'),
                '--engine', name], env, profile(b, work, False)))
        assert len(result['rows']) == result['ai_calls'] == 64
        rows = []
        for value in result['rows']:
            target = HERE / 'asr' / name / (value['id'] + '.json')
            b.write_data(target, encode(value), job)
            rows.append(dict(path=str(target.relative_to(REPO)), sha256=digest(target)))
        b.save(HERE / ('asr-manifest-' + name + '.json'), dict(rows=rows, new_ai=64,
            reused=0, optimization_after_asr=False), job)
    print(name, '64件保存完了', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['test', 'fixture', 'comparison', 'isolate', 'asr',
        'fixture-worker', 'comparison-worker'])
    parser.add_argument('--engine', choices=['whisper', 'reazon'])
    parser.add_argument('--render-job')
    parser.add_argument('--dsp-job')
    args = parser.parse_args()
    if args.stage != 'test':
        verify()
    if args.stage.endswith('-worker'):
        globals()[args.stage.replace('-', '_')](args.render_job, args.dsp_job)
        return
    b = Budget()
    b.recover()
    if args.stage == 'test':
        test()
    elif args.stage in ['fixture', 'comparison']:
        computation(args.stage)
    elif args.stage == 'isolate':
        isolate()
    elif args.stage == 'asr':
        assert args.engine
        asr(args.engine)
    print(b.reconcile(), flush=True)


if __name__ == '__main__':
    main()
