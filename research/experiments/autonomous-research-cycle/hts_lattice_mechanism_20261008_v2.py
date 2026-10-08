"""既知ARの有限MCP誤差を不通過のまま保持し、射影とlattice自体の限定機構を確認する。"""
import ast,hashlib,json,os,subprocess
from pathlib import Path
import hts_lattice_mechanism_20261008 as original
from budget import ROOT,read,digest,encode
Budget=original.Budget;HERE=original.HERE;NAME=original.NAME;REPO=original.REPO

def make_fixture():
    text=original.FIXTURE
    text=text.replace(';assert herr<=1e-8','')
    text=text.replace(';assert independent<=1e-10 and knownerr<=1e-7 and gainerr<=1e-7',';assert independent<=1e-10')
    needle="    spectral.append(dict(case=index,alpha=alpha,known_response_relative_error=herr,dense_coefficient_max_abs_error=independent,known_coefficient_max_abs_error=knownerr,known_gain_error=gainerr,passed=True))"
    added="""    # 無限ARを有限35 MCPへ写した時の既知の尾。元の誤差閾値は変えない。
    rho=np.abs(w);tail=float(np.sum(rho**35/(35*(1-rho)))+len(poles)*abs(alpha)**35/(35*(1-abs(alpha))))
    response_bound=float(np.expm1(tail));assert herr<=response_bound+1e-12
    old_pass=bool(herr<=1e-8 and knownerr<=1e-7 and gainerr<=1e-7)
    spectral.append(dict(case=index,alpha=alpha,known_response_relative_error=herr,dense_coefficient_max_abs_error=independent,known_coefficient_max_abs_error=knownerr,known_gain_error=gainerr,
        analytic_truncated_log_tail_bound=tail,analytic_relative_response_bound=response_bound,finite_MCP_tail_bound_pass=True,
        independent_finite_MCP_projection_pass=True,original_known_AR_gate_pass=old_pass,passed=old_pass))"""
    assert text.count(needle)==1;text=text.replace(needle,added)
    text=text.replace('print(json.dumps(dict(passed=True,known_AR_checks=spectral',"print(json.dumps(dict(passed=all(v['original_known_AR_gate_pass'] for v in spectral),implementation_mechanical_passed=True,known_AR_checks=spectral")
    text=text.replace('render=62,dsp=232','render=62,dsp=248')
    text=text.replace('dsp_breakdown=dict(known_AR_projection=16','dsp_breakdown=dict(analytic_MCP_tail_bound=16,known_AR_projection=16')
    ast.parse(text);return text

def amend():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];original.verify(read(HERE/'execution-contract.json'))
    diag=read(HERE/'known-AR-truncation-diagnostic.json');assert sum(v['original_known_AR_gate_pass'] for v in diag['spectral'])==14 and len(diag['spectral'])==16
    fixture=make_fixture()
    with b.job(NAME,'setup','有限MCPの既知AR不通過と限定機構の別版契約',reserve_bytes=2000000) as j:
        b.write(HERE/'fixture_v2.py',fixture.encode(),j)
        b.save(HERE/'execution-amendment-v2.json',dict(controller_sha256=digest(Path(__file__)),fixture_sha256=digest(HERE/'fixture_v2.py'),original_execution_contract_sha256=digest(HERE/'execution-contract.json'),
            original_fixture_sha256=digest(HERE/'fixture.py'),diagnostic_sha256=digest(HERE/'known-AR-truncation-diagnostic.json'),
            reason='有限35 MCPは負のpoleを含む既知ARの無限cepstrumを厳密に表せず、alpha.55の2/16条件で元の応答/係数ゲート不通過。独立Toeplitzは全16一致。',
            original_thresholds_unchanged=True,original_failed_cases_not_removed=True,inputs_C_binary_and_projection_algorithm_unchanged=True,
            original_known_AR_qualification_remains_false=True,
            new_scope='元の全16応答/係数/gain判定を保持し、有限MCPへの射影が独立密Toeplitzと一致するか、C静的直接形/有限動的逆写像/原HTSの限定機構を検査する。失敗の応答誤差は解析的cepstrum尾上限と追加照合。',
            thresholds=dict(additional_tail_bound_rounding_allowance=1e-12,all_original_thresholds_kept=True),
            additional_run_cost=dict(render=62,dsp=248,analytic_tail_checks_dsp=16),campaign_limits_unchanged=True,quality_goal_completed=False),j)
    verify();print('既知AR14/16と2不通過を保持し、有限表現の尾と限定機構を別登録',flush=True)

def verify():
    a=read(HERE/'execution-amendment-v2.json');assert digest(Path(__file__))==a['controller_sha256']
    assert digest(HERE/'fixture_v2.py')==a['fixture_sha256'] and digest(HERE/'fixture.py')==a['original_fixture_sha256']
    assert digest(HERE/'execution-contract.json')==a['original_execution_contract_sha256']
    assert digest(HERE/'known-AR-truncation-diagnostic.json')==a['diagnostic_sha256'];original.verify(read(HERE/'execution-contract.json'));return a

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify()
    r=b.reserve(NAME,'render','全極latticeの人工駆動源・独立直接形・原HTS全生成',62,20000000,expected_seconds=300)
    try:
        d=b.reserve(NAME,'dsp','独立Toeplitz・既知AR・動的逆写像・安定域・原源照合',248,1000000,expected_seconds=300)
        try:
            with b.workspace(r,'有限MCPと限定lattice機構の別版fixture') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(original.PYTHON),'-B',str(HERE/'fixture_v2.py')],env=env,check=True,capture_output=True,text=True,timeout=240)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit-v2.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure-v2.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','元の全分母不通過・有限表現・限定機構・費用・一時回収の終了',reserve_bytes=2000000) as j:
        assert fixture['implementation_mechanical_passed'] and not fixture['passed']
        assert sum(fixture['render_breakdown'].values())==62 and sum(fixture['dsp_breakdown'].values())==248
        rows=fixture['known_AR_checks'];assert len(rows)==16 and sum(v['original_known_AR_gate_pass'] for v in rows)==14
        verify()
        summary=dict(mechanical_fixture_passed=False,original_known_AR_qualification=False,original_known_AR_pass_count=14,original_known_AR_denominator=16,
            implementation_mechanical_fixture_passed=True,limited_scope='有限35 MCPの独立Toeplitz射影・静的直接形・有限動的逆写像・原HTS不変のみ。既知無限ARの全件厳密再現ではない。',
            known_AR_failed_cases=[v for v in rows if not v['original_known_AR_gate_pass']],all_original_thresholds_and_denominators_kept=True,analytic_truncation_bounds_passed=True,
            lattice_order=34,FFT_length=16384,original_native_wave_exact=True,source_clock_and_all_input_parameters_exact=True,causal_prefix_exact=True,
            global_time_varying_stability_proven=False,real_HTS_MCP_projection_qualified=False,real_Japanese_speech_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
        b.save(HERE/'aggregate-summary.json',summary,j)
        lines=['# 全極射影とlatticeの限定機構','','元の全件機構資格は不通過。既知AR8系×alpha0/.55の16条件中14通過、alpha.55の負poleを含む2条件は元の応答/係数閾値を外れた。失敗・しきい値・分母・初回消費は保持する。','',
            '無限ARを有限35 MCPに写した表現誤差を、cepstrumの35次以降の解析的尾上限で確認した。独立密Toeplitzとの射影係数照合は全16通過。Cと射影算法・入力・係数は変更していない。','',
            '別版の限定機構として、4駆動源×3次数の独立標準形/因果性、有限動的34次の昇順解析逆写像、8人工MCP、4HTS原native/入力/源時計を確認した。一般MCP/MLSAや既知無限ARの厳密再現、任意時間変動の一様安定、自然さへ拡張しない。','',
            '診断前の一時領域予約2MBに対し入口の8MB要件で拒否された失敗96DSPも保持した。適切な20MB予約で診断を実行し、全所有一時領域を回収した。','',
            '次は科学24件のレビュー。その後、有限MCPの近似損失/安定域を実frame全件で別資格として確認する。係数やknown ARゲートを同コホートで救済しない。知覚資格なし・P5未開封・品質未達。','',
            '一次資料: [SPTK levdur](https://sp-nitech.github.io/sptk/latest/main/levdur.html)、[par2lpc](https://sp-nitech.github.io/sptk/latest/main/par2lpc.html)、[poledf](https://sp-nitech.github.io/sptk/latest/main/poledf.html)。独自実装で、ソース/library取得なし。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,failed_attempts_and_internal_HTS_helpers_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,original_mechanical_qualification=False,limited_implementation_qualification=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='lattice-limited-mechanism-completed',active_campaign=None,next='科学24件レビュー後に有限MCP射影損失と安定域の全実frame資格',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0090.json',dict(latest_completed=NAME,original_mechanical_qualification=False,limited_implementation_qualification=True,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(original_AR_gate_pass='14/16',original_mechanical_qualification=False,limited_implementation_qualification=True,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['amend','fixture']);a=p.parse_args();amend() if a.stage=='amend' else run()
