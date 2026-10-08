"""別の日本語MRI一次表を公開経路から限定取得し、生成に先立つ検証入口を確保する。"""
import argparse,ast,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-mri-primary-source-access-20261009-v1';NAME='mri-primary-source-access-v1'
PREV=ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1'
PDFPY=Path('/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
SOURCES=[('author-public','https://www.researchgate.net/publication/profile/Yasuhiro-Shimada-3/publication/7255958_Measurement_of_temporal_changes_in_vocal_tract_area_function_from_3D_cine-MRI_data/links/02bfe511970313ac3d000000/Measurement-of-temporal-changes-in-vocal-tract-area-function-from-3D-cine-MRI-data.pdf'),('publisher-public','https://pubs.aip.org/asa/jasa/article-pdf/119/2/1037/14779974/1037_1_online.pdf')]
SCANNER=r'''"""取得PDFの一次文献同一性と表位置だけを確認。全数値の資格は別段階。"""
import sys,json,re,os,tempfile
from pathlib import Path
from pypdf import PdfReader
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
source=Path(sys.argv[1]);pages=PdfReader(source).pages;texts=[p.extract_text(extraction_mode='layout') for p in pages];alltext='\n'.join(texts)
assert len(pages)==13 and '10.1121/1.2151823' in alltext and 'Takemoto' in alltext and '2006' in alltext
tables={r:[i+1 for i,t in enumerate(texts) if re.search(r'TABLE\s+'+r+r'\s*\.',t)] for r in ['I','II','III']};assert all(tables.values())
print(json.dumps(dict(passed=True,pages=len(pages),DOI='10.1121/1.2151823',table_pages_one_based=tables,full_numeric_table_verified=False,geometry_direction_units_and_lengths_verified=False,generated_waveforms=0)))
'''
@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield j
    except BaseException as e:b.finish(j,repr(e));raise
    else:b.finish(j)
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];v=read(PREV/'aggregate-summary.json');assert not v['adopted'] and not any(v['research_protection_gates'][s] for s in ('derivative','flow'))
    ast.parse(SCANNER);limits=dict(seconds=7200,bytes=200000000,write_bytes=400000000,setup=20,audit=20,render=0,dsp=64,ai=0,teacher=0,train=0,inverse=0,download=8000000)
    reg=dict(campaign=NAME,question='別の日本語cine-MRIの公開一次PDFを取得し、共有声道数値/単位/境界を独立検証する次の入口を確保できるか。取得だけを形状・音声品質の資格としない。',
      previous_seal=digest(PREV/'artifact-seal.json'),previous_content_not_protected=True,previous_source_and_gain_and_timing_and_geometry_rescue_frozen=True,
      primary=dict(title='Measurement of temporal changes in vocal tract area function from 3D cine-MRI data',DOI='10.1121/1.2151823',journal='JASA 119(2),1037–1049,2006',public_author_page='https://www.researchgate.net/publication/7255958_Measurement_of_temporal_changes_in_vocal_tract_area_function_from_3D_cine-MRI_data',publisher_or_author_manuscript_only=True,HTML_full_text_was_publicly_readable=True),
      acquisition=dict(priority=SOURCES,maximum_bytes_each=4000000,total_maximum_charged_download=8000000,try_publisher_only_if_author_PDF_not_saved=True,HTTP_or_non_PDF_failure_retained=True,no_login_or_captcha_bypass_or_contact_or_paid_access=True,no_corpus_or_audio_or_models=True),
      scope='一次表は数値事実の参考。本文/図/全PDFは©2006 ASAでCCと主張しない。取得できたPDFは指定外部に私的研究参照として保持しGitで再配布しない。共有生成用の数値は方向/単位/欠落/主声道長/枝と全数値の別検証・目視を経るまで導入しない。単一51歳Tokyo男性のcine計測を全日本語の正解にしない。',
      expected_following_geometry=dict(section_cm=.25,main_section_counts=dict(a=71,i=70,u=72,e=69,o=74),main_areas_expected=356,main_tables=['I','II'],piriform_table='III',attachment_section=11,mri_geometry_not_yet_numerically_verified=True,new_kernel_bounds_and_branches_and_physical_outputs_need_separate_qualification=True),
      estimates=dict(render=0,DSP_at_most=4,AI=0,download=8000000,temporary_peak=16000000,temporary_write=32000000,closeout_and_Git_included=True),limits=limits,controller_sha256=digest(Path(__file__)),quality_goal_completed=False,protected_confirmation_opened=False,perceptual_qualification=False,
      next_if_available='一次PDFの主声道/左右枝の全数値を二抽出と目視で照合して別登録する。16区間/96kHzの旧境界を変更して使う前に、新区間数/標本化/長さ/枝・源と出力の単位を独立資格化する。波形やASR結果から形状を選別しない。',
      next_if_unavailable='取得失敗のURL/HTTPと費用を保持し、公開HTMLの存在を否定しない。同じアクセスを反復/迂回しない。公開一次式で源のvolume velocity・mouth flow・遠方放射の境界/単位という別機構を先に資格化する。数学的loss portの不採択をgain救済しない。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','別の日本語一次MRIの公開取得範囲/費用/未資格を事前登録',size=1000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'scanner.py',SCANNER.encode(),j);b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={'registration.json':digest(HERE/'registration.json'),'scanner.py':digest(HERE/'scanner.py')},no_waveforms=True),j)
    b.save(ROOT/'progress-0134.json',dict(active_campaign=NAME,next='登録push→公開著者/出版元だけを有限取得→一次同一性と表位置→数値検証への正確な未実施入口',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()));print('日本語MRI一次PDFの公開取得監査を事前登録',flush=True)
def acquire():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
    for n,h in c['files'].items():assert digest(HERE/n)==h
    rows=[];selected=None
    for name,url in SOURCES:
        if selected:break
        with job(b,'download','公開一次PDFを一回取得 '+name,4000000,5000000,90) as j:
            row=dict(id=name,URL=url,maximum_bytes=4000000,charged_download=4000000,saved=False)
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; voice-simulator research; public-reference-only)'})
                with urllib.request.urlopen(req,timeout=45) as response:
                    data=response.read(4000001);row.update(status=response.status,final_URL=response.url,content_type=response.headers.get('Content-Type'))
                assert len(data)<=4000000 and data.startswith(b'%PDF-'),'公開応答が上限内PDFではない'
                path=HERE/'source'/(name+'.pdf');b.write_data(path,data,j);selected=path;row.update(saved=True,bytes=len(data),sha256=digest(path),path=str(path.relative_to(REPO)))
            except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,AssertionError) as exc:row.update(error=repr(exc),status=getattr(exc,'code',row.get('status')),no_bypass_attempted=True)
            rows.append(row);b.save(HERE/('acquisition-'+name+'.json'),row,j)
    scan=None
    if selected:
        with job(b,'dsp','一次PDF同一性/13頁/表位置のみの限定確認',4,40000000,180) as j:
            with b.workspace(j,'一次PDF読取専用の科学依存初期化',16000000,32000000) as (_,env):
                out=subprocess.run([str(PDFPY),'-B',str(HERE/'scanner.py'),str(selected)],env=env,check=True,capture_output=True,text=True,timeout=120)
            scan=json.loads(out.stdout);b.save(HERE/'primary-identity-audit.json',scan,j)
    with job(b,'audit','取得可否・正確な未資格・費用・全旧封印・一時回収を封印',size=2000000) as j:
        for n,h in read(PREV/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        available=bool(scan and scan['passed']);reg=read(HERE/'registration.json');result=dict(source_available=available,sources=rows,primary_identity=scan,all_numeric_facts_verified=False,geometry_or_generator_qualified=False,generated_waveforms=0,new_AI=0,protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,next=reg['next_if_available' if available else 'next_if_unavailable']);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 別の日本語cine-MRI一次PDFの公開取得監査','','[Takemoto et al. 2006](https://doi.org/10.1121/1.2151823)の[著者公開頁](https://www.researchgate.net/publication/7255958_Measurement_of_temporal_changes_in_vocal_tract_area_function_from_3D_cine-MRI_data)と出版元の公開PDFリンクだけを有限に試した。HTML全文が読めたことと、PDFの取得可否を分ける。','',f'PDF取得/同一性確認: {available}。新規音声0・AI0。全声道数値・方向・単位・長さ・境界、生成器、音声品質は未資格。','']
        for r in rows:lines.append(f'- {r["id"]}: saved={r["saved"]}, status={r.get("status")}, error={r.get("error")}。取得費 {r["charged_download"]} bytes。')
        lines += ['',reg['scope'],'',result['next'],'','失敗を含む全取得費を返金しない。指定外部の自分一時領域を全回収。旧第74の不採択/全工学・旧全契約/封印を保持し、P5未開封・品質未達。',''];b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='mri-primary-source-access-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0135.json',dict(latest_completed=NAME,quality_goal_completed=False,next=result['next'],review=b.review_due(),budget=b.reconcile()));print(dict(source_available=available,quality_goal_completed=False,next=result['next']),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','acquire']);a=p.parse_args();globals()[a.stage]()
