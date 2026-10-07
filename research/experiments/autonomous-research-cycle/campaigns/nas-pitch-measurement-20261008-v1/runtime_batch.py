"""272人工条件を全て再生成し、メモリ内archiveをpipeへ返す。"""
from pathlib import Path
import sys,io,json,zipfile,base64
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import generate,verify
def main():
    rows=json.loads(sys.stdin.read());assert len(rows)==272;verify()
    out=io.BytesIO();records=[]
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for spec in rows:
            data,meta=generate(spec)
            archive.writestr(spec['id']+'.wav',data);archive.writestr(spec['id']+'.json',json.dumps(meta,allow_nan=False))
            records.append(dict(id=spec['id'],**meta))
        archive.writestr('manifest.json',json.dumps(dict(records=records,synthesis_calls=272,E0_calls=272)))
    print(base64.b64encode(out.getvalue()).decode())
if __name__=='__main__':main()
