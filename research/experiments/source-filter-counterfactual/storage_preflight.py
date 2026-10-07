"""次案の保存前検査。既存生成器へ接続せず純粋関数として点検する。"""
import json


def compact_row(row,source_path,source_sha256):
    fields=('id','text','variant','condition','length','challenge_group','split','status','wav','wav_sha256')
    output={k:row[k] for k in fields if k in row}
    output.update(source_record=source_path,source_record_sha256=source_sha256)
    return output


def encoded_bytes(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')


def check(current_bytes,prospective_bytes,limit_bytes,margin=65536):
    if any(type(x) is not int or x<0 for x in (current_bytes,prospective_bytes,limit_bytes,margin)):
        raise ValueError('容量と余裕は非負整数で指定します')
    if current_bytes+prospective_bytes+margin>limit_bytes:
        raise RuntimeError('保存前の容量上限です')
    return True


def tests():
    rejected=0
    for current,size in [(250000000,235490836),(300000000,60000000),(350000000,1)]:
        try:check(current,size,350000000)
        except RuntimeError:rejected+=1
    assert rejected==3 and check(300000000,100000,350000000)
    r={'id':'x','text':'試験','status':'completed','wav':'x.wav','wav_sha256':'s','state_snapshot_before':[0]*1000,'state_snapshot_after':[0]*1000}
    c=compact_row(r,'x.json','sha');assert 'state_snapshot_before' not in c and 'state_snapshot_after' not in c
    assert len(encoded_bytes(c))<len(encoded_bytes(r)) and c['source_record_sha256']=='sha'
    return {'large_manifest_rejected_before_write':True,'margin_enforced':True,'compact_manifest_references_preserved':True,
        'production_writer_modified':False,'new_generation_calls':0,'new_ai_calls':0,'new_shared_fits':0}

if __name__=='__main__':print(tests())
