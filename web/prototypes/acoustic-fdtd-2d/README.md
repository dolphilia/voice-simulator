# 2D Acoustic FDTD Prototype

線形音響方程式に近い `p + vx/vy` の staggered grid FDTD で、2D の音波伝搬を可視化する Web プロトタイプです。

## 起動

```bash
npm install
npm run dev
```

開発サーバーは `http://localhost:5176` です。

## できること

- 音源セル、耳セル、壁セルを Canvas 上に配置
- 完全反射、吸音、透過、散乱、高域吸音の壁種別を選択
- 赤/青で音圧の正負を可視化
- 外周の単純吸音層で端反射を軽減
- 耳セルで拾った圧力波形を録音し、Web Audio API で再生

## 実装メモ

調査と設計方針は `docs/plans/acoustic-fdtd-2d-prototype-plan.md` を参照してください。
