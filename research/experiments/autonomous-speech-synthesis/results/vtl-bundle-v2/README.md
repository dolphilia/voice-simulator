# VTL研究用生成bundle

かなまたは音素列と明示アクセントを入力する非ニューラル生成器。固定160Hz・0.20秒/モーラ。日本語の明瞭性・自然さは未資格。`--variant accent-tap` は短い舌尖閉鎖の研究比較。録音、AI重み、発話辞書、保存済み軌跡を含まない。

NumPy/SciPyとmacOS arm64環境が必要。辞書前段は含めない。`JD3.speaker` は全発話で共有する声道形状と音素標的であり、参照録音から生成した発話制御列ではない。

VocalTractLabはGPL-3.0-or-later。添付のLICENSE-VTLとSOURCE.jsonを参照。APIライブラリは公式ソースを変更せずReleaseで構築。
