"""許可リストで共有制御・規則前段・物理モデルだけを移出する。"""
import ast
import importlib.metadata
import json
import shutil
from budget import Budget,ROOT,RESULT,save,digest

OLD=ROOT.parent/'autonomous-speech-synthesis'


def main():
    with Budget().job('setup','非ニューラルbundleの移出',20_000_000):
        target=RESULT/'bundle'
        target.mkdir(exist_ok=False)
        selection=json.loads((RESULT/'model-selection.json').read_text())
        for name in ('direct_non_neural','distilled_non_neural'):
            model=selection['chosen'][name]
            if digest(ROOT/model['path'])!=model['sha256']:
                raise ValueError('凍結したモデルと一致しません')
            shutil.copy2(ROOT/model['path'],target/f'{name}.json')
        for name in ('runtime.py','renderer.py','shared_control.py'):
            shutil.copy2(ROOT/name,target/name)
        shutil.copy2(OLD/'japanese_frontend.py',target/'japanese_frontend.py')
        old_bundle=OLD/'results/vtl-bundle-v2'
        tree=ast.parse((old_bundle/'generator.py').read_text())
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Backend')
        (target/'backend.py').write_text('"""VTLの非ニューラルC ABIを読み込む。"""\nimport ctypes as ct\nfrom pathlib import Path\n\n'+ast.unparse(cls)+'\n')
        for name in ('JD3.speaker','libVocalTractLabApi.dylib','LICENSE-VTL'):
            shutil.copy2(old_bundle/name,target/name)
        save(target/'PROVENANCE.json',{
            'VTL':json.loads((old_bundle/'SOURCE.json').read_text()),
            'model_selection_sha256':digest(RESULT/'model-selection.json'),
            'teacher_in_runtime':False,'per_utterance_lookup':False,
            'model_kind':'固定された100程度の文脈特徴から、継続長/F0の補正を求めるridge回帰',
            'scope':'移行可能性を調べる研究版。品質を認定した配布版ではない',
            'dependencies':{name:importlib.metadata.version(name) for name in ('numpy','scipy','pyopenjtalk')},
            'platform':'macOS arm64、Python 3.11。移植性の認定は行っていない'})
        (target/'README.md').write_text('''# 非ニューラル共有制御の研究bundle

文章をOpen JTalkの辞書・規則で解析し、共有ridge回帰から継続長とF0を計算してVTLで生成する。
教師音声、参照音声、発話ごとの制御軌跡、ニューラル重みは含まない。
`--model direct_non_neural` または `--model distilled_non_neural` を明示して比較する。
音声の品質は未認定。r、u、無声化などの制限は実験報告を参照。

```bash
python runtime.py --text '遠くの鐘が鳴る。' --model distilled_non_neural --output /tmp/nas-example.wav
```

NumPy、SciPy、辞書を導入済みのpyopenjtalkが必要。VTLはGPL-3.0-or-laterで、同梱のLICENSE-VTLとPROVENANCE.jsonを参照。
''')
        files={str(p.relative_to(target)):digest(p) for p in sorted(target.rglob('*')) if p.is_file()}
        save(target/'manifest.json',{'files':files,'runtime_neural':False,'contains_recorded_audio':False,
             'parameter_count_per_model':{name:len(json.loads((target/f'{name}.json').read_text())['coefficients'])*2
                                          for name in ('direct_non_neural','distilled_non_neural')}})
        print(json.dumps({'files':len(files),'bytes':sum(p.stat().st_size for p in target.rglob('*') if p.is_file())}))


if __name__=='__main__':
    main()
