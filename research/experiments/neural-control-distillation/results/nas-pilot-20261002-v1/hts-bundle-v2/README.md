# 非ニューラルHMM制御の研究bundle

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
