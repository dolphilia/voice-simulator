"""既存固定支持の源励振・欠測・未知を全分母で閉じる。"""
from paths import *
import argparse,subprocess
from collections import Counter
def verify():
    c=read(HERE/'execution-contract.json')
    for n,h in c['sources'].items():assert digest(HERE/n)==h,n
    for n,h in c['inputs'].items():assert digest(REPO/n)==h,n
    assert digest(HERE/'registration.json')==c['registration_sha256'] and digest(HERE/'protocol.json')==c['protocol_sha256']
def run(stage):
    verify();b=Budget();b.recover();records=read(HERE/'protocol.json')['records']
    if stage=='hts':
        number=sum(x['cohort']=='nas-vocoder-f0' and x['method'].startswith('hts') and not (HERE/'new-hts-diagnostic'/(x['id']+'.json')).exists() for x in records)
        assert number>0
        with b.job(NAME,'dsp','96HTS位相/実パルスの不変検査',count=number*2,reserve_bytes=1000000):
            with b.job(NAME,'render','既存HTS96の観測再構成。波形保存なし',count=number,reserve_bytes=600000000) as j:
                with b.workspace(j,'HTS観測の外部専用cache') as (_,env):
                    subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py'),stage,'--job',j],env=env,check=True,timeout=10800)
    else:
        number=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in records);assert number>0
        with b.job(NAME,'dsp','全固定支持・旧DIO・実パルス・3窓を照合',count=number*3,reserve_bytes=600000000) as j:
            with b.workspace(j,'固定支持照合の外部専用cache') as (_,env):
                subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py'),stage,'--job',j],env=env,check=True,timeout=10800)
    print(b.reconcile(),flush=True)
def close():
    verify();b=Budget();b.recover()
    with b.job(NAME,'audit','全分母・源不足/音響曖昧/未知・費用・封印',reserve_bytes=5000000) as j:
        rows=[]
        for x in read(HERE/'diagnostic-manifest.json')['rows']:
            assert digest(REPO/x['path'])==x['sha256'];rows.append(read(REPO/x['path']))
        assert len(rows)==992 and sum(x['actual_source_known'] for x in rows)==224
        groups={}
        for x in rows:groups.setdefault(x['cohort']+'/'+x['method'],[]).append(x)
        table={}
        for k,v in groups.items():
            intervals=[d for x in v for d in x['all_fixed_support_intervals']];missing=[d for d in intervals if d['old_fixed_support_missing']]
            table[k]=dict(files=len(v),known_source_files=sum(x['actual_source_known'] for x in v),
                fixed_support_intervals=len(intervals),missing_intervals=len(missing),
                all_source_states=dict(Counter(d['actual_source_state'] for d in intervals)),
                missing_source_states=dict(Counter(d['actual_source_state'] for d in missing)),
                missing_drive_states=dict(Counter(d['driving_state'] for d in missing)),
                missing_phones=dict(Counter(d['phone'] for d in missing)),
                missing_duration_ms=dict(Counter(str(d['duration_ms']) for d in missing)))
        cross=read(CROSS/'aggregate-summary.json')
        for k,v in table.items():
            cohort,method=k.split('/');old=cross['cohorts'][cohort+'-20261008-v1']['methods'][method]
            assert v['files']==old['expected'] and v['missing_phones']==old['missing_phone_counts']
        summary=dict(total=992,actual_HTS_source_known=224,WORLD_actual_source_unknown=768,all_fixed_support_kept=True,
            groups=table,old_DIO_support_exact=True,old_missing_counts_match_cross_factor_audit=True,
            acoustic_ambiguity_not_proven_tracker_failure=True,source_pulse_does_not_guarantee_final_periodic_energy=True,
            WORLD_unknown_not_imputed=True,no_old_qualification_change=True,
            quality_goal_completed=False,protected_confirmation_opened=False,observational_existing_corpus_only=True)
        b.save(HERE/'aggregate-summary.json',summary,j)
        c=b.snapshot()['campaigns'][NAME];b.save(HERE/'cost-audit.json',dict(campaign=c,new_HTS_observations=96,reused_HTS_observations=128,
            new_WORLD_observations=0,new_AI=0,new_tracker_calls=0,all_temporary_removed=True),j)
        lines=['# 固定有声支持と実励振の欠測診断','',
            '既存992件の固定支持区間をすべて保持し、旧DIOのclock・有声件数・支持欠測を再照合した。WORLD768件は互換不通過のため実励振unknownを保持。HTS224件は旧128traceと、旧WAV完全一致の追加96traceを使用した。','',
            '|コホート/方式|支持区間|欠測|欠測源区分|','|---|---:|---:|---|']
        for k,v in table.items():lines.append(f"|{k}|{v['fixed_support_intervals']}|{v['missing_intervals']}|{v['missing_source_states']}|")
        lines+=['','源が全無声、区間内パルス0、4パルス未満、パルス存在下の音響曖昧、WORLD未確認を分けた。4パルス条件は第25回の窓内平均発生率に必要な3完全間隔であり、旧支持や知覚ゲートを変えていない。',
            'パルスがあってもLPF後の周期エネルギー・SNR・残響・非定常性の影響が残るため、DIOの欠測を測定器の失敗だけに断定しない。無励振区間の残響も保持する。源LF0の全有声は実励振truthではない。',
            '短窓/動的測定と源区分は事後診断に限定。旧ASR/採否/P5を更新しない。次は全結果と二ASR悪化群を統合し、追加制御比較の可否と必要条件を判断する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_removed=True),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s.setdefault('continuation_checkpoint_history',[]).append(s['continuation_checkpoint'])
        s['continuation_checkpoint']=dict(id='support-excitation-completed-20261008-0001',active_campaign=None,campaign_closed=True,
            next='commit/push→第28回全結果/ASR悪化群/終了監査',git_save_pending=True,quality_goal_completed=False,protected_confirmation_opened=False);b._write_state(s)
    b.save(ROOT/'progress-0039.json',dict(latest_completed=NAME,quality_goal_completed=False,next='第28回統合終了監査',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['hts','diagnose','close']);a=p.parse_args()
    close() if a.stage=='close' else run(a.stage)
if __name__=='__main__':main()
