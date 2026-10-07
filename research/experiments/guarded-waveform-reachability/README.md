# 固定支持域を守る実波形F0逆推定比較

承認済み計画に従う開発4文の研究診断。非ニューラルHTS、旧DIO・支持域・4基底を維持し、片側差分と縮小更新だけを比較する。発話別係数は最終共有モデルへ配布しない。

実行環境は既存 `autonomous-speech-synthesis/.venv-eval/bin/python`。campaign、prepare、render、evaluate（各認識器）、summarize、closeout、sealを順に実行する。旧資産は読み取り専用。上限1時間・150MB・render128・AI8・教師/学習/取得0。再生成とASR調整を禁止する。
