"""固定された既知信号だけを各一回生成する。"""
from scipy.io import wavfile
from event_io import *
from event_signal import generate

def main():
    p=verify_protocol();b=LocalBudget();out=[]
    for row in p['rows']:
        record={'id':row['id'],'phase':row['phase'],'status':'failed','render_calls':1}
        try:
            with b.job('render',row['id'],250_000):
                audio,truth,meta=generate(row)
                with np.load(REPO/row['truth']) as ref:
                    assert all(np.array_equal(truth[n],ref[n]) for n in truth)
                buf=BytesIO();wavfile.write(buf,24000,audio);path=RESULT/'render'/f"{row['id']}.wav"
                write_checked(path,buf.getvalue())
                # E0は出力の技術的健全性だけ。内容・自然さを示さない。
                e0={'samples':len(audio),'finite':bool(np.isfinite(audio).all()),'peak':float(np.max(abs(audio))),
                    'first_sample':float(audio[0]),'last_sample':float(audio[-1]),'dc':float(np.mean(audio))}
                assert e0['finite'] and len(audio)==28800 and 0<e0['peak']<.99 and abs(e0['first_sample'])<1e-8 and abs(e0['last_sample'])<1e-8
                record.update(status='completed',wav=str(path.relative_to(REPO)),wav_sha256=digest(path),generator=meta,E0=e0,E0_pass=True)
        except Exception as exc:
            record['error']=repr(exc)
        path=RESULT/'render'/f"{row['id']}.json";save(path,record);out.append({'id':row['id'],'record':str(path.relative_to(REPO)),'sha256':digest(path)})
        print({'render':row['id'],'status':record['status']},flush=True)
    save(RESULT/'render-manifest.json',{'rows':out,'render_calls':len(out),'ai_calls':0,'quality_certified':False})
if __name__=='__main__':main()
