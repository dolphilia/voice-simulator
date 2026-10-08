"""全160比較と独立性・費用・不採択を照合し封印する。"""
from paths import *
from controller_v2 import verify
def main():
    verify();a2=read(HERE/'preflight-recovery-v2.json');assert all(digest(HERE/n)==h for n,h in a2['source_hashes'].items());b=Budget();b.recover();assert not b.snapshot()['jobs']
    s=read(HERE/'aggregate-summary.json')
    assert not s['quality_goal_completed'] and not s['perceptual_qualification'] and not s['protected_confirmation_opened']
    with b.job(NAME,'audit','GV比較の全外部hash・費用・終了封印',reserve_bytes=4_000_000) as j:
        n=b.audit_data_hashes();v=b.snapshot();c=v['campaigns'][NAME]
        assert all(x['status']=='removed' and x['absence_verified'] for x in v.get('temporary_work',{}).values())
        assert all(c['counts'].get(k,0)<=lim for k,lim in c['limits'].items() if k not in ['seconds','bytes'])
        assert v['seconds']-c['start_seconds']<c['limits']['seconds'] and c['payload_bytes']<c['limits']['bytes']
        b.save(HERE/'cost-audit.json',dict(actual_render=487,actual_render_breakdown=dict(comparison=161,normal_isolated=320,CLI=4,compatibility=2),
            conservative_render=c['counts']['render'],conservative_DSP=c['counts']['dsp'],AI=320,
            technical_retries=3,unused_reservations_not_returned=True,campaign=c,whole_cycle_counts=v['counts'],
            whole_cycle_seconds=v['seconds'],whole_cycle_write_bytes=v['write_bytes'],all_temporary_removed=True,new_teacher_train_inverse_download_money=0),j)
        b.save(HERE/'decision-audit.json',dict(qualifications=s['qualifications'],selected=[k for k,x in s['qualifications'].items() if x],
            scope='内容・指定制御の研究資格だけ。知覚資格・独立P5は未達。',GV_ablation_analysis=s['GV_ablation_analysis'],
            secondary_diagnostics=s['secondary_diagnostics'],all_gates_fixed_before_output=True,
            quality_goal_completed=False,protected_confirmation_opened=False,next='85%以降は新しい経路を足さず、既存候補の比較・監査へ進む。'),j)
        lines=['# MCP/LF0のGV補正を除く比較','', '新16文×2条件×5方式の160比較。全160通常／隔離組、CLI4件、二ASR各160件。','',
            '|方式|ピッチ/支持通過|E0通過|Whisper誤り|Reazon誤り|資格|','|---|---:|---:|---:|---:|---|']
        for m,q in s['qualifications'].items():
            e=s['engineering'][m];w=s['content'][m]['whisper']['groups']['both/all'];r=s['content'][m]['reazon']['groups']['both/all']
            lines.append(f"|{m}|{e['pitch_pass_count']}/32|{e['E0_pass_count']}/32|{w['errors']}/{w['characters']}|{r['errors']}/{r['characters']}|{q}|")
        lines+=['','USE_GVの該当フラグだけを1→0とし、共有模型のデータ本体・位置・その他ヘッダを保持。GV重み0を無効化の代用には使わない。',
            '実状態とMLPG内部のGV mean/variance/有効長を検査。状態長/MSD/音響状態分布/LPF/設定/利得を保持。',
            'LF0補完・絶対校正は既存の固定規則。MCP後処理β=0、WORLD/AP=1。出力後の係数・しきい値変更なし。',
            '実波形487生成、二ASR320、教師・学習・逆推定・取得・金銭支出0。全費用・全33群の悪化・欠測を保存。',
            'Harvest/中心ACFは限定診断。実日本語の測定資格や知覚資格へ拡張しない。保護P5未開封、全体品質未達。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        hashes={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=hashes,path_base='repository',external_hash_verified=n,
            experiment_completed=True,quality_certified=False,quality_goal_completed=False,budget_before_seal=b.snapshot()),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(hashes),seal_sha256=digest(HERE/'artifact-seal.json'),
            all_temporary_work_removed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    b.save(ROOT/'progress-0024.json',dict(latest_completed=str(HERE.relative_to(ROOT)),active_campaign=None,comparison_records=160,
        normal_isolated_pairs=160,CLI=4,ASR_records=320,qualifications=s['qualifications'],quality_goal_completed=False,
        protected_confirmation_opened=False,all_temporary_work_removed=True,git_save_pending=True,
        next='85%以降は既存候補の比較・因果監査・終了に重点。',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
