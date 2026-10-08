"""旧6資料を反復せず、新2資料の公開適用範囲と不足を全件保存する。"""
import os
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

NAME='japanese-perceptual-novel-resources-v1'
HERE=ROOT/'campaigns/nas-japanese-perceptual-novel-resources-20261008-v1'
REPO=ROOT.parents[2]
CRITERIA=['Japanese_spoken_verified','current_non_neural_synthesis_or_degradation_scope_verified',
          'public_audio_ratings_pair_verified','terms_for_all_required_artifacts_verified',
          'unused_confirmation_separable_verified']
CANDIDATES=[
 dict(id='PASQA-2026',sources=['https://arxiv.org/html/2606.20137v1','https://github.com/lycorp-jp/PASQA',
     'https://huggingface.co/ly-corporation/PASQA','https://github.com/lycorp-jp/PASQA/issues/1'],
     facts='日本語のアクセント核誤りをNANSY-TTSで制御し、疑似アクセント評点を学習。主観120刺激・15母語話者、別TTS評価50文・10母語話者。重みの公開と刺激/人評点の公開を区別。',
     Japanese_spoken_verified=True,current_non_neural_synthesis_or_degradation_scope_verified=False,
     public_audio_ratings_pair_verified=False,terms_for_all_required_artifacts_verified=False,
     unused_confirmation_separable_verified=None,
     scoped_terms=dict(code='GitHub CC0-1.0',weights='Hugging Face Apache-2.0',audio_ratings='未確認。コード/重みの条件を内製音声・個別評点へ転用しない。'),
     applicability='アクセント順位と発話全体の自然さ、ニューラルTTSと共有HTSの源/フィルタ劣化を区別。非ニューラルでの実校正なし。',
     reason='公開モデルは確認できるが、現HTSでの刺激/人評点対応と未使用確認集合を確認できない。論文の高相関を現対象へ拡張しない。'),
 dict(id='ITU-P.Sup23-1998',sources=['https://www.itu.int/rec/T-REC-P.Sup23/en',
     'https://www.itu.int/rec/T-REC-P.Sup23-199802-I','https://www.itu.int/net/itu-t/sigdb/menu.aspx'],
     facts='公式はcoded-speech databaseと試験信号配布先を記載。旧配布先はMyWorkspaceへ転送する。本文PDFのweb取得はoctet-stream扱いで成功しなかった。原音声/個別評点ファイルは取得していない。',
     Japanese_spoken_verified=None,current_non_neural_synthesis_or_degradation_scope_verified=False,
     public_audio_ratings_pair_verified=None,terms_for_all_required_artifacts_verified=None,
     unused_confirmation_separable_verified=None,
     scoped_terms=dict(document='公式頁はFree Downloadと表示',audio_ratings='実配布物/全条件を未確認。文書の無料閲覧と音声利用権を区別。'),
     applicability='符号化電話音声という範囲を、文章生成HTSのbuzz/音響pitch曖昧さ/韻律/発話自然さへ拡張しない。',
     reason='日本語評点資料を含むという探索情報だけでは現HTS適用性を確認できない。公式配布実体・個別対応・利用条件が未確認。ログイン/登録/連絡をせず未資格のまま保持。')]

def main():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    execution=read(HERE/'execution-contract.json')
    assert digest(__file__)==execution['audit_source_sha256']
    assert digest(HERE/'registration.json')==execution['registration_sha256']
    reg=read(HERE/'registration.json');assert reg['candidates']==[x['id'] for x in CANDIDATES]
    j=b.reserve(NAME,'audit','新2資料の範囲・対応・条件・未確認の正式監査',3,1000000,expected_seconds=180)
    try:
        for row in CANDIDATES:
            row['failed_or_unverified']=[key for key in CRITERIA if row[key] is not True]
            row['metadata_eligibility']=not row['failed_or_unverified']
            row['actual_calibration_performed']=False;row['qualification']=False
        result=dict(candidates=CANDIDATES,checked_at='2026-10-08',criteria=CRITERIA,
            eligible_for_current_Japanese_non_neural=sum(x['metadata_eligibility'] for x in CANDIDATES),
            formal_audit_source_sha256=digest(__file__),qualification=False,actual_calibration_performed=False,
            source_read_method='web一次本文/公式カード/公式配布案内。探索済み情報を適用性監査へ整理。',
            source_content_hashes_not_collected=True,arxiv_version_pinned='2606.20137v1',
            old_six_resources_not_reaudited=True,raw_data_audio_model_download_bytes=0,new_inference=0,
            new_human_responses=0,external_audio_sent=0,protected_confirmation_opened=False,quality_goal_completed=False,
            next='この新2資料だけの同条件再探索を凍結。実対応資料/適用範囲が変わる場合に新契約で実校正。既存知覚資格不足と生成の内容/音響因子の結果を分け、生成研究を継続する。')
        assert result['eligible_for_current_Japanese_non_neural']==0
        b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 新2知覚資料の適用性監査','',
            '旧6資料を繰り返さず、PASQA-2026とITU-T P.Sup23を確認した。現日本語非ニューラルHTS発話を実校正できる公開刺激・人評点・適用劣化・利用条件の一式は確認できず。実校正0、知覚資格なし。','',
            '|資料|得た証拠|不足/判断|','|---|---|---|']
        for row in CANDIDATES:lines.append('|'+row['id']+'|'+row['facts']+'|'+row['reason']+'|')
        lines+=['','PASQAは日本語アクセント評価に関わる新たな先例であり、公開コードと重みの利用条件を確認した。ただし現在のHTSの音源/フィルタ劣化や全体自然さを判定する資格にはしない。ITU資料の配布案内も実音声/評点/権利の確認を代替しない。','']
        for row in CANDIDATES:
            lines += [row['id']+': '+', '.join('[一次資料'+str(i+1)+']('+u+')' for i,u in enumerate(row['sources'])),'']
        lines += ['音声・評点・重みの取得0、推論0、外部音声送信0、新しい人の回答0。一次本文のcopy/hashは保存しておらず、取得物の実照合も行っていない。未知を通過に扱わず、P5未開封・全体品質未達を保持する。','',result['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[w for w in s['temporary_work'].values() if w['campaign']==NAME]
        assert all(w['status']=='removed' and not os.path.lexists(w['path']) for w in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,Git_fee_in_global_ledger=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    except BaseException as exc:b.finish(j,repr(exc));raise
    else:b.finish(j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='japanese-perceptual-novel-resources-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0060.json',dict(latest_completed=NAME,next=result['next'],qualification=False,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print('新2資料の適用性を保存。実校正/知覚資格は0。生成研究を継続',flush=True)

if __name__=='__main__':main()
