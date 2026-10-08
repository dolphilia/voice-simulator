# 正の断面積による独立二方向声道伝搬

原HTS/MLSA/共有HMMから独立した正規化波primitiveを独自Cで実装した。R=rho*c/Aから反射kと透過sqrt(1-k²)を作り、sectionごとに一標本伝搬する。終端反射.75/-.85と人工geometryを出力前に固定し、結果から利得/係数を選ばない。

静的4形状×2駆動の独立圧力波とエネルギー、8/16/24section一様管の解析delay応答、4形状の独立圧力行列の複素応答、3動的形状×2駆動の独立回転表現・無入力正規化エネルギー・将来入力/形状の前半不変を照合した。不正断面・駆動・終端反射を拒否する。80render/256DSPを保守的に課し返金しない。

48kHz/音速343m/s/24sectionで一様管長17.15cm。人工断面は母音正解ではない。正規化波のpassivityを、移動壁の仕事を含む実圧力エネルギーや生理的調音の資格へ拡張しない。閉鎖/鼻腔/粘性/熱/放射/生理声門/音素指令/日本語は別検証。

一次式: [Julius O. Smith, normalized-scattering](https://www.dsprelated.com/freebooks/pasp/Normalized_Scattering_Junctions.html), [Julius O. Smith, pressure-scattering](https://www.dsprelated.com/freebooks/pasp/Plane_Wave_Scattering.html), [Julius O. Smith, ideal-acoustic-tube](https://www.dsprelated.com/freebooks/pasp/Digital_Waveguide_Models.html)

科学36件の第6回レビュー。通過時は一次測定に基づく共有声道形状/音素指令を別登録し、人工断面を母音正解と扱わず生成制御へ進む。

P5未開封・日本語知覚資格なし・品質未達。旧係数救済と全凍結を保持。
