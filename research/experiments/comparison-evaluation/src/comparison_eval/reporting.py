from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .manifest import ManifestRecord


def manifest_report(records: list[ManifestRecord], baseline: dict[str, Any] | None = None) -> str:
    splits = Counter(record.split for record in records)
    speakers = defaultdict(set)
    labels = defaultdict(set)
    kinds = Counter(record.kind for record in records)
    licenses = Counter(record.license for record in records)
    for record in records:
        speakers[record.split].add(record.speaker_id)
        labels[record.split].add(record.label)
    lines = [
        "# 比較評価データ監査レポート",
        "",
        "このレポートは manifest と calibration 基準分布から自動生成した。音声の再配布可否や知覚品質を保証するものではない。",
        "",
        "## データ構成",
        "",
        "| split | サンプル | 話者 | ラベル |",
        "| --- | ---: | ---: | --- |",
    ]
    for split in ("development", "calibration", "holdout"):
        lines.append(f"| {split} | {splits[split]} | {len(speakers[split])} | {', '.join(sorted(labels[split])) or '-'} |")
    lines.extend(["", f"- 種別: {dict(kinds)}", f"- ライセンス表記: {dict(licenses)}", ""])
    warnings = []
    if len(kinds) == 1 and "human" in kinds:
        warnings.append("参照は人間音声だけで、生成方式・解析fixtureとの比較タスクは別途必要。")
    if all("utau" in record.sample_id for record in records):
        warnings.append("人間参照がUTAU音源に偏っており、収録環境、演技、性別・年齢、方言の代表性は限定的。")
    if len(speakers["holdout"]) < 2:
        warnings.append("holdout話者が2未満のため、未知話者への一般化を強く主張できない。")
    if any(len(labels[split]) < 5 for split in splits):
        warnings.append("一部splitで5母音を満たしていない。")
    warnings.append("各音源の利用条件は元readmeの個別確認が必要で、派生特徴量の公開範囲も保守的に扱う。")
    lines.extend(["## 偏りと制約", "", *[f"- {warning}" for warning in warnings], ""])
    if baseline:
        separation = baseline.get("pairwise_analysis", {}).get("label_separation", {})
        ranked = sorted(separation.items(), key=lambda item: item[1].get("probability_different_is_farther", 0.0), reverse=True)
        lines.extend(["## Calibration上の識別傾向", "", "値は、別ラベルの距離が同一ラベルの距離より大きかったペア比率である。0.5付近は識別力が乏しい。", "", "| 特徴 | 比率 |", "| --- | ---: |"])
        for name, values in ranked[:10]:
            lines.append(f"| {name} | {values['probability_different_is_farther']:.3f} |")
        lines.extend(["", f"強い相関（|Spearman| ≥ 0.8）: {len(baseline.get('pairwise_analysis', {}).get('strong_correlations', []))} 組。総合化では二重計上を避ける。", ""])
        loso = baseline.get("leave_one_speaker_out", {})
        failures = baseline.get("estimation_failures", {}).get("overall", {})
        lines.extend([
            "## 推定器と未知話者の検証",
            "",
            f"- leave-one-speaker-out 5母音分類: {loso.get('accuracy', 0.0):.3f}（偶然水準 {loso.get('chance_accuracy', 0.2):.3f}、{loso.get('speaker_count', 0)}話者）",
            f"- F0推定失敗率: {failures.get('f0_failure_rate', 0.0):.3f}",
            f"- formant不完全率: {failures.get('formant_incomplete_rate', 0.0):.3f}",
            f"- 音声validation失敗率: {failures.get('invalid_audio_rate', 0.0):.3f}",
            "",
            "LOSO分類は音響特徴の音素識別傾向を調べる診断であり、自然さや生成品質の直接評価ではない。",
            "",
        ])
    lines.extend([
        "## 判断",
        "",
        "- この基準分布は開発中の候補絞り込みと異常診断に使えるが、人間らしさの最終根拠にはしない。",
        "- Target similarity と Human-likeness は分け、カテゴリ得点を維持する。試聴校正前の総合点は出さない。",
        "- 次に補う優先順位は、holdout話者の追加、権利台帳の確定、摩擦音・遷移・息の専用区間、UTAU以外の条件が明確な参照である。",
        "- holdoutは通常の反復調整に使わず、候補が固定された時点の検証だけに用いる。",
        "",
    ])
    return "\n".join(lines)
