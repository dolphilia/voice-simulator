"""原観測範囲の不通過を保持し、分布損失の一次式を確認する入口を確保する。"""
import argparse,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
from contextlib import contextmanager
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-viscothermal-primary-source-20261009-v1';NAME='viscothermal-primary-source-v1'
PREV=ROOT/'campaigns/nas-volume-waveguide-coupling-20261009-v1'
URL='https://www.jstage.jst.go.jp/article/ast/29/2/29_2_130/_pdf'
PDFPY='/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
POPPLER='/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm'
SCANNER=r'''"""一次PDF同一性と元本文を確認。数値/機構/音声の採択ではない。"""
import sys,json,os,tempfile
from pathlib import Path
from pypdf import PdfReader
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
pdf=PdfReader(sys.argv[1]);assert len(pdf.pages)==9
texts=[p.extract_text(extraction_mode='layout') for p in pdf.pages];full='\n'.join(texts)
assert 'Hayashi' in texts[0] and 'Miki' in texts[0] and '10.1250/ast.29.130' in full and '2008' in full
Path(sys.argv[2]).write_text(full)
print(json.dumps(dict(passed=True,pages=9,DOI='10.1250/ast.29.130',extracted_layout_bytes=len(full.encode()),all_equations_and_units_visually_verified=False,parameters_or_code_adopted=False)))
'''
@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield j
    except BaseException as exc:b.finish(j,repr(exc));raise
    else:b.finish(j)
def run(cmd,env):return subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=180)
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];v=read(PREV/'aggregate-summary.json');assert not v['adopted'] and v['within_original_observer_domain']==38
    limits=dict(seconds=7200,bytes=200000000,write_bytes=400000000,setup=20,audit=20,render=0,dsp=64,ai=0,teacher=0,train=0,inverse=0,download=2000000)
    reg=dict(campaign=NAME,question='無損失声道の共振と原観測範囲超過を保持し、周波数依存の粘性/熱/壁損失という独立機構の公開一次式と次の検証入口を確保できるか。',previous_seal=digest(PREV/'artifact-seal.json'),prior_SI_all_43_engineering_unverified_and_not_adopted=True,prior_source_RMS_and_observer_limits_geometry_gain_gates_frozen=True,
      primary=dict(title='Approximation method for time-domain simulation of the lossy vocal tract and evaluation of frequency-dependent losses during glottal source flow',authors=['Kyohei Hayashi','Nobuhiro Miki'],journal='Acoust. Sci. Tech. 29(2),130–138(2008)',DOI='10.1250/ast.29.130',article_URL='https://www.jstage.jst.go.jp/article/ast/29/2/29_2_130/_article/-char/en',public_JOURNAL_FREE_ACCESS_banner_read=True,PDF_URL=URL,maximum_bytes=2000000,web_tool_PDF_fetch_denied_by_robots_not_source_HTTP_status=True,one_normal_bounded_public_HTTP_attempt_only=True,no_auth_login_captcha_bypass_contact_or_payment=True,license='©2008 Acoustical Society of Japan。PDF/本文/頁画像は指定外部に私的研究参照として保持し、Git再配布しない。原コード転載なし。数値・式の独自実装は別登録。'),
      scope='取得・9頁/DOI/著者の同一性だけ。全損失式/単位/数値/適用条件/受動因果実現や声道音声の資格ではない。本文を読む前に定数を創作しない。全式を別抽出と目視で確認するまで導入しない。近似器の対象/周波数/公差/費用は出力前の次契約に固定する。',
      estimates=dict(render=0,DSP=4,AI=0,download=2000000,temporary_peak=24000000,temporary_write=48000000,closeout_Git_included=True),limits=limits,controller_sha256=digest(Path(__file__)),protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,
      next_if_available='一次の損失式/伝搬/特性インピーダンス/物理単位を目視と独立抽出で確認し、共有声道に導入する前に、周波数依存損失の別の因果受動実現を全固定条件で資格化する。初回の源振幅/観測範囲を救済しない。',next_if_unavailable='出版元のHTTP/非PDF等を保持し同じ取得を反復/迂回しない。公開一次の損失waveguide/受動フィルタ式など別資料を使い、工学的近似と人の粘性/壁定数の未資格を明示する。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','分布損失の公開一次式/取得範囲/未資格と費用を事前固定',size=1000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'scanner.py',SCANNER.encode(),j);b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={'registration.json':digest(HERE/'registration.json'),'scanner.py':digest(HERE/'scanner.py')},no_waveforms=True),j)
    b.save(ROOT/'progress-0140.json',dict(active_campaign=NAME,next='登録push→公開一次PDFを有限取得→同一性/元式の読取入口を保持→損失の独立検証へ',quality_goal_completed=False,budget=b.reconcile()));print('分布損失の一次式確認入口を事前登録',flush=True)
def acquire():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
    for n,h in c['files'].items():assert digest(HERE/n)==h
    receipt=dict(URL=URL,maximum_bytes=2000000,charged_download=2000000,saved=False)
    with job(b,'download','公開一次損失PDFの有限取得一回のみ',2000000,3000000,90) as j:
        try:
            with urllib.request.urlopen(urllib.request.Request(URL,headers={'User-Agent':'VoiceSimulatorResearch/1.0'}),timeout=45) as f:data=f.read(2000001);receipt.update(status=f.status,final_URL=f.url)
            assert len(data)<=2000000 and data.startswith(b'%PDF-');b.write_data(HERE/'source/hayashi-miki-2008.pdf',data,j);receipt.update(saved=True,bytes=len(data),sha256=digest(HERE/'source/hayashi-miki-2008.pdf'))
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,AssertionError) as exc:receipt.update(error=repr(exc),status=getattr(exc,'code',receipt.get('status')),no_bypass_attempted=True)
        b.save(HERE/'acquisition.json',receipt,j)
    scan=None
    if receipt['saved']:
        with job(b,'dsp','一次損失PDFの同一性/式の読取と二頁画像準備だけ',4,60000000,300) as j:
            with b.workspace(j,'損失一次PDF読取と目視頁の専用一時領域',24000000,48000000) as (work,env):
                scan=json.loads(run([PDFPY,'-B',str(HERE/'scanner.py'),str(HERE/'source/hayashi-miki-2008.pdf'),str(work/'layout.txt')],env).stdout);b.write_data(HERE/'source/layout.txt',(work/'layout.txt').read_bytes(),j)
                for page in (2,3):run([POPPLER,'-f',str(page),'-singlefile','-r','120','-png',str(HERE/'source/hayashi-miki-2008.pdf'),str(work/('page-'+str(page)))],env);b.write_data(HERE/'source'/('page-'+str(page)+'.png'),(work/('page-'+str(page)+'.png')).read_bytes(),j)
            b.save(HERE/'primary-identity-audit.json',scan,j)
    with job(b,'audit','一次損失式の取得可否と全未資格/費用/旧封印/回収を保持',size=2000000) as j:
        for n,h in read(PREV/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        available=bool(scan and scan['passed']);reg=read(HERE/'registration.json');next=reg['next_if_available' if available else 'next_if_unavailable'];result=dict(source_available=available,acquisition=receipt,identity=scan,all_equations_units_and_parameters_verified=False,loss_filter_or_generation_qualified=False,generated_waveforms=0,new_AI=0,protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,next=next);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 分布損失の一次式を確認する公開取得入口','','[Hayashi・Miki 2008](https://www.jstage.jst.go.jp/article/ast/29/2/29_2_130/_article/-char/en)の出版元公開PDFを一回だけ有限取得。web取得ツールのrobots拒否と原HTTPの状態を分ける。無料公開の通常HTTP取得であり、認証/CAPTCHA/料金/連絡なし。','',f'取得/9頁DOI同一性: {available}。HTTP={receipt.get("status")}、費用2Mbytes、新WAV0/AI0。全損失式、単位、物理定数、受動/因果近似、生成器、日本語音声はまだ未資格。','',reg['scope'],'',reg['primary']['license'],'',next,'','全初回取得費を返金せず、全自分一時領域を指定外部から回収。旧SI観測範囲38/43と工学未確認/不採択、全旧凍結を保持。P5未開封・品質未達。',''];b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();camp=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp);b.save(HERE/'cost-audit.json',dict(counts=camp['counts'],seconds=s['seconds']-camp['start_seconds'],write_bytes=s['write_bytes']-camp['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='viscothermal-primary-source-access-completed',active_campaign=None,next=next,git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0141.json',dict(latest_completed=NAME,next=next,review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(source_available=available,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','acquire']);a=p.parse_args();globals()[a.stage]()
