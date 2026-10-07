"""公式ReazonSpeechの固定量子化版を独立診断用に取得する。"""
import subprocess
import sys
import urllib.request
from budget import Budget,ROOT,RESULT,save,digest

REV='291488c8151be24d7da4bf7af26e533fad96e407'
FILES={
 'encoder-epoch-99-avg-1.int8.onnx':(154670139,'2c7bd08a8a99f9ddd0d9e458456577b1f6279214e51426f114f9eced44c54e1d'),
 'decoder-epoch-99-avg-1.int8.onnx':(2959337,'8f0bff94d38797b03b762634ed03211a8e303d06cc4603cdd0cf4199d6eb1485'),
 'joiner-epoch-99-avg-1.int8.onnx':(2696970,'49cc7ea1d3d35a40a27442db5e89996da64bf0e683a903dce76e99e57a12e4de'),
 'tokens.txt':(45754,None),'README.md':(1188,None)}


def main():
    budget=Budget();records=[]
    for name,(size,expected) in FILES.items():
        path=ROOT/'.cache/reazonspeech'/name
        url=f'https://huggingface.co/reazon-research/reazonspeech-k2-v2/resolve/{REV}/{name}'
        with budget.job('setup','独立ASR取得/'+name,size+100000):
            path.parent.mkdir(parents=True,exist_ok=True)
            total=0
            with urllib.request.urlopen(url,timeout=60) as r,path.open('xb') as f:
                while chunk:=r.read(1024*1024):
                    total+=len(chunk)
                    if total>size:raise ValueError('公式容量を超えました')
                    f.write(chunk)
            sha=digest(path)
            if total!=size or (expected is not None and sha!=expected):
                raise ValueError('公式の容量/hashと一致しません')
            records.append({'path':str(path.relative_to(ROOT)),'url':url,'bytes':total,'sha256':sha})
            print(name,total,flush=True)
    with budget.job('setup','独立ASR推論ライブラリ',150_000_000):
        command=[sys.executable,'-m','pip','install','--no-cache-dir','--target',str(ROOT/'.cache/packages'),
                 'sherpa-onnx==1.13.8']
        r=subprocess.run(command,text=True,capture_output=True,timeout=600)
        save(RESULT/'second-asr-install.json',{'command':command,'returncode':r.returncode,
                                             'stdout':r.stdout,'stderr':r.stderr})
        r.check_returncode()
    save(RESULT/'second-asr-provenance.json',{'model':'reazon-research/reazonspeech-k2-v2',
        'revision':REV,'license':'Apache-2.0','files':records,'runtime':'sherpa-onnx 1.13.8 CPU int8',
        'purpose':'Whisperと異なる日本語Zipformerの診断。音声最適化やモデル選択には使用しない',
        'qualification':'naturalnessは評価しない。学習資料の完全な重複排除も未証明'})


if __name__=='__main__':main()
