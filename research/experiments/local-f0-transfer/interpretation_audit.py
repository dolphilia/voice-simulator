"""認識後は係数を変えず、中心化とクリップの識別性だけを純粋関数で監査する。"""
import numpy as np
from campaign import LocalBudget, RESULT, read, save
from local_control import deltas


def main():
    with LocalBudget().job('audit', '形状の共通オフセットと蒸留差の解釈を監査', 1_000_000):
        r = read(RESULT/'training-inputs/development/development-00.json')
        def shape(x, offset=0):
            return np.linspace(-1., 1., len(x))+offset
        base, _ = deltas(r['row'], r['snapshot'], shape)
        offset, _ = deltas(r['row'], r['snapshot'], lambda x: shape(x, 4.))
        assert not np.array_equal(base, offset)
        direct = np.array(read(RESULT/'models/direct_non_neural.json')['coefficients'])
        student = np.array(read(RESULT/'models/distilled_non_neural.json')['coefficients'])
        save(RESULT/'interpretation-audit.json', {'pure_function_fixture': True, 'new_ai_calls': 0,
            'new_render_calls': 0, 'new_training_calls': 0, 'models_or_decisions_changed': False,
            'common_offset_invariance': False, 'fixture': {'input_shape': '等間隔−1〜1半音', 'common_offset': 4.,
                'baseline_state_deltas': base.tolist(), 'offset_state_deltas': offset.tolist()},
            'direct_student_coefficient_l2_difference': float(np.linalg.norm(student-direct)),
            'interpretation': '損失が中心化後の形状を学ぶのに、実行時は中心化前にクリップするため共通オフセットで形状が変わる。特にニューラル経路の比較はこの実装上の制約を含み、ニューラル一般の有用性を否定しない。',
            'future_rule': '別版で中心化を先に行い、最大絶対値へ一括縮尺する不変な射影を事前固定する。今回の結果は変更しない。',
            'quality_certified': False})
        print({'common_offset_invariance': False, 'coefficient_l2_difference': float(np.linalg.norm(student-direct))})


if __name__ == '__main__':
    main()
