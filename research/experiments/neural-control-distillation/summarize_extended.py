"""追加対照、共有制御への移行、未知文の範囲を実ファイルから集計する。"""
import json
import argparse
from collections import defaultdict
import numpy as np
from scipy import signal
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest


def content(directory):
    groups=defaultdict(list)
    for p in sorted((RESULT/directory).glob('*/*.json')):
        r=json.loads(p.read_text())
        if digest(r['wav'])!=r['wav_sha256']:raise ValueError('評価音声のハッシュ不一致')
        groups[r['variant']].append(r)
    return {k:{'utterances':len(v),'errors':sum(r['errors'] for r in v),'characters':sum(r['characters'] for r in v),
               'kana_cer_micro':sum(r['errors'] for r in v)/sum(r['characters'] for r in v),
               'rows':[{'id':r['id'],'hypothesis':r['hypothesis'],'kana_cer':r['kana_cer']} for r in v]} for k,v in groups.items()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='extended-comparison-summary.json')
    args=parser.parse_args()
    with Budget().job('audit','補助対照と適用範囲の集計',5_000_000):
        result={'asr':{d:content(d) for d in ['supplemental-content','second-asr','transfer-content','transfer-second-asr',
                                            'transfer-gain-content','transfer-gain-second-asr']}}
        for directory in ('transfer-gain-content','transfer-gain-second-asr'):
            if sum(v['utterances'] for v in result['asr'][directory].values())!=16:
                raise ValueError('利得修正後の内容比較に欠損があります')
        rows=json.loads((RESULT/'hts-transfer/protocol.json').read_text())['rows']
        variants=['baseline','direct_non_neural','neural_control','distilled']
        transfer={}
        for v in variants:
            recs=[json.loads((RESULT/'hts-transfer'/r['id']/f'{v}.json').read_text()) for r in rows]
            transfer[v]={'objective_mean':float(np.mean([r['objective'] for r in recs])),
                'engineering_pass':all(r['evaluation']['E0_pass'] for r in recs),
                'objective_by_utterance':{r['id']:r['objective'] for r in recs}}
        result['hts_transfer']=transfer
        result['hts_transfer_scope']='4文の後続診断。直接/ニューラル対照は結果閲覧後に追加した固定モデルで、再学習・調整なし。確証的検定はしない'
        primary=json.loads((RESULT/'splits.json').read_text())['rows']
        train=[r for r in primary if r['split']=='development']
        def words(rs):return {w['orig'] for r in rs for w in r['features'] if w['pos'] not in ('記号','助詞','助動詞')}
        def trigrams(r):
            phones=['<s>',*r['phonemes'],'</s>'];return set(zip(phones,phones[1:],phones[2:]))
        seen_words=words(train);seen_contexts=set().union(*(trigrams(r) for r in train))
        coverage={}
        for split in ['selection','audit']:
            group=[r for r in primary if r['split']==split]
            voc=words(group);ctx=set().union(*(trigrams(r) for r in group))
            coverage[split]={'utterances':len(group),'content_word_types':len(voc),'unseen_content_word_types':len(voc-seen_words),
                 'shared_content_words':sorted(voc&seen_words),'phoneme_trigram_types':len(ctx),'unseen_phoneme_trigram_types':len(ctx-seen_contexts),
                 'unseen_phonemes':sorted(set(p for r in group for p in r['phonemes'])-set(p for r in train for p in r['phonemes']))}
        result['generalization_coverage']=coverage
        result['coverage_limit']='文章は非重複だが、語彙・文脈の完全非重複ではない。学習音声のF0/速度も単一設定で、隔離試験だけから速度別品質は主張しない'
        spectra=[]
        for row in primary:
            if row['split']!='audit':continue
            fs,x=wavfile.read(RESULT/'teacher'/f'{row["id"]}.wav')
            fy,y=wavfile.read(RESULT/'world'/f'{row["id"]}.wav')
            if fs!=fy:raise ValueError('標本化周波数の不一致')
            n=min(len(x),len(y));x=x[:n].astype(float);y=y[:n].astype(float)
            measurements=[]
            for fft in [256,512,1024]:
                a=np.abs(signal.stft(x,fs,nperseg=fft,noverlap=fft*3//4)[2])
                b=np.abs(signal.stft(y,fs,nperseg=fft,noverlap=fft*3//4)[2])
                measurements.append({'fft':fft,'spectral_convergence':float(np.linalg.norm(a-b)/np.linalg.norm(a)),
                    'mean_abs_log_magnitude':float(np.mean(np.abs(np.log(a+1e-5)-np.log(b+1e-5))))})
            world=np.load(RESULT/'world'/f'{row["id"]}.npz')
            f0=world['f0']
            spectra.append({'id':row['id'],'same_timeline_seconds':n/fs,'metrics':measurements,
                            'world_voiced_frame_fraction':float(np.mean(f0>0)),
                            'world_voiced_f0_median':float(np.median(f0[f0>0]))})
        result['world_spectrum']=spectra
        result['world_spectrum_scope']='同一時間軸の分析再合成のみ。末尾の長さ差は短い方に限定、時間伸縮・DTWなし。声門位相差も距離へ入るため自然さの指標ではない'
        result['unmeasured']={'VOT':'音素開放と有声開始の独立した基準整列がなく、指令時刻を実測と取り違えないため未認定',
            'transition':'音素境界の正解と信頼性を確認した局所遷移測定がない。全体F0/長さだけで改善を主張しない',
            'naturalness':'日本語の当該非ニューラル方式に資格がある知覚指標・非劣性幅がなく、未認定'}
        result['hts_gain_repair']={
            'engineering_pass':all(json.loads(p.read_text())['evaluation']['E0_pass'] for p in (RESULT/'hts-transfer-gain-v2').glob('new-*/*.json')),
            'render_summary':json.loads((RESULT/'hts-transfer-gain-v2/render-summary.json').read_text()),
            'runtime_content_check':'ASR入力構築の変数衝突で1予約失敗。コードを修正し、残枠は4文の利得修正比較へ配分したため、runtime専用2文は内容評価未実施'}
        save(RESULT/args.output,result)
        print(json.dumps({'hts_transfer':transfer,'coverage':coverage},ensure_ascii=False))


if __name__=='__main__':main()
