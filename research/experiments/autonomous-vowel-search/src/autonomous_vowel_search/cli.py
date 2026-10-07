from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path

from .configuration import validate_campaign, validate_targets
from .inventory import build_ledger, validate_ledger
from .io import read_json, sha256_file, write_json_new, write_jsonl_new
from .paths import CONFIG_ROOT, EXPERIMENT_ROOT, RESULTS_ROOT
from .regression import run_smoke
from .reference_evaluation import evaluate_sensitivity_references, markdown_report as reference_markdown_report, validate_reference_group
from .sensitivity import markdown_report, run_sensitivity
from .time_structure import evaluate_time_structure, markdown_report as time_structure_markdown_report
from .onset import markdown_report as onset_markdown_report, run_onset_sensitivity
from .search import freeze_settings, markdown_report as search_markdown_report, run_search
from .robustness import markdown_report as robustness_markdown_report, run_robustness
from .listening_package import freeze_listening_package, markdown_readme as listening_package_readme


def configs() -> tuple[dict, dict, dict, dict]:
    return (
        read_json(CONFIG_ROOT / "campaign-a220-v1.json"),
        read_json(CONFIG_ROOT / "acoustic-targets-v1.json"),
        read_json(CONFIG_ROOT / "candidate-ledger-schema-v1.json"),
        read_json(CONFIG_ROOT / "regression-suite-v1.json"),
    )


def command_inventory(_: argparse.Namespace) -> int:
    _, _, schema, _ = configs()
    rows = build_ledger()
    errors = validate_ledger(rows, schema)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    output = RESULTS_ROOT / "a0/ledger.jsonl"
    write_jsonl_new(output, rows)
    summary = {
        "schema_version": "1.0.0",
        "candidate_count": len(rows),
        "conditions": sorted({row["condition"] for row in rows}),
        "with_listening_evidence": sum(row["listening_status"] != "not_queued" for row in rows),
        "hash_verified": sum(row["engineering_checks"]["hash_verified"] for row in rows),
        "ledger_sha256": sha256_file(output),
        "interpretation": "source evidence inventory; missing answers are not inferred",
    }
    write_json_new(RESULTS_ROOT / "a0/summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def validation_result() -> dict:
    campaign, targets, schema, suite = configs()
    errors = [*validate_campaign(campaign), *validate_targets(targets)]
    required_configs = {
        name: sha256_file(CONFIG_ROOT / name)
        for name in (
            "campaign-a220-v1.json",
            "acoustic-targets-v1.json",
            "candidate-ledger-schema-v1.json",
            "regression-suite-v1.json",
        )
    }
    return {
        "schema_version": "1.0.0",
        "valid": not errors,
        "errors": errors,
        "config_sha256": required_configs,
        "ledger_schema_version": schema["schema_version"],
        "regression_suite": suite["suite_id"],
    }


def command_validate(_: argparse.Namespace) -> int:
    result = validation_result()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


def command_regression(_: argparse.Namespace) -> int:
    campaign, targets, _, suite = configs()
    validation = validation_result()
    if not validation["valid"]:
        print("設定検査が不通過です", file=sys.stderr)
        return 2
    output_dir = RESULTS_ROOT / campaign["campaign_id"] / "a1"
    output = output_dir / "smoke.json"
    if output.exists() or (output_dir / "audio/b9-canonical.wav").exists():
        print(f"既存成果物は上書きしません: {output_dir}", file=sys.stderr)
        return 2
    result = run_smoke(output_dir, campaign, targets, suite)
    write_json_new(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 3


def command_sensitivity(_: argparse.Namespace) -> int:
    campaign, targets, _, _ = configs()
    validation = validation_result()
    smoke_path = RESULTS_ROOT / campaign["campaign_id"] / "a1/smoke.json"
    if not validation["valid"]:
        print("設定検査が不通過です", file=sys.stderr)
        return 2
    if not smoke_path.is_file() or not read_json(smoke_path).get("passed"):
        print("A1 smoke回帰の通過が必要です", file=sys.stderr)
        return 2
    output_dir = RESULTS_ROOT / campaign["campaign_id"] / "a2-sensitivity"
    output = output_dir / "sensitivity.json"
    if output.exists() or (output_dir / "audio").exists():
        print(f"既存成果物は上書きしません: {output_dir}", file=sys.stderr)
        return 2
    result = run_sensitivity(output_dir, campaign, targets)
    write_json_new(output, result)
    report = output_dir / "report.md"
    if report.exists():
        raise FileExistsError(f"既存成果物は上書きしません: {report}")
    report.write_text(markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "settings": result["setting_count"],
        "renders": result["render_count"],
        "elapsed_sec": result["elapsed_sec"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_evaluate_references(_: argparse.Namespace) -> int:
    campaign, _, _, _ = configs()
    sensitivity_dir = RESULTS_ROOT / campaign["campaign_id"] / "a2-sensitivity"
    sensitivity_path = sensitivity_dir / "sensitivity.json"
    if not sensitivity_path.is_file():
        print("A2感度pilotが必要です", file=sys.stderr)
        return 2
    group = read_json(CONFIG_ROOT / "development-reference-group-a220-v1.json")
    errors = validate_reference_group(group)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    output_dir = RESULTS_ROOT / campaign["campaign_id"] / "a2b-reference-evaluation"
    output = output_dir / "evaluation.json"
    if output.exists():
        print(f"既存成果物は上書きしません: {output}", file=sys.stderr)
        return 2
    result = evaluate_sensitivity_references(read_json(sensitivity_path), sensitivity_dir, group)
    write_json_new(output, result)
    report = output_dir / "report.md"
    report.write_text(reference_markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "reference_group": result["reference_group_id"],
        "speakers": result["speaker_count"],
        "comparisons": result["comparison_count"],
        "holdout_opened": result["holdout_opened"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_time_structure(_: argparse.Namespace) -> int:
    campaign, _, _, _ = configs()
    sensitivity_dir = RESULTS_ROOT / campaign["campaign_id"] / "a2-sensitivity"
    sensitivity_path = sensitivity_dir / "sensitivity.json"
    if not sensitivity_path.is_file():
        print("A2感度pilotが必要です", file=sys.stderr)
        return 2
    group = read_json(CONFIG_ROOT / "development-reference-group-a220-v1.json")
    output_dir = RESULTS_ROOT / campaign["campaign_id"] / "a2c-time-structure"
    output = output_dir / "evaluation.json"
    if output.exists():
        print(f"既存成果物は上書きしません: {output}", file=sys.stderr)
        return 2
    result = evaluate_time_structure(read_json(sensitivity_path), sensitivity_dir, group)
    write_json_new(output, result)
    (output_dir / "report.md").write_text(time_structure_markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "campaign_id": result["campaign_id"],
        "reference_group": result["reference_group_id"],
        "generated": len(result["generated"]),
        "references": len(result["references"]),
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_onset_sensitivity(_: argparse.Namespace) -> int:
    config = read_json(CONFIG_ROOT / "onset-campaign-a220-v1.json")
    output_dir = RESULTS_ROOT / config["campaign_id"] / "a2-sensitivity"
    output = output_dir / "sensitivity.json"
    if output.exists() or (output_dir / "audio").exists():
        print(f"既存成果物は上書きしません: {output_dir}", file=sys.stderr)
        return 2
    result = run_onset_sensitivity(output_dir, config)
    write_json_new(output, result)
    (output_dir / "report.md").write_text(onset_markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "campaign_id": result["campaign_id"],
        "renders": result["render_count"],
        "canonical_regression_passed": result["canonical_regression_passed"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_run_campaign(_: argparse.Namespace) -> int:
    config = read_json(CONFIG_ROOT / "search-campaign-a220-v1.json")
    _, targets, _, _ = configs()
    output_dir = RESULTS_ROOT / config["campaign_id"] / "a3-search"
    output = output_dir / "evaluation.json"
    if output.exists() or (output_dir / "audio").exists():
        print(f"既存成果物は上書きしません: {output_dir}", file=sys.stderr)
        return 2
    frozen = freeze_settings(config)
    write_json_new(output_dir / "frozen-settings.json", {
        "schema_version": "1.0.0",
        "campaign_id": config["campaign_id"],
        "settings": frozen,
    })
    result = run_search(output_dir, config, targets)
    write_json_new(output, result)
    (output_dir / "report.md").write_text(search_markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "campaign_id": result["campaign_id"],
        "settings": result["setting_count"],
        "renders": result["render_count"],
        "method_summary": result["method_summary"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_robustness(_: argparse.Namespace) -> int:
    config = read_json(CONFIG_ROOT / "search-campaign-a220-v1.json")
    _, targets, _, _ = configs()
    search_path = RESULTS_ROOT / config["campaign_id"] / "a3-search/evaluation.json"
    if not search_path.is_file():
        print("A3探索結果が必要です", file=sys.stderr)
        return 2
    output_dir = RESULTS_ROOT / config["campaign_id"] / "a4-robustness"
    output = output_dir / "evaluation.json"
    if output.exists() or (output_dir / "audio").exists():
        print(f"既存成果物は上書きしません: {output_dir}", file=sys.stderr)
        return 2
    result = run_robustness(output_dir, read_json(search_path), config, targets)
    write_json_new(output, result)
    (output_dir / "report.md").write_text(robustness_markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "campaign_id": result["campaign_id"],
        "candidates": len(result["selected"]),
        "renders": result["render_count"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_freeze_listening(_: argparse.Namespace) -> int:
    config = read_json(CONFIG_ROOT / "search-campaign-a220-v1.json")
    robustness_dir = RESULTS_ROOT / config["campaign_id"] / "a4-robustness"
    robustness_path = robustness_dir / "evaluation.json"
    if not robustness_path.is_file():
        print("A4頑健性結果が必要です", file=sys.stderr)
        return 2
    output_dir = RESULTS_ROOT / config["campaign_id"] / "a5-listening-package"
    output = output_dir / "manifest.json"
    if output.exists():
        print(f"既存成果物は上書きしません: {output}", file=sys.stderr)
        return 2
    package = freeze_listening_package(read_json(robustness_path), robustness_dir)
    write_json_new(output, package)
    (output_dir / "README.md").write_text(listening_package_readme(package), encoding="utf-8")
    print(json.dumps({
        "package_id": package["package_id"],
        "status": package["status"],
        "candidates": len(package["selected_candidate_ids"]),
        "presentations": package["presentation_count"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_status(_: argparse.Namespace) -> int:
    campaign, _, _, _ = configs()
    onset_campaign = read_json(CONFIG_ROOT / "onset-campaign-a220-v1.json")
    search_campaign = read_json(CONFIG_ROOT / "search-campaign-a220-v1.json")
    artifacts = {
        "a0_inventory": RESULTS_ROOT / "a0/summary.json",
        "a1_regression": RESULTS_ROOT / campaign["campaign_id"] / "a1/smoke.json",
        "a2_sensitivity": RESULTS_ROOT / campaign["campaign_id"] / "a2-sensitivity/sensitivity.json",
        "a2b_reference_evaluation": RESULTS_ROOT / campaign["campaign_id"] / "a2b-reference-evaluation/evaluation.json",
        "a2c_time_structure": RESULTS_ROOT / campaign["campaign_id"] / "a2c-time-structure/evaluation.json",
        "onset_a2_sensitivity": RESULTS_ROOT / onset_campaign["campaign_id"] / "a2-sensitivity/sensitivity.json",
        "a3_search": RESULTS_ROOT / search_campaign["campaign_id"] / "a3-search/evaluation.json",
        "a4_robustness": RESULTS_ROOT / search_campaign["campaign_id"] / "a4-robustness/evaluation.json",
        "a5_listening_package": RESULTS_ROOT / search_campaign["campaign_id"] / "a5-listening-package/manifest.json",
    }
    result = {
        "campaign_id": campaign["campaign_id"],
        "configured_status": campaign["status"],
        "stages": {name: {"complete": path.is_file(), "path": str(path)} for name, path in artifacts.items()},
        "formal_search_frozen": bool(search_campaign["frozen"]),
        "formal_search_campaign_id": search_campaign["campaign_id"],
        "listening_status": "not_queued",
        "perceptual_claim_allowed": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_test(_: argparse.Namespace) -> int:
    suite = unittest.defaultTestLoader.discover(str(EXPERIMENT_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="試聴待ちと分離した母音自動探索")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (
        ("inventory", command_inventory),
        ("validate-config", command_validate),
        ("regression", command_regression),
        ("sensitivity", command_sensitivity),
        ("evaluate-references", command_evaluate_references),
        ("time-structure", command_time_structure),
        ("onset-sensitivity", command_onset_sensitivity),
        ("run-campaign", command_run_campaign),
        ("robustness", command_robustness),
        ("freeze-listening", command_freeze_listening),
        ("status", command_status),
        ("test", command_test),
    ):
        command = commands.add_parser(name)
        command.set_defaults(function=function)
    args = parser.parse_args(argv)
    try:
        return int(args.function(args))
    except (FileExistsError, FileNotFoundError, KeyError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
