from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

from . import BASELINE_VERSION, METRIC_PROFILE_VERSION, SCHEMA_VERSION
from .baseline import human_feature_baseline, human_pair_baseline, pair_classes
from .benchmark import compare_benchmarks, load_tasks, markdown_report, pareto_front, run_task, summarize_variants
from .calibration import calibrate_perceptual_mapping, validate_perceptual_mapping
from .extract import extract_file
from .io import read_jsonl, sha256_file, write_json, write_jsonl
from .manifest import REQUIRED_COLUMNS, deterministic_split, load_manifest, validate_manifest
from .metrics import compare_audio
from .listening import analyze_perceptual_suite, analyze_responses, merge_listening_analyses, prepare_perceptual_suite, prepare_session
from .reporting import manifest_report
from .scorecard import add_human_likeness, build_scorecard
from .validation import estimation_failure_report, leave_one_speaker_out
from .synthesis import render_calibration_anchors, render_suite
from .signal import read_audio, resample


def experiment_root() -> Path:
    return Path(__file__).resolve().parents[2]


def profile_segment(profile: str) -> str:
    return str(profile_config(profile)["segment"])


def profile_config(profile: str) -> dict[str, Any]:
    config = json.loads((experiment_root() / "config/metric-profiles.json").read_text(encoding="utf-8"))
    try:
        return dict(config["profiles"][profile])
    except KeyError as exc:
        raise ValueError(f"unknown profile: {profile}") from exc


def command_validate(args: argparse.Namespace) -> int:
    path = Path(args.manifest).resolve()
    records = load_manifest(path)
    errors = validate_manifest(path, records)
    print(json.dumps({"valid": not errors, "record_count": len(records), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def command_extract(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    records = load_manifest(manifest_path)
    errors = validate_manifest(manifest_path, records)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    output = []
    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
    cache_hits = 0
    for record in records:
        path = (manifest_path.parent / record.relative_path).resolve()
        metadata = {**record.metadata, "kind": record.kind, "label": record.label, "speaker_id": record.speaker_id, "source_recording_id": record.source_recording_id, "split": record.split, "license": record.license}
        segment = profile_segment(record.profile)
        cache_path = cache_dir / f"{sha256_file(path)}-{METRIC_PROFILE_VERSION}-{record.profile}-{segment}.json" if cache_dir else None
        if cache_path and cache_path.is_file():
            bundle = json.loads(cache_path.read_text(encoding="utf-8"))
            bundle["sample_id"], bundle["metadata"] = record.sample_id, metadata | {key: value for key, value in bundle.get("metadata", {}).items() if key in {"validation", "segment", "frame_count"}}
            cache_hits += 1
        else:
            bundle = extract_file(path, record.sample_id, record.profile, segment, metadata).to_dict()
            if cache_path:
                write_json(cache_path, bundle)
        output.append(bundle)
    write_jsonl(Path(args.output), output)
    print(f"{len(output)} samples ({cache_hits} cache hits) -> {Path(args.output).resolve()}")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    reference_path, generated_path = Path(args.reference).resolve(), Path(args.generated).resolve()
    ref_rate, reference = read_audio(reference_path)
    gen_rate, generated = read_audio(generated_path)
    target_rate = int(args.sample_rate or min(ref_rate, gen_rate))
    reference = resample(reference, ref_rate, target_rate)
    generated = resample(generated, gen_rate, target_rate)
    spec = profile_config(args.profile)
    metrics = [metric for metric in compare_audio(reference, generated, target_rate, str(spec["segment"])) if metric.category in set(spec["categories"])]
    card = build_scorecard(metrics, args.profile, reference_path.name, generated_path.name)
    if args.baseline:
        generated_bundle = extract_file(generated_path, generated_path.stem, args.profile, profile_segment(args.profile), {"label": args.label}).to_dict()
        add_human_likeness(card, generated_bundle, json.loads(Path(args.baseline).read_text(encoding="utf-8")), args.label)
    card["provenance"] = {"schema_version": SCHEMA_VERSION, "metric_profile_version": METRIC_PROFILE_VERSION, "sample_rate": target_rate}
    if args.output:
        write_json(Path(args.output), card)
    print(json.dumps(card, ensure_ascii=False, indent=2))
    return 0


def command_baseline(args: argparse.Namespace) -> int:
    all_features = read_jsonl(Path(args.features))
    features = [item for item in all_features if item.get("metadata", {}).get("split") == args.split]
    if not features:
        print(f"no features for split: {args.split}", file=sys.stderr)
        return 2
    result = {
        "schema_version": SCHEMA_VERSION,
        "baseline_version": BASELINE_VERSION,
        "split": args.split,
        "feature_distributions": human_feature_baseline(features),
        "pair_classes": pair_classes([item["metadata"] | {"sample_id": item["sample_id"]} for item in features]),
        "pairwise_analysis": human_pair_baseline(features),
        "estimation_failures": estimation_failure_report(features),
        "leave_one_speaker_out": leave_one_speaker_out(features),
    }
    write_json(Path(args.output), result)
    print(f"baseline -> {Path(args.output).resolve()}")
    return 0


def command_generate_utau_manifest(args: argparse.Namespace) -> int:
    index_path = Path(args.index).resolve()
    output_path = Path(args.output).resolve()
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with index_path.open(newline="", encoding="utf-8") as handle:
        for source in csv.DictReader(handle):
            label = Path(source["wav_filename"]).stem
            is_core = source["subset"].startswith("単独音") and label in {"あ", "い", "う", "え", "お", "し", "す"}
            is_breath = source["subset"] == "息" and label in {"息1", "息2"}
            if not (is_core or is_breath):
                continue
            absolute_audio = (Path.cwd() / Path(source["oto_path"]).parent / source["wav_filename"]).resolve()
            if not absolute_audio.is_file():
                continue
            speaker = source["speaker_dir"]
            subset_id = source["subset"].replace(" ", "-")
            sample_id = f"utau-{speaker}-{subset_id}-{label}"
            if sample_id in seen:
                continue
            seen.add(sample_id)
            relative = str(Path(os.path.relpath(absolute_audio, output_path.parent)))
            rows.append({
                "sample_id": sample_id, "relative_path": relative, "kind": "human",
                "profile": "fricative-noise" if label in {"し", "す", "息1", "息2"} else "sustained-vowel", "label": "breath" if is_breath else label,
                "speaker_id": speaker, "source_recording_id": f"utau-{speaker}-{subset_id}-{label}", "split": deterministic_split(speaker),
                "license": "local-research-only; verify source readme before export", "source": source["oto_path"], "subset": source["subset"],
            })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [*REQUIRED_COLUMNS, "source", "subset"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"output": str(output_path), "records": len(rows), "splits": {split: sum(row["split"] == split for row in rows) for split in ("development", "calibration", "holdout")}}, ensure_ascii=False, indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    records = load_manifest(manifest_path)
    errors = validate_manifest(manifest_path, records)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else None
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(manifest_report(records, baseline), encoding="utf-8")
    print(f"report -> {output.resolve()}")
    return 0


def command_license_ledger(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    records = load_manifest(manifest_path)
    entries: dict[tuple[str, str], dict[str, str]] = {}
    for record in records:
        source = record.metadata.get("source", "")
        subset = record.metadata.get("subset", "")
        key = (record.speaker_id, subset)
        source_dir = (Path.cwd() / Path(source)).resolve().parent if source else None
        candidates = list(source_dir.glob("[Rr][Ee][Aa][Dd][Mm][Ee]*")) if source_dir and source_dir.is_dir() else []
        readme = candidates[0] if candidates else None
        entries[key] = {
            "speaker_id": record.speaker_id,
            "subset": subset,
            "origin": source,
            "declared_scope": record.license,
            "terms_file": str(readme.relative_to(Path.cwd())) if readme and readme.is_relative_to(Path.cwd()) else str(readme or ""),
            "terms_sha256": sha256_file(readme) if readme and readme.is_file() else "",
            "review_status": "terms-file-present-unreviewed" if readme else "terms-file-missing",
            "export_allowed": "no",
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["speaker_id", "subset", "origin", "declared_scope", "terms_file", "terms_sha256", "review_status", "export_allowed"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(entries[key] for key in sorted(entries))
    print(json.dumps({"entries": len(entries), "terms_present": sum(bool(item["terms_sha256"]) for item in entries.values()), "export_allowed": 0, "output": str(output.resolve())}, ensure_ascii=False, indent=2))
    return 0


def command_benchmark(args: argparse.Namespace) -> int:
    tasks_path = Path(args.tasks).resolve()
    tasks = load_tasks(tasks_path)
    if not args.allow_holdout and any(task["reference_split"] == "holdout" for task in tasks):
        print("holdout task requires --allow-holdout; routine iteration must not inspect holdout", file=sys.stderr)
        return 2
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else None
    root = Path.cwd()
    gates = json.loads((experiment_root() / "config/thresholds.json").read_text(encoding="utf-8"))["gates"]
    results = []
    for task in tasks:
        spec = profile_config(task["profile"])
        results.append(run_task(task, root, str(spec["segment"]), baseline, set(spec["categories"]), gates))
    payload = {"schema_version": SCHEMA_VERSION, "tasks_file": str(tasks_path), "pareto_front": pareto_front(results), "variant_summary": summarize_variants(results), "results": results}
    write_json(Path(args.output), payload)
    if args.markdown:
        markdown_path = Path(args.markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_report(results, payload["pareto_front"], payload["variant_summary"]), encoding="utf-8")
    print(json.dumps({"tasks": len(results), "gate_failures": sum(bool(item["gate_failures"]) for item in results), "pareto_front": payload["pareto_front"]}, ensure_ascii=False, indent=2))
    return 3 if any(item["gate_failures"] for item in results) else 0


def command_diff(args: argparse.Namespace) -> int:
    previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    result = compare_benchmarks(previous, current, args.tolerance)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 3


def command_prepare_listening(args: argparse.Namespace) -> int:
    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    result = prepare_session(benchmark, Path(args.output).resolve(), args.seed, args.maximum, args.duplicate_ratio, args.selection)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_analyze_listening(args: argparse.Namespace) -> int:
    result = analyze_responses(Path(args.session).resolve())
    if args.output:
        write_json(Path(args.output), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 2


def command_calibrate(args: argparse.Namespace) -> int:
    listening = json.loads(Path(args.listening).read_text(encoding="utf-8"))
    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    result = calibrate_perceptual_mapping(listening, benchmark, args.minimum_pairs)
    write_json(Path(args.output), result)
    print(json.dumps({"status": result["status"], "task_count": result["task_count"], "correlations": len(result["correlations"]), "activated": False}, ensure_ascii=False, indent=2))
    return 0 if result["task_count"] >= args.minimum_pairs else 2


def command_render_suite(args: argparse.Namespace) -> int:
    result = render_suite(Path(args.config).resolve(), Path(args.output).resolve())
    write_json(Path(args.manifest), result)
    print(json.dumps({"records": len(result["records"]), "output": str(Path(args.output).resolve()), "manifest": str(Path(args.manifest).resolve())}, ensure_ascii=False, indent=2))
    return 0


def command_validate_calibration(args: argparse.Namespace) -> int:
    calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    listening = json.loads(Path(args.listening).read_text(encoding="utf-8"))
    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    result = validate_perceptual_mapping(calibration, listening, benchmark, args.minimum_pairs)
    write_json(Path(args.output), result)
    print(json.dumps({"status": result["status"], "eligible_for_adoption": result["eligible_for_adoption"], "activated": False}, ensure_ascii=False, indent=2))
    return 0 if result["eligible_for_adoption"] else 2


def command_merge_listening(args: argparse.Namespace) -> int:
    analyses = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.inputs]
    result = merge_listening_analyses(analyses)
    write_json(Path(args.output), result)
    print(json.dumps({"sources": len(analyses), "tasks": len(result["task_aggregates"]), "complete": result["complete"]}, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 2


def command_merge_benchmarks(args: argparse.Namespace) -> int:
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.inputs]
    results = [result for payload in payloads for result in payload.get("results", [])]
    task_ids = [result["task"]["task_id"] for result in results]
    if len(task_ids) != len(set(task_ids)):
        print("duplicate task_id across benchmarks", file=sys.stderr)
        return 2
    result = {"schema_version": SCHEMA_VERSION, "source_benchmarks": args.inputs, "pareto_front": pareto_front(results), "variant_summary": summarize_variants(results), "results": results}
    write_json(Path(args.output), result)
    print(json.dumps({"sources": len(payloads), "tasks": len(results)}, ensure_ascii=False, indent=2))
    return 0


def command_prepare_suite(args: argparse.Namespace) -> int:
    rendered = json.loads(Path(args.rendered).read_text(encoding="utf-8"))
    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    result = prepare_perceptual_suite(rendered, benchmark, Path(args.output).resolve(), args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_render_anchors(args: argparse.Namespace) -> int:
    records = render_calibration_anchors(Path(args.reference).resolve(), Path(args.output).resolve(), Path(args.config).resolve())
    tasks_path = Path(args.tasks).resolve()
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["task_id", "generated_path", "reference_path", "profile", "label", "reference_split", "variant"]
    with tasks_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames); writer.writeheader()
        for record in records:
            writer.writerow({"task_id": f"anchor-{record['name']}", "generated_path": os.path.relpath(record["path"], Path.cwd()), "reference_path": os.path.relpath(record["reference_path"], Path.cwd()), "profile": "sustained-vowel", "label": "あ", "reference_split": "development", "variant": record["name"]})
    print(json.dumps({"anchors": len(records), "tasks": str(tasks_path), "output": str(Path(args.output).resolve())}, ensure_ascii=False, indent=2))
    return 0


def command_analyze_suite(args: argparse.Namespace) -> int:
    result = analyze_perceptual_suite(Path(args.session).resolve())
    if args.output:
        write_json(Path(args.output), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 2


def command_test(_: argparse.Namespace) -> int:
    suite = unittest.defaultTestLoader.discover(str(experiment_root() / "tests"), pattern="test_*.py")
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Voice Simulator comparison evaluation")
    commands = result.add_subparsers(dest="command", required=True)
    test = commands.add_parser("test")
    test.set_defaults(function=command_test)
    validate = commands.add_parser("validate-manifest")
    validate.add_argument("--manifest", required=True)
    validate.set_defaults(function=command_validate)
    extract = commands.add_parser("extract")
    extract.add_argument("--manifest", required=True)
    extract.add_argument("--output", required=True)
    extract.add_argument("--cache-dir")
    extract.set_defaults(function=command_extract)
    compare = commands.add_parser("compare")
    compare.add_argument("--reference", required=True)
    compare.add_argument("--generated", required=True)
    compare.add_argument("--profile", default="sustained-vowel")
    compare.add_argument("--sample-rate", type=int)
    compare.add_argument("--output")
    compare.add_argument("--baseline")
    compare.add_argument("--label", default="あ")
    compare.set_defaults(function=command_compare)
    baseline = commands.add_parser("baseline")
    baseline.add_argument("--features", required=True)
    baseline.add_argument("--output", required=True)
    baseline.add_argument("--split", default="calibration", choices=["development", "calibration"])
    baseline.set_defaults(function=command_baseline)
    generate = commands.add_parser("generate-utau-manifest")
    generate.add_argument("--index", default="research/data/processed/analysis/utau-oto-index.csv")
    generate.add_argument("--output", default=str(experiment_root() / "config/manifests/utau-evaluation.csv"))
    generate.set_defaults(function=command_generate_utau_manifest)
    report = commands.add_parser("report")
    report.add_argument("--manifest", required=True)
    report.add_argument("--baseline")
    report.add_argument("--output", required=True)
    report.set_defaults(function=command_report)
    ledger = commands.add_parser("license-ledger")
    ledger.add_argument("--manifest", required=True)
    ledger.add_argument("--output", required=True)
    ledger.set_defaults(function=command_license_ledger)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--tasks", required=True)
    benchmark.add_argument("--baseline")
    benchmark.add_argument("--output", required=True)
    benchmark.add_argument("--markdown")
    benchmark.add_argument("--allow-holdout", action="store_true")
    benchmark.set_defaults(function=command_benchmark)
    diff = commands.add_parser("diff")
    diff.add_argument("--previous", required=True)
    diff.add_argument("--current", required=True)
    diff.add_argument("--tolerance", type=float, default=1.0)
    diff.set_defaults(function=command_diff)
    listening = commands.add_parser("prepare-listening")
    listening.add_argument("--benchmark", required=True)
    listening.add_argument("--output", required=True)
    listening.add_argument("--seed", type=int, default=20260813)
    listening.add_argument("--maximum", type=int, default=6)
    listening.add_argument("--duplicate-ratio", type=float, default=0.2)
    listening.add_argument("--selection", choices=["pareto", "all"], default="pareto")
    listening.set_defaults(function=command_prepare_listening)
    analyze = commands.add_parser("analyze-listening")
    analyze.add_argument("--session", required=True)
    analyze.add_argument("--output")
    analyze.set_defaults(function=command_analyze_listening)
    calibrate = commands.add_parser("calibrate")
    calibrate.add_argument("--listening", required=True)
    calibrate.add_argument("--benchmark", required=True)
    calibrate.add_argument("--output", required=True)
    calibrate.add_argument("--minimum-pairs", type=int, default=4)
    calibrate.set_defaults(function=command_calibrate)
    render = commands.add_parser("render-perceptual-fixtures")
    render.add_argument("--config", default=str(experiment_root() / "config/synthesis-fixtures.json"))
    render.add_argument("--output", required=True)
    render.add_argument("--manifest", required=True)
    render.set_defaults(function=command_render_suite)
    suite = commands.add_parser("prepare-perceptual-suite")
    suite.add_argument("--rendered", required=True)
    suite.add_argument("--benchmark", required=True)
    suite.add_argument("--output", required=True)
    suite.add_argument("--seed", type=int, default=20260813)
    suite.set_defaults(function=command_prepare_suite)
    analyze_suite = commands.add_parser("analyze-perceptual-suite")
    analyze_suite.add_argument("--session", required=True)
    analyze_suite.add_argument("--output")
    analyze_suite.set_defaults(function=command_analyze_suite)
    anchors = commands.add_parser("render-calibration-anchors")
    anchors.add_argument("--reference", required=True)
    anchors.add_argument("--output", required=True)
    anchors.add_argument("--tasks", required=True)
    anchors.add_argument("--config", default=str(experiment_root() / "config/synthesis-fixtures.json"))
    anchors.set_defaults(function=command_render_anchors)
    validate_calibration = commands.add_parser("validate-calibration")
    validate_calibration.add_argument("--calibration", required=True)
    validate_calibration.add_argument("--listening", required=True)
    validate_calibration.add_argument("--benchmark", required=True)
    validate_calibration.add_argument("--output", required=True)
    validate_calibration.add_argument("--minimum-pairs", type=int, default=4)
    validate_calibration.set_defaults(function=command_validate_calibration)
    merge = commands.add_parser("merge-listening")
    merge.add_argument("--inputs", nargs="+", required=True)
    merge.add_argument("--output", required=True)
    merge.set_defaults(function=command_merge_listening)
    merge_benchmarks = commands.add_parser("merge-benchmarks")
    merge_benchmarks.add_argument("--inputs", nargs="+", required=True)
    merge_benchmarks.add_argument("--output", required=True)
    merge_benchmarks.set_defaults(function=command_merge_benchmarks)
    return result


def main() -> int:
    args = parser().parse_args()
    return int(args.function(args))
