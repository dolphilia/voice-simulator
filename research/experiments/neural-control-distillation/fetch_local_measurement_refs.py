"""局所信号測定の外部資料を上限付きで取得し、ログイン先は追跡しない。"""
import json
import argparse
from pathlib import Path
import urllib.request
import zipfile
from post_pilot import PostBudget,POST
from budget import save,digest

SOURCES={
 'haskins-vot.wav.zip':'https://www.haskinslaboratories.org/s/VOT_Audio_WAV.zip',
 'paidologos-data.html':'https://talkbank.org/data/phon/Japanese/PaidoJapanese?f=zip',
 'paidologos-media.html':'https://media.talkbank.org/phon/Japanese/PaidoJapanese'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='1',choices=['1','2'])
    args=parser.parse_args()
    rows=[];out=POST/('local-measurement-references-'+args.attempt)
    with PostBudget().job('setup','局所測定の公開資料を取得',25000000):
        out.mkdir(exist_ok=False)
        for name,url in SOURCES.items():
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'voice-simulator-research/1.0'})
                with urllib.request.urlopen(req,timeout=30) as response:
                    final=response.url;content_type=response.headers.get('Content-Type')
                    data=response.read(15000001)
                if len(data)>15000000:raise ValueError('個別取得上限15MBを超過')
                (out/name).write_bytes(data)
                rows.append({'url':url,'final_url':final,'content_type':content_type,'bytes':len(data),'path':name,'sha256':digest(out/name),'status':'retrieved'})
            except Exception as e:rows.append({'url':url,'status':'unavailable','error':repr(e)})
        p=out/'haskins-vot.wav.zip'
        if p.is_file() and zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                entries=[i for i in z.infolist() if i.filename.lower().endswith('.wav')]
                if sum(i.file_size for i in entries)>15000000:raise ValueError('展開上限15MBを超過')
                for i in entries:
                    name=Path(i.filename).name
                    if name.startswith('._'):continue
                    dest=out/'wav'/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(z.read(i))
                rows.append({'archive':p.name,'wav_entries':len(entries),'scope':'外部の合成VOT連続体。日本語の自然さ/音素分類の資格とは別',
                    'source_page':'https://www.haskinslaboratories.org/vot','license':'公開ダウンロード資料。再配布ライセンスの明記は未確認、研究比較のみ・最終bundleへ含めない',
                    'expected':'公称−150〜150ms、10ms間隔、+140ms欠落。+30/+50/+90/+100/+110msに約5msの長さ差の注記'})
        save(out/'provenance.json',{'rows':rows})
        print(json.dumps(rows,ensure_ascii=False))


if __name__=='__main__':main()
