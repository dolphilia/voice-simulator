# 非ニューラル共有制御の研究bundle

文章をOpen JTalkの辞書・規則で解析し、共有ridge回帰から継続長とF0を計算してVTLで生成する。
教師音声、参照音声、発話ごとの制御軌跡、ニューラル重みは含まない。
`--model direct_non_neural` または `--model distilled_non_neural` を明示して比較する。
音声の品質は未認定。r、u、無声化などの制限は実験報告を参照。

```bash
python runtime.py --text '遠くの鐘が鳴る。' --model distilled_non_neural --output /tmp/nas-example.wav
```

NumPy、SciPy、辞書を導入済みのpyopenjtalkが必要。VTLはGPL-3.0-or-laterで、同梱のLICENSE-VTLとPROVENANCE.jsonを参照。
