"""旧8資料を反復せず、新4資料の公開メタデータと知覚評価への適用範囲を保存する。"""
import argparse, hashlib, os, urllib.request
from pathlib import Path
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-perceptual-new-four-20261008-v1'
NAME='perceptual-new-four-v1'
CRITERIA=['Japanese_spoken_verified','current_non_neural_scope_verified','public_stimulus_individual_rating_pair_verified','all_artifact_terms_verified','unused_confirmation_separable_verified']
SOURCES=[
 ('speechjudge-card','https://huggingface.co/api/datasets/RMSnow/SpeechJudge-Data'),
 ('animescore-readme','https://raw.githubusercontent.com/sizigi/animescore/main/README.md'),
 ('animescore-data-readme','https://raw.githubusercontent.com/sizigi/animescore/main/data/README.md'),
 ('character-tts-paper','https://arxiv.org/html/2505.17320v2'),
 ('humanlike-japanese-article','https://www.jstage.jst.go.jp/article/jnlp/33/1/33_186/_article/-char/en'),
 ('humanlike-stimulus-page','https://www.speech-data.jp/kaken_hiryu/synthesis/ntl_vs_dis/')]
CANDIDATES=[
 dict(id='SpeechJudge-Data',sources=[SOURCES[0][1],'https://huggingface.co/datasets/RMSnow/SpeechJudge-Data','https://speechjudge.github.io/'],
      facts='公開カードは中国語/英語の単一・交差・混合言語と人による自然さ比較を記載。日本語は記載なし。実ファイルは連絡先と利用条件の同意を要するgated資料。',
      Japanese_spoken_verified=False,current_non_neural_scope_verified=False,public_stimulus_individual_rating_pair_verified=False,all_artifact_terms_verified=False,unused_confirmation_separable_verified=None,
      reason='中国語/英語の評点を日本語HTSの校正へ移さない。gatedファイルへアクセスせず、同意・申請・連絡を行わない。カードのCC BY-NC 4.0と実ファイル利用資格を区別。'),
 dict(id='AnimeScore',sources=[SOURCES[1][1],SOURCES[2][1],'https://github.com/sizigi/animescore'],
      facts='日本語のアニメらしさをA/B比較から順位学習する資料。READMEは3,000発話、187評定者、15,000対を記載。元音声は含まれず各コーパスの条件に依存。CER/UTMOSによる選別を含む。',
      Japanese_spoken_verified=True,current_non_neural_scope_verified=False,public_stimulus_individual_rating_pair_verified=False,all_artifact_terms_verified=False,unused_confirmation_separable_verified=None,
      reason='アニメらしさの選好を自然さMOSと同一視しない。UTMOSは人の自然さ評点ではない。READMEのMIT表記を元音声の許諾へ移さず、掲載DOIの出版確認も主張しない。'),
 dict(id='Expressive-Japanese-Character-TTS-2505.17320v2',sources=[SOURCES[3][1]],
      facts='VITS/SBV2のキャラクター音声比較。日本語母語話者11人の60音声評定と5人のCMOSを本文で記載。公表値は集約評点。音声学習用の収録資料と評価用の刺激を区別。',
      Japanese_spoken_verified=True,current_non_neural_scope_verified=False,public_stimulus_individual_rating_pair_verified=False,all_artifact_terms_verified=False,unused_confirmation_separable_verified=None,
      reason='刺激・個別評点・利用条件の公開対応を特定できない。記事のCC BY-NC-SA 4.0をキャラクター音声・モデルの許諾へ転用しない。集約MOSを現HTSの品質証明にしない。'),
 dict(id='Humanlike-Japanese-JNLP-33-186',sources=[SOURCES[4][1],SOURCES[5][1]],
      facts='日本語FastPitch/WaveGANの中立/非流暢5対を106人が人間らしさで比較。本文は刺激公開頁を案内する一方、学習コーパスは制限付き私有資料。本文の公開評点は属性別の集約数。',
      Japanese_spoken_verified=True,current_non_neural_scope_verified=False,public_stimulus_individual_rating_pair_verified=False,all_artifact_terms_verified=False,unused_confirmation_separable_verified=None,
      reason='刺激頁の存在を認める。頁の取得失敗を不存在と解釈しない。5対の内容/フィラー等の差と現HTS源・フィルタ劣化を区別し、個別評点と音声利用条件の対応未確認を保持する。記事CC BY 4.0を音声許諾へ転用しない。')]

def verify():
    c=read(HERE/'source-contract.json')
    assert digest(Path(__file__))==c['controller_sha256']
    for n,h in c['files'].items():assert digest(HERE/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    prev=ROOT/'campaigns/nas-hts-lf-comparison-20261008-v1'
    assert read(prev/'aggregate-summary.json')['research_protection_gates']['lf'] is False
    limits=dict(seconds=3600,bytes=100000000,write_bytes=200000000,setup=8,audit=8,download=6000000,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0)
    reg=dict(campaign=NAME,question='新4資料に現日本語非ニューラル発話の実校正に必要な対応/範囲/許諾/未使用確認があるか。',
             candidates=CANDIDATES,criteria=CRITERIA,sources=SOURCES,public_metadata_only=True,bytes_per_source_at_most=1000000,
             no_gated_access_or_terms_submission=True,no_audio_weights_or_rating_files=True,old_eight_resources_not_repeated=True,
             eligibility_requires_all_criteria_true=True,actual_calibration_not_performed=True,prior_LF_seal=digest(prev/'artifact-seal.json'),
             controller_sha256=digest(Path(__file__)),limits=limits,protected_confirmation_opened=False,quality_goal_completed=False,
             next='同資料の同条件探索を凍結。レビュー第5回分岐の異なる共有文脈/韻律表現を出力前登録する。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','新4知覚資料の固定範囲と公開メタデータ費を登録',reserve_bytes=1000000) as j:
        b.save(HERE/'registration.json',reg,j)
        b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={'registration.json':digest(HERE/'registration.json')},no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0109.json',dict(active_campaign=NAME,next='登録push→公開メタデータの固定取得→全4候補の不足保存',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_audio_or_inference=0),flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify();fetches=[]
    with b.job(NAME,'download','新6公開メタデータ頁の上限付き取得・失敗も保存',6000000,10000000) as j:
        for name,url in SOURCES:
            row=dict(id=name,url=url,maximum_bytes=1000000,gated_file_access=False)
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch/1.0'})
                with urllib.request.urlopen(req,timeout=45) as response:
                    data=response.read(1000001);row.update(resolved_url=str(response.url),http_status=response.status,content_type=response.headers.get('Content-Type'))
                if len(data)>1000000:raise ValueError('公開メタデータが取得上限を超えた')
                target=HERE/'metadata'/f'{name}.txt';b.write_data(target,data,j)
                row.update(saved=True,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),path=str(target.relative_to(REPO)))
            except (OSError,ValueError) as exc:row.update(saved=False,error=repr(exc),unavailable_not_inferred=True)
            fetches.append(row)
        b.save(HERE/'metadata-fetch-audit.json',dict(sources=fetches,conservative_download_charge=6000000,unused_reservation_not_returned=True,audio_or_model_bytes=0),j)
    with b.job(NAME,'audit','新4知覚資料の不足・公開範囲・費用を全分母で封印',reserve_bytes=2000000) as j:
        verify();rows=[]
        for original in CANDIDATES:
            row=dict(original);row['failed_or_unknown']=[k for k in CRITERIA if row[k] is not True];row['metadata_eligible']=not row['failed_or_unknown'];rows.append(row)
        result=dict(candidates=rows,criteria=CRITERIA,eligible_for_current_Japanese_non_neural=sum(x['metadata_eligible'] for x in rows),
                    public_metadata_sources=fetches,source_fact_method='公開一次本文/公式カードの探索読取りを固定分類。取得hashは保存した公開頁に限定。本文から実音声を取得/実照合していない。',
                    calibration_count=0,perceptual_qualification=False,new_human_responses=0,new_audio_or_model_download_bytes=0,
                    protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next'])
        b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 新4知覚資料の公開範囲監査','','旧8資料を反復せず、新4資料の一次公開メタデータを上限付きで保存した。実音声・モデル・個別評点ファイルの取得0、校正0。全条件の通過候補0/4。日本語知覚資格なし・P5未開封・品質未達。','',
               '|資料|確認範囲|不足/判断|','|---|---|---|']
        for row in rows:lines.append('|'+row['id']+'|'+row['facts']+'|'+row['reason']+'|')
        for row in rows:lines+=['',row['id']+': '+', '.join('[一次資料'+str(i+1)+']('+u+')' for i,u in enumerate(row['sources']))]
        lines+=['','取得失敗は不存在を意味しない。記事・コード・モデル・音声の許諾を区別し、gated同意/申請/連絡をしていない。メタデータのhashは実刺激/個別評点の照合を代替しない。','',result['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[x for x in s['temporary_work'].values() if x['campaign']==NAME]
        assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='perceptual-new-four-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0110.json',dict(latest_completed=NAME,next=result['next'],quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(eligible=result['eligible_for_current_Japanese_non_neural'],calibration_count=0,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','run']);a=p.parse_args();{'register':register,'run':run}[a.stage]()
