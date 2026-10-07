from pathlib import Path


EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
BASELINE_ROOT = REPOSITORY_ROOT / "research/experiments/synthetic-vowel-baseline"
COMPARISON_ROOT = REPOSITORY_ROOT / "research/experiments/comparison-evaluation"
CONFIG_ROOT = EXPERIMENT_ROOT / "config"
RESULTS_ROOT = EXPERIMENT_ROOT / "results"

