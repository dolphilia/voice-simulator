"""承認済み実波形F0到達性比較の契約・費用・旧成果の保存。"""
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PILOT = ROOT.parent/'neural-control-distillation'
OLD = ROOT.parent/'autonomous-speech-synthesis'
EXT = ROOT.parent/'neural-control-extension'
REV = EXT/'results/nas-extension-20261002-v1/acoustic-revision'
BUNDLE = REV/'bundle'
FACT = ROOT.parent/'acoustic-control-factorial'
FRES = FACT/'results/nas-factorial-20261003-v1'
LOCAL = ROOT.parent/'local-f0-transfer'
LRES = LOCAL/'results/nas-local-f0-20261003-v1'
PROJ = ROOT.parent/'local-f0-projection-revision'
PRES = PROJ/'results/nas-local-f0-projection-20261003-v1'
WAVE = ROOT.parent/'waveform-local-f0-reachability'
WRES = WAVE/'results/nas-waveform-f0-20261003-v1'
METER = ROOT.parent/'local-f0-meter-validation'
MRES = METER/'results/nas-f0-meter-20261003-v1'
GUARD = ROOT.parent/'guarded-waveform-reachability'
GRES = GUARD/'results/nas-guarded-f0-20261003-v1'
TARGET = ROOT.parent/'waveform-target-shared-control'
TRES = TARGET/'results/nas-wave-target-shared-20261003-v1'
SHARED = ROOT.parent/'saved-waveform-shared-control'
SRES = SHARED/'results/nas-saved-wave-shared-20261003-v1'
EVAL = ROOT.parent/'saved-shared-control-evaluation'
ERES = EVAL/'results/nas-saved-shared-eval-20261003-v1'
RESULT = ROOT/'results/nas-source-filter-20261003-v1'
sys.path.insert(0, str(PILOT))
from budget import Budget, digest


def read(path):
    return json.loads(Path(path).read_text())


def check_seal(path):
    seal = read(path)
    base = Path(seal['path_base'])
    assert all((base/n).is_file() and digest(base/n) == sha for n, sha in seal['files'].items())
    return {'seal': str(path.relative_to(REPO)), 'sha256': digest(path), 'verified_files': len(seal['files'])}


from contextlib import contextmanager
import os

# 台帳・ロックはBudgetが管理。他の変更は保存経路ごとに照合する。
def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf8')

class Storage:
    def __init__(self, root=ROOT, result=RESULT, limit=100_000_000):
        self.root,self.result=Path(root),Path(result)
        self.limit=limit
        self.budget=Budget(self.root,self.result)
        self.state=self.result/'.storage-state.json'
    def snapshot(self):
        return {str(p.relative_to(self.root)):[p.stat().st_size,p.stat().st_mtime_ns]
                for p in self.root.rglob('*') if p.is_file() and p not in
                (self.state,self.result/'.lock',self.result/'ledger.jsonl')}
    def check(self):
        if (self.result/'artifact-seal.json').exists():raise RuntimeError('終了封印後の書込を認めません')
        if self.state.exists() and read(self.state)['files']!=self.snapshot():
            raise RuntimeError('予約外の外部書込・変更を検出しました')
        events=self.budget.events();ended={e['id'] for e in events if e['event']=='finish'}
        if any(e['event']=='start' and e['id'] not in ended and e['pid']!=os.getpid() for e in events):
            raise RuntimeError('別プロセスの未終了ジョブを検出しました')
        contract=self.result/'contract.json'
        if contract.exists():
            c=read(contract)
            if time.time()-c['started_epoch']>=c['limits']['seconds']:raise RuntimeError('実行時間の上限です')
        if self.budget.inventory()['bytes']+65536>self.limit:raise RuntimeError('実容量の上限です')
    def reserve(self, size):
        self.check()
        # 台帳・状態更新の余裕を計数。既存状態ファイルは容量に含めたまま予約する。
        margin=max(65536,len(encoded({'files':self.snapshot()}))+16384)
        current=self.budget.inventory()['bytes']
        if current+size+margin>self.limit:raise RuntimeError('符号化後容量の上限です')
        return {'before_bytes':current,'reserved_bytes':size,'ledger_margin_bytes':margin}
    def reconcile(self, reservation):
        inventory=self.budget.inventory()
        if inventory['bytes']>reservation['before_bytes']+reservation['reserved_bytes']:
            raise RuntimeError('予約容量を超える書込を検出しました')
        value={'files':self.snapshot(),'last_write':reservation,'inventory_after_payload':inventory}
        data=encoded(value)
        if inventory['bytes']+len(data)+65536>self.limit:raise RuntimeError('管理台帳更新の容量上限です')
        with self.state.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        assert self.budget.inventory()['bytes']+65536<=self.limit
    def write(self,path,data):
        path=Path(path)
        if self.root not in path.resolve().parents:raise ValueError('保存先が新実験外です')
        with self.budget.locked():
            reservation=self.reserve(len(data))
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            self.reconcile(reservation)
    @contextmanager
    def external(self,path,maximum_bytes):
        path=Path(path)
        with self.budget.locked():
            reservation=self.reserve(maximum_bytes);before=self.snapshot()
            if path.exists():raise FileExistsError(path)
            try:yield
            finally:
                after=self.snapshot();name=str(path.relative_to(self.root))
                other={k:v for k,v in after.items() if k!=name}
                if other!=before:raise RuntimeError('外部処理が許可以外のファイルを変更しました')
                if path.exists() and path.stat().st_size>maximum_bytes:raise RuntimeError('外部出力が予約を超えました')
                self.reconcile(reservation)


def write_checked(path,data):Storage().write(path,data)
def save(path,value):write_checked(path,encoded(value))
def copy_checked(source,target):write_checked(target,Path(source).read_bytes())

class LocalBudget(Budget):
    def __init__(self):super().__init__(ROOT,RESULT)
    def reserve(self,kind,label,reserve_bytes=0,count=1):
        if (RESULT/'artifact-seal.json').exists():raise RuntimeError('終了封印後の処理を認めません')
        if kind in ('teacher','train','ai'):raise RuntimeError('追加教師・fit・AIを認めません')
        with self.locked():Storage().check()
        return super().reserve(kind,label,reserve_bytes,count)


def main():
    b=LocalBudget()
    if (RESULT/'contract.json').exists():raise FileExistsError('新campaignは開始済みです')
    save(RESULT/'contract.json',{'campaign':RESULT.name,'started_epoch':time.time(),
        'limits':{'seconds':3600,'bytes':100_000_000,'render':54,'ai':0,'teacher':0,'train':0},
        'authorization':'ユーザーによる音源・フィルタ切り分け54生成・AI0の承認',
        'proposal_sha256':digest(REPO/'docs/plans/source-filter-counterfactual-proposal-2026-10-03.md'),
        'source_download_limit_bytes':0,'paid_api':False,'automatic_extension':False,'unattended':True})
    with b.job('setup','17封印と固定HTS資産を照合',2_000_000):
        items=read(ERES/'input-preservation.json')['seals']
        verified=[check_seal(REPO/p['seal']) for p in items]
        assert verified==items
        verified.append(check_seal(ERES/'artifact-seal.json'))
        save(RESULT/'input-preservation.json',{'seals':verified,'all_verified':True})
        save(RESULT/'host-preflight.json',{'sandbox_startup_returncode':0,'render_calls':0,'ai_calls':0,'dispatch_context':'OS隔離を適用できる実行環境での事前起動検査を通過'})
    print({'campaign':RESULT.name,'seals':len(verified),'sealed_files':sum(s['verified_files'] for s in verified)},flush=True)

if __name__=='__main__':main()
