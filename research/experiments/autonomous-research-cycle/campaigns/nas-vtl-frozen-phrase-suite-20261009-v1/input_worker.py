"""既知の非保護履歴だけで、有限語群を音声出力前に選別する。"""
import sys,json,re,unicodedata,os,tempfile,hashlib
from pathlib import Path
repo=Path(sys.argv[1]);native=Path(sys.argv[2]);config=json.loads(Path(sys.argv[3]).read_text())
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(native));from japanese_frontend import analyze
import pyopenjtalk
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(t):return re.sub(r'[\W_]','',unicodedata.normalize('NFKC',t))
texts=set();labels=set()
def collect(x):
 if isinstance(x,dict):
  if isinstance(x.get('text'),str):texts.add(norm(x['text']))
  if x.get('full_context_labels'):labels.add(tuple(x['full_context_labels']))
  for z in x.values():collect(z)
 elif isinstance(x,list):
  for z in x:collect(z)
for n,h in config['history'].items():
 assert not re.search('splits|protected|holdout|final.confirm',n,re.I) and n.endswith('protocol.json')
 p=repo/n;assert digest(p)==h;collect(json.loads(p.read_text()))
rows=[];audit=[]
for length,wanted in [('short',3),('long',4)]:
 selected=[]
 for text in config['pool'][length]:
  row=analyze(text);kana=pyopenjtalk.g2p(text,kana=True)
  actual=[re.search(r'\-([^+]+)\+',v).group(1) for v in row['full_context_labels']]
  moras=''.join(chr(ord(c)-96) if 'ァ'<=c<='ヶ' else c for c in unicodedata.normalize('NFKC',kana))
  supported=set('あいうえおかきくけこたちつてとさしすせそ')
  valid=len(moras)==wanted and set(moras)<=supported and actual[0]==actual[-1]=='sil' and set(actual[1:-1])<=set(['a','i','u','e','o','I','U','k','t','s','sh','ch','ts'])
  collision=norm(text) in texts or tuple(row['full_context_labels']) in labels
  choose=valid and not collision and len(selected)<4
  audit.append(dict(text=text,kana=kana,length=length,phones=actual,collision=collision,supported=valid,selected=choose))
  if choose:
   row.update(kana=kana,moras=moras,phones=actual,length=length,challenge_group=len(selected),id='vtl-phrase-'+str(len(rows)+len(selected)).zfill(2),role='未使用選別診断。P5ではなく、知覚/一般化の資格ではない。')
   selected.append(row);texts.add(norm(text));labels.add(tuple(row['full_context_labels']))
 assert len(selected)==4,('初出力前の入力不足',length,audit)
 rows.extend(selected)
print(json.dumps(dict(rows=rows,audit=audit,history=config['history'],P5_opened=False),ensure_ascii=False,allow_nan=False))
