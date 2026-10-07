"""実験の診断改善と独立した品質認定を区別する判定器。"""
import math


def decide(evidence):
    """改善方向を損失（小さいほど良い）へ統一した契約を検査する。"""
    if evidence.get('engineering_pass') is not True:
        return {'state': 'rejected', 'reason': '工学条件に未達または証拠不足'}
    if evidence.get('runtime_non_neural_verified') is not True:
        return {'state': 'inconclusive', 'reason': '最終実行経路の独立性が未検証'}
    confirmation = evidence.get('confirmation', {})
    if (confirmation.get('frozen_before_selection') is not True or
            confirmation.get('independent') is not True or
            confirmation.get('reused_for_tuning') is not False or
            not confirmation.get('source_manifest_sha256')):
        return {'state': 'inconclusive', 'reason': '独立確認の契約・来歴が不足'}
    for name in ('content', 'prosody', 'perception'):
        item = evidence.get('metrics', {}).get(name, {})
        qualification = item.get('qualification', {})
        if (qualification.get('status') != 'qualified' or
                qualification.get('target_domain') != 'japanese-non-neural-speech' or
                not qualification.get('evidence_sha256')):
            return {'state': 'inconclusive', 'reason': f'{name} の対象領域の資格が不足'}
        bounds, margin = item.get('loss_delta_ci'), item.get('noninferiority_margin')
        if (not isinstance(bounds, list) or len(bounds) != 2 or
                any(type(x) not in (float, int) or not math.isfinite(x) for x in bounds) or
                type(margin) not in (float, int) or not math.isfinite(margin) or margin < 0 or
                bounds[0] > bounds[1] or item.get('multiplicity_controlled') is not True or
                item.get('missing_count') != 0 or item.get('protection_pass') is not True):
            return {'state': 'inconclusive', 'reason': f'{name} の区間・保護条件・欠損検査が不足'}
        if bounds[1] > margin:
            return {'state': 'rejected', 'reason': f'{name} が事前の非劣性条件に未達'}
    return {'state': 'autonomously-validated',
            'reason': '独立した実音声証拠が全ての凍結済み契約を満たす'}
