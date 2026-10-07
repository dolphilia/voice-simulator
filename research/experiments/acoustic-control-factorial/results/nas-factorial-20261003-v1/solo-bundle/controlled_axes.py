"""F0と速度の変更軸を明示する純粋関数。生成器・学習器は呼ばない。"""
import math

AXES = {'native': (), 'direct_f0_only': ('f0',),
        'direct_duration_only': ('duration',),
        'direct_joint': ('f0', 'duration'), 'distilled_joint': ('f0', 'duration')}


def positive(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(label+'は有限の正数にします')
    return float(value)


def native_settings(requested):
    f0 = positive(requested['requested_f0'], 'F0参照')
    speed = positive(requested['speed'], '指定速度')
    if not 140 <= f0 <= 320 or not .75 <= speed <= 1.3:
        raise ValueError('既存研究版の指定範囲外です')
    return {'speed': speed, 'half_tone': 12*math.log2(f0/220)}


def bounded(speed, shift, axes):
    saturation_axes = []
    if not .5 <= speed <= 2:
        saturation_axes.append('duration')
    if not -12 <= shift <= 12:
        saturation_axes.append('f0')
    return {'speed': max(.5, min(2., speed)), 'half_tone': max(-12., min(12., shift)),
            'unbounded_speed': speed, 'unbounded_half_tone': shift,
            'saturated': bool(saturation_axes), 'saturation_axes': saturation_axes,
            'active_axes': list(axes)}


def validate(variant, requested, target=None, measured=None):
    if variant not in AXES:
        raise ValueError('未登録の方式です')
    native = native_settings(requested)
    if AXES[variant]:
        for name in ('active_seconds', 'f0_hz'):
            positive(target[name], '目標'+name)
            positive(measured[name], '測定'+name)
    return AXES[variant], native


def initial_settings(variant, requested, target=None, calibration=None):
    axes, native = validate(variant, requested, target, calibration)
    speed = calibration['active_seconds']/target['active_seconds'] if 'duration' in axes else native['speed']
    shift = 12*math.log2(target['f0_hz']/calibration['f0_hz']) if 'f0' in axes else native['half_tone']
    return bounded(speed, shift, axes)


def refined_settings(variant, requested, target, previous, measured):
    axes, native = validate(variant, requested, target, measured)
    for name in ('speed', 'half_tone'):
        if type(previous[name]) not in (int, float) or not math.isfinite(previous[name]):
            raise ValueError('補正前の設定が有限ではありません')
    if not .5 <= previous['speed'] <= 2 or not -12 <= previous['half_tone'] <= 12:
        raise ValueError('補正前の設定が制御範囲外です')
    if 'duration' not in axes and previous['speed'] != native['speed']:
        raise ValueError('固定すべき速度が変更されています')
    if 'f0' not in axes and previous['half_tone'] != native['half_tone']:
        raise ValueError('固定すべきF0設定が変更されています')
    speed = previous['speed']*measured['active_seconds']/target['active_seconds'] if 'duration' in axes else native['speed']
    shift = previous['half_tone']+12*math.log2(target['f0_hz']/measured['f0_hz']) if 'f0' in axes else native['half_tone']
    return bounded(speed, shift, axes)
