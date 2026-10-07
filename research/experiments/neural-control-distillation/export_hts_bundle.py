"""固定共有モデルと小さい古典HMM音源を、許可リストに従って移出する。"""
import ast
import importlib.metadata
import json
from pathlib import Path
import shutil
from budget import Budget,ROOT,RESULT,save,digest


def extract(path,names):
    tree=ast.parse(path.read_text())
    return '\n\n'.join(ast.unparse(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names)


def main():
    import pyopenjtalk
    with Budget().job('setup','HMM版の非ニューラル移出',10_000_000):
        target=RESULT/'hts-bundle-v2';target.mkdir(exist_ok=False)
        source=RESULT/'bundle'
        # 先に隔離検証した前段と、凍結済みの同一モデルをコピーする。
        for name in ('direct_non_neural.json','distilled_non_neural.json','japanese_frontend.py','shared_control.py','renderer.py'):
            shutil.copy2(source/name,target/name)
        for name in ('hts_runtime.py','acoustics.py'):
            shutil.copy2(ROOT/name,target/name)
        core='"""HMM生成と信号測定。教師や参照データを参照しない。"""\nimport numpy as np\nfrom scipy import signal\nfrom acoustics import estimate_f0, acoustic_features\nfrom shared_control import predict\n\n'
        core+=extract(ROOT/'hts_transfer.py',{'render_hts','aggregate_settings'})+'\n\n'
        core+=extract(ROOT/'fit_controls.py',{'measure'})+'\n'
        (target/'hts_core.py').write_text(core)
        voice=Path(pyopenjtalk.__file__).parent/'htsvoice/mei_normal.htsvoice'
        shutil.copy2(voice,target/voice.name)
        shutil.copy2(RESULT/'hts-provenance.json',target/'HTS-PROVENANCE.json')
        # 配布元の既存ライセンス本文を同梱する。
        license_path=voice.parent/'LICENSE_mei_normal.htsvoice'
        if not license_path.is_file():
            license_path=next(p for p in voice.parent.iterdir() if 'COPYING' in p.name or 'LICENSE' in p.name)
        shutil.copy2(license_path,target/'LICENSE-HTSVOICE')
        (target/'README.md').write_text('''# 非ニューラルHMM制御の研究bundle

日本語を辞書・規則で解析し、共有ridge回帰から発話全体の長さとF0を予測する。
小さい古典HMM音源（Mei normal）で一度校正用の音を生成し、速度と半音補正を指定して再生成する。
校正用の波形は検索・再生・加工しない。音素ごとの韻律はHMM側に残る。
直接学習とニューラルから蒸留した回帰の両方を比較できる。ニューラル重みや録音は含まない。

```bash
python hts_runtime.py --text '遠くの鐘が鳴る。' --model distilled_non_neural --output /tmp/hts-example.wav
```

Python 3.11、NumPy、SciPy、辞書導入済みのpyopenjtalkが必要。
HMM音源は Copyright 2009–2013 Nagoya Institute of Technology、CC BY 3.0。LICENSE-HTSVOICE、HTS-PROVENANCE.jsonを参照。
自然さは未認定。4文での小規模比較を広い日本語性能の証明に使わない。
v2は出力ピークが0.95を超える場合に全区間の利得を一様に下げ、利得と元のピークを記録する。
''')
        save(target/'PROVENANCE.json',{'dependencies':{n:importlib.metadata.version(n) for n in ('numpy','scipy','pyopenjtalk')},
            'source_model_selection_sha256':digest(RESULT/'model-selection.json'),
            'runtime_neural':False,'recorded_audio_included':False,'per_utterance_lookup':False,
            'synthesis_calls_per_utterance':2,'model_size_depends_on_training_utterance_count':False,
            'fixed_classical_voice_sha256':digest(voice),'platform':'macOS arm64 Python 3.11のみ実証'})
        files={str(p.relative_to(target)):digest(p) for p in sorted(target.rglob('*')) if p.is_file()}
        save(target/'manifest.json',{'files':files,'runtime_neural':False,'contains_recorded_audio':False,
            'parameters_per_regression':len(json.loads((target/'distilled_non_neural.json').read_text())['coefficients'])*2})
        print(json.dumps({'files':len(files),'bytes':sum(p.stat().st_size for p in target.rglob('*') if p.is_file())}))


if __name__=='__main__':main()
