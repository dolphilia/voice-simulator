"""自分の外部一時出力の限定read-data許可で隔離工程だけを再開する。"""
import argparse,ast,json,os
from pathlib import Path
import waveguide_sequence_runtime_20261008 as m
from budget import read,digest
from long_horizon_budget import LongHorizonBudget as Budget
ROOT,HERE,NAME=m.ROOT,m.HERE,m.NAME

def strict(b,work):
    # file-read*の許可を、親の具体的file-read-data拒否より明示的に限定する。
    text=m.profile(b,work,True)+'(allow file-read-data (subpath '+json.dumps(str(work))+'))\n'
    assert '(allow file-read-data )' not in text
    return text

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];m.verify(read(HERE/'execution-contract.json'))
    fixture=read(HERE/'fixture-audit.json');manifest=read(HERE/'render-manifest.json')
    assert fixture['mechanism_passed'] and len(fixture['rows'])==8 and len(manifest['rows'])==8
    for row in manifest['rows']:assert digest(m.REPO/row['path'])==row['sha256']
    failure=read(HERE/'child-failure.json');assert 'PermissionError' in failure['stderr'] and 'single-a.wav' in failure['stderr']
    with b.job(NAME,'audit','隔離の所有一時領域だけread-data許可を事前追補',reserve_bytes=2000000) as j:
        amendment=dict(reason='親外部rootの具体的file-read-data拒否に対し、file-read*だけでは自分の出力をhash再読取りできなかった。所有workspaceのsubpathだけを具体的file-read-data許可する。',
            source_sha256=digest(Path(__file__)),original_controller_sha256=digest(Path(m.__file__)),original_execution_contract_sha256=digest(HERE/'execution-contract.json'),original_failure_sha256=digest(HERE/'child-failure.json'),
            reused_normal_fixture_sha256=digest(HERE/'fixture-audit.json'),reused_normal_manifest_sha256=digest(HERE/'render-manifest.json'),normal_waveforms_repeated=0,independent_reference_repeated=0,
            all_generator_code_coefficients_requests_and_gates_unchanged=True,no_past_audio_or_metadata_read_permission_added=True,no_unconditional_empty_read_allow=True,
            extra_charged_render=320,extra_charged_DSP=128,extra_maximum_seconds=900,temporary_peak=16000000,temporary_write=32000000,old_failures_and_costs_not_refunded=True,quality_goal_completed=False)
        b.save(HERE/'isolation-amendment-v2.json',amendment,j)
    print(dict(amendment_registered=True,normal_and_independent_waves_not_repeated=True),flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');m.verify(contract)
    amendment=read(HERE/'isolation-amendment-v2.json');assert digest(Path(__file__))==amendment['source_sha256'] and digest(Path(m.__file__))==amendment['original_controller_sha256']
    fixture=read(HERE/'fixture-audit.json');assert digest(HERE/'fixture-audit.json')==amendment['reused_normal_fixture_sha256']
    for row in read(HERE/'render-manifest.json')['rows']:assert digest(m.REPO/row['path'])==row['sha256']
    r=b.reserve(NAME,'render','限定所有read-data許可の隔離全8とCLI3だけ再生成',320,32000000,expected_seconds=900)
    try:
        d=b.reserve(NAME,'dsp','保存通常hashと隔離/CLI・全9実読取り/接続拒否の照合',128,2000000,expected_seconds=900)
        try:
            with b.workspace(r,'隔離修正全8と実拒否/CLIだけ専用',16000000,32000000) as (work,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1');profile=strict(b,work)
                isolated=m.execute([str(m.PYTHON),'-B',str(HERE/'runtime-bundle/batch.py'),str(work)],env,profile,json.dumps(m.requests()),timeout=600)
                assert [x['wav_sha256'] for x in isolated['rows']]==[x['wav_sha256'] for x in fixture['rows']]
                forbidden=[m.PREV/'render/a-220.wav',(m.PREV/'render/a-220.wav').resolve(),m.PREV/'upstream/arai-2007.pdf',(m.PREV/'upstream/arai-2007.pdf').resolve(),HERE/'registration.json',ROOT/'control/state.json',ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1/protocol.json',ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1/runtime-batch-normal.json',(ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1/runtime-batch-normal.json').resolve()]
                assert all(p.is_file() for p in forbidden)
                probe=m.execute([str(m.PYTHON),'-B',str(HERE/'runtime-bundle/denial_probe.py')],env,profile,json.dumps([str(p) for p in forbidden]),timeout=45);assert probe['all_denied']
                cli=[]
                for id in read(HERE/'registration.json')['fixture']['CLI_conditions']:
                    row=next(x for x in fixture['rows'] if x['id']==id);out=m.execute([str(m.PYTHON),'-B',str(HERE/'runtime-bundle/cli.py'),'--output',str(work/(id+'-cli.wav'))],env,profile,json.dumps(row['request']),timeout=180)
                    assert out['wav_sha256']==row['wav_sha256'];cli.append(dict(id=id,wav_sha256=out['wav_sha256'],calls=out['source_and_block_render_calls']))
                extra=isolated['calls']+sum(x['calls'] for x in cli);assert extra<=320
                b.save(HERE/'denial-probe.json',probe,d);b.save(HERE/'runtime-audit.json',dict(normal_isolated_all8_exact=True,CLI_all3_exact=True,CLI_rows=cli,reused_normal_calls=fixture['actual_render_calls'],normal_generation_repeated=False,independent_reference_repeated=False,
                    isolated_calls=isolated['calls'],CLI_calls=sum(x['calls'] for x in cli),extra_actual_render_calls=extra,original_charged_render=1000,extra_charged_render=320,total_charged_render=1320,total_charged_DSP=1128,
                    original_isolation_failure_retained=True,original_failed_first_case_conservatively_in_1000=True,amendment_sha256=digest(HERE/'isolation-amendment-v2.json'),forbidden_files_and_network_denied=True,
                    all_generation_bundle_files_internal=True,owned_work_subpath_read_data_allowed=True,no_unconditional_empty_read_allow=True,HMM=False,neural=False,recorded_audio=False,utterance_lookup=False),d)
        except BaseException as exc:
            if isinstance(exc,m.subprocess.CalledProcessError):b.save(HERE/'child-failure-v2.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','原費用と隔離追補の合計を封印前の別紙へ保存',reserve_bytes=2000000) as j:
        b.save(HERE/'isolation-repair-cost-note-v2.json',dict(original_report_count=1000,extra_render=320,total_render=1320,original_DSP=1000,extra_DSP=128,total_DSP=1128,original_failure_and_costs_retained=True,normal_and_reference_not_repeated=True,authoritative_cost_audit_path='cost-audit.json',quality_goal_completed=False),j)
        b.write(HERE/'report-v2.md',('# 状態継承の連続母音列と隔離修正の終了結果\n\n8列の独立回転、4096と2048/4096/8192の区切り不変、原3単母音のbyte一致、将来指令変更時のraw前半不変を全通過。E0 8/8、pitch 8/8、事前固定支持欠測0/77、最長6000ms。原共有径・LF尺度・帯域・gain・終端と工学閾値を変更していない。\n\n初回の隔離は、自分の外部一時出力のhash再読取りまで具体的file-read-data拒否が適用されて失敗した。所有workspaceのsubpathだけに具体的read-data許可を追加し、通常波形/独立参照を再生成せず再開した。通常/隔離8波と隔離CLI3条件の全byte一致、過去波形/PDFの論理/実体パス・登録・台帳・旧protocol・archiveの実読取り9件と実接続の権限拒否を確認した。無条件/空のread許可はない。\n\n原1000render/1000DSPは失敗も含めて保持。隔離修正320render/128DSPを追加し、総1320render/1128DSP。原report.mdの1000という費用は初回分で、合計は本紙とcost-audit.jsonを正本とする。使った全所有一時領域は指定外部媒体から削除済み。\n\n最終bundleはHMM/神経推論/録音/発話lookupを使わず、共有母音列から状態と位相を継承して計算する。子音・閉鎖・鼻腔・放射/損失・移動壁の仕事、内容/日本語自然さは未資格。次は新しい有限母音語列で原nativeと二ASR内容比較を出力前登録する。旧契約/封印/凍結を保持。P5未開封・知覚資格なし・品質未達。\n').encode(),j)
    # 原版の封印/全工学条件/台帳終了は変更せず、その末尾だけを使う。
    node=next(n for n in ast.parse(Path(m.__file__).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='run')
    start=next(i for i,n in enumerate(node.body) if isinstance(n,ast.With) and isinstance(n.items[0].context_expr,ast.Call) and isinstance(n.items[0].context_expr.func,ast.Attribute) and n.items[0].context_expr.func.attr=='job')
    scope=dict(m.__dict__,b=b,contract=contract,fixture=fixture)
    exec(compile(ast.Module(body=node.body[start:],type_ignores=[]),m.__file__,'exec'),scope)
    b.save(ROOT/'progress-0122.json',dict(latest_completed=NAME,effective_report='campaigns/nas-waveguide-sequence-runtime-20261008-v1/report-v2.md',normal_and_reference_not_repeated=True,extra_render=320,extra_DSP=128,quality_goal_completed=False,next=read(HERE/'registration.json')['next'],budget=b.reconcile()))
    print(dict(isolation_repair_completed=True,total_render=1320,total_DSP=1128),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','finish']);a=p.parse_args();{'register':register,'finish':run}[a.stage]()
