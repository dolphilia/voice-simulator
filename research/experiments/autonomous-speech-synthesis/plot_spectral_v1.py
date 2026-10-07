#!/usr/bin/env python3
"""完了した選別話者比較を可視化する。音声生成・最適化・追加評価はしない。"""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
# フォントキャッシュは書き込み可能な一時領域へ置く。
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'voice-spectral-matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path(tempfile.gettempdir()) / 'voice-spectral-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
sys.path.insert(0, str(ROOT / 'src'))
from autonomous_speech_synthesis.io import read, write_once, file_hash


def main():
    source = ROOT / 'results/ans-spectral-multistart-v1/speaker-comparison.json'
    data = read(source)
    if data['promotion_allowed'] or data['quality_goal_achieved']:
        raise ValueError('この図は品質昇格を主張しない診断集計だけを扱います')
    rows = [r for r in data['rows'] if 'selection_speaker_rows' in r]
    output = ROOT / 'results/spectral-analysis-v1'
    output.mkdir(exist_ok=True)
    targets = [output / ('selection-residual.' + suffix) for suffix in ('png', 'svg')]
    if any(p.exists() for p in targets) or (output / 'figure-data.json').exists():
        raise FileExistsError('完成済みまたは途中の図を上書きしません')
    plt.rcParams['font.family'] = ['Hiragino Sans', 'Noto Sans CJK JP', 'DejaVu Sans']
    fig, axis = plt.subplots(figsize=(11, 8.4))
    colors = {'shared': '#1766A6', 'free': '#C55A16'}
    labels = {'shared': '共有規則', 'free': '条件別適合'}
    chart_rows = []
    for index, row in enumerate(rows):
        record = {'task': row['task'], 'speakers': len(row['selection_speaker_rows'])}
        for kind, offset in [('shared', -.13), ('free', .13)]:
            values = np.array([s[kind] for s in row['selection_speaker_rows']])
            mean = float(values.mean()); low = float(values.min()); high = float(values.max())
            record[kind] = {'mean': mean, 'min': low, 'max': high}
            axis.errorbar(mean, index + offset, xerr=[[mean-low], [high-mean]],
                          fmt='o', color=colors[kind], capsize=3, markersize=5,
                          label=labels[kind] if index == 0 else None)
        chart_rows.append(record)
    axis.set_yticks(range(len(rows)), [r['task'].replace('vowel-', '/') .replace('-', '/ ') +
                     f" Hz  (n={len(r['selection_speaker_rows'])})" for r in rows])
    axis.invert_yaxis(); axis.set_xlim(left=0)
    axis.set_xlabel('選別話者への平滑対数スペクトル残差（二乗平均・小さいほど近い）')
    axis.grid(axis='x', alpha=.18)
    axis.legend(loc='upper right', frameon=False)
    axis.set_title('静的母音の適合：選別話者ごとの残差', pad=18, fontsize=16)
    fig.text(.03, .045, '点：話者を等重みとした平均　横線：観測した話者の最小〜最大（信頼区間ではない）', fontsize=10)
    fig.text(.03, .019, '/u/ 160 Hzは選別話者不足で除外。相対利得に制約があるモデルの診断であり、自然さの合格判定ではない。', fontsize=10)
    fig.tight_layout(rect=(0, .075, 1, 1))
    for target in targets:
        fig.savefig(target, dpi=160)
    plt.close(fig)
    write_once(output / 'figure-data.json', {
        'rows': chart_rows, 'source_sha256': file_hash(source),
        'script_sha256': file_hash(Path(__file__)),
        'figures': {p.name: file_hash(p) for p in targets},
        'additional_audio_renders': 0, 'additional_AI_evaluations': 0,
        'scope': '保存済みの選別話者別残差を表示。話者内の3seedは独立標本として数えない。',
    })
    print('選別残差の図を保存しました:', output)


if __name__ == '__main__':
    main()
