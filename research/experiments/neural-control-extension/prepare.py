"""未知文・指定条件と既存モデルを生成前に固定する。"""
import json
import sys
from campaign import ExtensionBudget,ROOT,PILOT,PRIOR,RESULT,save,digest
sys.path.insert(0,str(PRIOR/'hts-bundle-v2'))
from japanese_frontend import analyze

TEXTS=[
 '薄い雲が山の上を流れる。','昨日は駅の近くで友達を待ちました。',
 '机の引き出しに古い手紙が入っています。','冷たい水で顔を洗いました。',
 '庭の隅で小鳥が餌を探しています。','青い電車が橋を渡ります。',
 '父は毎朝新聞をゆっくり読みます。','夕方になると海から風が吹いてきます。',
 '大きな箱には柔らかい毛布を入れてください。','雨がやんだので窓を少し開けました。',
 '右の道を進むと小さな郵便局があります。','白い皿に焼いた魚を載せました。',
 '今年の春は桜が早く咲きました。','山の向こうに明るい月が見えます。',
 '三つの椅子を部屋の中央に並べます。','本を返したあとで図書館の外を歩きました。']
CONDITIONS=[(180.,.85),(180.,1.15),(260.,.85),(260.,1.15)]


def main():
    budget=ExtensionBudget();budget.initialize()
    with budget.job('setup','追加比較の事前分割・指標・配分を固定',5000000):
        used={r['text'] for r in json.loads((PRIOR/'splits.json').read_text())['rows']}
        used.update(r['text'] for r in json.loads((PRIOR/'hts-transfer/protocol.json').read_text())['rows'])
        for name in ['runtime-audit/contract.json','hts-runtime-audit-v2/contract.json']:
            for t in json.loads((PRIOR/name).read_text())['tests']:used.add(t if isinstance(t,str) else t['text'])
        if len(set(TEXTS))!=16 or set(TEXTS)&used:raise ValueError('未知文の重複')
        bundle=PRIOR/'hts-bundle-v2';manifest=json.loads((bundle/'manifest.json').read_text())
        if any(digest(bundle/name)!=sha for name,sha in manifest['files'].items()):raise ValueError('既存bundleのハッシュ不一致')
        rows=[]
        for i,text in enumerate(TEXTS):
            a=analyze(text)
            if not 1<=len(a['phonemes'])<=120:raise ValueError('音素長が既存制御の範囲外')
            f0,speed=CONDITIONS[i%4]
            rows.append({'id':f'unknown-{i:02d}',**a,'challenge':{'requested_f0':f0,'speed':speed}})
        save(RESULT/'protocol.json',{'rows':rows,'models':['native','direct_non_neural','distilled_non_neural'],
            'conditions':['neutral','challenge'],'neutral':{'requested_f0':220.,'speed':1.},
            'new_model_training':False,'tuning_on_these_rows':False,'source_bundle_manifest_sha256':digest(bundle/'manifest.json'),
            'primary':'両ASRそれぞれで、同じ文/指定条件のnativeに対する集計かなCERが悪化しないこと',
            'aggregation':'全16文と4指定条件別。2条件や複数モデルを別々の独立文として数えない',
            'acoustic_response':'同じモデル・文のneutralに対する実測F0比と活動長比。目標はrequested_f0/220と1/speed',
            'response_diagnostic_tolerance':{'f0_relative':.05,'active_duration_relative':.10},
            'tolerance_scope':'工学的な応答診断。知覚的な非劣性幅として使わない',
            'native_controls':'speedと12log2(requested_f0/220)の半音補正。既定HMMのF0そのものを220Hzと仮定しない',
            'learned_controls':'固定ridge予測の合計時間/時間重み付きF0をHMMへ写像。従来と同じspeed[0.6,1.6]、半音[-6,6]',
            'output_gain':'全方式にmin(1,0.95/peak)を適用、元ピークと利得を保存',
            'planned_counts':{'primary_render_calls':160,'primary_asr':192,'teacher':24,'teacher_asr':48,'ai_reserve':60},
            'teacher_plan':'jf_alphaで未知16文、同じ8文を別の日本語声で診断。教師としての独立性は声の違いだけでは主張しない',
            'quality_status':'独立な日本語知覚評価資格がないため自然さの最終認定は行わない',
            'stop':'比較を凍結して保存。残枠の使用は用途を記録し、上限を自動更新しない'})
        print(json.dumps({'texts':len(rows),'phones':[len(r['phonemes']) for r in rows],'limits':budget.initialize()['limits']},ensure_ascii=False))


if __name__=='__main__':main()
