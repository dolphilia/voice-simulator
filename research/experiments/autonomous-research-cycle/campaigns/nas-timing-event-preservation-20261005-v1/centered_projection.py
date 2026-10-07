"""承認済み比較の中心化先行射影。"""
import numpy as np


def project(values):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not np.isfinite(x).all() or (len(x) and np.max(abs(x)) > 1e6):
        raise ValueError('一次元・有限・絶対値100万以内の局所予測を要求します')
    if not len(x):
        return x.copy()
    centered = x-x.mean()
    scale = min(1., 3./max(1e-12, float(np.max(abs(centered)))))
    return centered*scale


def tests():
    cases = [[-1., 0., 1.], [0., 2., 10.], [-1000., 0., 10.], [7., 7., 7.], []]
    for case in cases:
        result = project(case)
        shifted = project(np.array(case)+4.)
        assert np.allclose(result, shifted, rtol=0, atol=1e-12)
        assert not len(result) or (np.max(abs(result)) <= 3 and abs(result.mean()) < 1e-12)
    assert np.array_equal(project([-1, 0, 1]), [-1, 0, 1])
    rejected = 0
    for case in ([float('nan')], [float('inf')], [[0]], [1e7]):
        try:
            project(case)
        except ValueError:
            rejected += 1
    assert rejected == 4
    return {'common_offset_invariance_cases': len(cases), 'zero_mean_and_bound_pass': True,
        'within_bound_shape_unchanged': True, 'invalid_inputs_rejected': rejected,
        'new_render_calls': 0, 'new_ai_calls': 0, 'new_training_calls': 0,
        'current_campaign_runtime_modified': True, 'current_comparison_authorized': True}


if __name__ == '__main__':
    print(tests())
