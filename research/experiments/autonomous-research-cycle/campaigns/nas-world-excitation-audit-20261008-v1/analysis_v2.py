"""既存WORLD実励振を全件観測・封印する。"""
from paths import *
import argparse,subprocess
def verify():
    c=read(HERE/'execution-contract-v2.json')
    assert digest(HERE/'registration.json')==c['registration_sha256']
    assert digest(HERE/'protocol.json')==c['protocol_sha256']
    for n,h in c['source_hashes'].items():assert digest(HERE/n)==h,n
    for n,h in c['inputs'].items():assert digest(REPO/n)==h,n
def run(stage):
    verify();b=Budget();b.recover();p=read(HERE/'protocol.json')
    count=4 if stage=='compat' else sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in p['records'])
    assert count>0
    with b.job(NAME,'dsp','実周期成分/入力不変/同一波形集計',count=count*4,reserve_bytes=1000000):
        with b.job(NAME,'render','観測付き同一WORLD再構成。音声重複保存なし',count=count,reserve_bytes=600000000) as j:
            with b.workspace(j,'numpy/WORLD初期化・外部専用cache') as (_,env):
                subprocess.run([str(PYTHON),'-B',str(HERE/'observe_v2.py'),stage,'--job',j],env=env,check=True,timeout=10800)
    if stage=='compat':assert read(HERE/'compatibility-audit.json')['all_wave_byte_exact']
    print(b.reconcile(),flush=True)
def close():
    verify();b=Budget();b.recover()
    with b.job(NAME,'audit','768同一波形・実周期成分・費用・封印',reserve_bytes=4000000) as j:
        rows=[]
        for x in read(HERE/'diagnostic-manifest.json')['rows']:
            assert digest(REPO/x['path'])==x['sha256'];d=read(REPO/x['path']);assert d['wave_byte_exact']
            assert digest(REPO/d['trace_path'])==d['trace_sha256'];rows.append(d)
        assert len(rows)==768
        keys=['pulses','clock_pulses_unvoiced','voiced_clock_pulses','periodic_emitted','voiced_AP_suppressed','voiced_zero_periodic_other','source_voiced_frames','observed_voiced_samples','sample_count_48k','emitted_pulses_within_kept_audio']
        groups={}
        for r in rows:groups.setdefault(r['cohort']+'/'+r['method'],[]).append(r)
        table={k:dict(files=len(v),**{n:sum(x[n] for x in v) for n in keys}) for k,v in groups.items()}
        summary=dict(total=768,all_wave_byte_exact=True,groups=table,maximum_component_sum_error=max(x['component_sum_max_abs_error'] for x in rows),
            LF0_not_actual_or_perceived_pitch=True,unvoiced_clock_pulses_not_voiced_excitation=True,
            periodic_energy_not_perceived_pitch=True,old_gates_and_decisions_unchanged=True,
            observational_existing_corpus_only=True,protected_confirmation_opened=False,quality_goal_completed=False)
        b.save(HERE/'aggregate-summary.json',summary,j)
        c=b.snapshot()['campaigns'][NAME]
        b.save(HERE/'cost-audit.json',dict(campaign=c,actual_reconstruct_calls=c['counts'].get('render',0),new_AI=0,
            audio_duplicate_saved=0,all_temporary_removed=True,quality_goal_completed=False),j)
        lines=['# WORLDの実励振観測','',
            '既存6コホートのWORLD768件を、固定一次実装へ2つの観測hookだけ追加して再構成した。全件で入力3配列と保存済み24kHz WAVのbytehashが一致した。新しい合成係数・採否ゲートはない。','',
            '無声区間にも既定500Hzの時計パルスがあるため、時計だけを有声励振としない。周期応答は有声/AP条件でゼロ化され、最終パルスはnoise_size=0で周期寄与がゼロになる。LF0と周期出力寄与を分けた。','',
            '|コホート/方式|件数|有声時計パルス|周期寄与あり|APによる抑制|','|---|---:|---:|---:|---:|']
        for k,v in table.items():lines.append(f"|{k}|{v['files']}|{v['voiced_clock_pulses']}|{v['periodic_emitted']}|{v['voiced_AP_suppressed']}|")
        lines+=['','周期/非周期の成分RMSは観測用派生量で、知覚的有声・瞬時pitchの資格ではない。残響が無励振区間へ広がることも保持した。次は固定支持欠測と実励振の関係を全件照合する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_removed=True),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s.setdefault('continuation_checkpoint_history',[]).append(s['continuation_checkpoint'])
        s['continuation_checkpoint']=dict(id='world-excitation-completed-20261008-0001',active_campaign=None,campaign_closed=True,
            next='commit/push→第27回固定支持欠測と実励振の原因分離',git_save_pending=True,quality_goal_completed=False,protected_confirmation_opened=False);b._write_state(s)
    b.save(ROOT/'progress-0037.json',dict(latest_completed=NAME,quality_goal_completed=False,next='第27回固定支持原因分離',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['compat','all','close']);a=p.parse_args()
    close() if a.stage=='close' else run(a.stage)
if __name__=='__main__':main()
