"""純粋観測監査を封印し、旧科学判定を保持する。"""
from paths import *
from controller import verify
def main():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    s=read(HERE/'aggregate-summary.json')
    assert s['total']==128 and s['all_byte_exact'] and not s['quality_goal_completed']
    with b.job(NAME,'audit','純粋観測監査の外部hash・費用・不採択を封印',reserve_bytes=4_000_000) as j:
        n=b.audit_data_hashes();v=b.snapshot();c=v['campaigns'][NAME]
        assert all(w['status']=='removed' and w['absence_verified'] for w in v['temporary_work'].values())
        assert all(c['counts'].get(k,0)<=lim for k,lim in c['limits'].items() if k not in ['seconds','bytes'])
        assert v['seconds']-c['start_seconds']<c['limits']['seconds'] and c['payload_bytes']<c['limits']['bytes']
        b.save(HERE/'cost-audit.json',dict(actual_render=132,actual_comparison=128,actual_fixture=4,
            conservative_render=c['counts']['render'],conservative_DSP=c['counts']['dsp'],AI=0,
            technical_retries=0,unused_reservations_not_returned=True,campaign=c,whole_cycle_counts=v['counts'],
            all_temporary_removed=True,new_teacher_train_inverse_download_money=0),j)
        lines=['# 既存HTS励振周期の純粋観測監査','','第19回の既存16文×2条件×HTS4方式、全128波形が旧波形hashと一致。新しい生成規則は追加していない。','',
            '|測定|限定窓の全128通過|通過件数|','|---|---|---:|']
        for name,x in s['results'].items():lines.append(f"|{name}|{x['all_128_pass']}|{x['groups']['both/all']['passed']}/128|")
        lines+=['','60msの安定全有声窓と20msの全無声窓が対象。境界・変動・短い区間は理由と分母を保存。欠測・不足を不通過に含む。',
            '実励振の周期・位相・パルスを記録した。知覚ピッチの真値、WORLD、日本語一般の資格には広げない。旧ゲートと採否は変更していない。',
            '4定周期fixtureと128観測で実生成132回。ASR・教師・学習・逆推定・音声/模型取得・新しい人の回答は0。全一時領域は削除確認済み。',
            '保護P5未開封、知覚資格不足、全体品質未達。次は既存結果の因果別整理・サイクル終了監査へ進む。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',external_hash_verified=n,
            experiment_completed=True,observer_only=True,quality_certified=False,quality_goal_completed=False),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),
            all_temporary_removed=True,old_qualification_unchanged=True,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    b.save(ROOT/'progress-0028.json',dict(latest_completed=str(HERE.relative_to(ROOT)),active_campaign=None,
        observation_records=128,actual_render=132,actual_AI=0,all_byte_exact=True,quality_goal_completed=False,
        protected_confirmation_opened=False,next='既存比較の因果別整理とサイクル終了監査。',git_save_pending=True,budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
