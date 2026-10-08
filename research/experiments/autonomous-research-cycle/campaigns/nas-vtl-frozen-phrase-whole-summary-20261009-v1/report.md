# 固定語句比較の部分結果

{
  "inputs": 8,
  "conditions": 2,
  "methods": [
    "native",
    "baseline",
    "learned"
  ],
  "expected_normal": 48,
  "expected_isolated": 48,
  "CLI": 3,
  "engineering": {
    "native": {
      "expected": 16,
      "E0_pass": 16,
      "pitch_pass": 3,
      "missing_records": 0,
      "fixed_support_intervals": 40,
      "missing_support": 0
    },
    "baseline": {
      "expected": 16,
      "E0_pass": 16,
      "pitch_pass": 8,
      "missing_records": 0,
      "fixed_support_intervals": 40,
      "missing_support": 0
    },
    "learned": {
      "expected": 16,
      "E0_pass": 16,
      "pitch_pass": 7,
      "missing_records": 0,
      "fixed_support_intervals": 40,
      "missing_support": 1
    }
  },
  "content": {
    "whisper": {
      "baseline_vs_native": {
        "groups": {
          "both/all": {
            "expected": 16,
            "missing": 0,
            "errors": 51,
            "native_errors": 10,
            "characters": 56,
            "non_worsening": false
          },
          "both/short": {
            "expected": 8,
            "missing": 0,
            "errors": 26,
            "native_errors": 2,
            "characters": 24,
            "non_worsening": false
          },
          "both/long": {
            "expected": 8,
            "missing": 0,
            "errors": 25,
            "native_errors": 8,
            "characters": 32,
            "non_worsening": false
          },
          "both/group0": {
            "expected": 4,
            "missing": 0,
            "errors": 9,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group1": {
            "expected": 4,
            "missing": 0,
            "errors": 13,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group2": {
            "expected": 4,
            "missing": 0,
            "errors": 18,
            "native_errors": 6,
            "characters": 14,
            "non_worsening": false
          },
          "both/group3": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 4,
            "characters": 14,
            "non_worsening": false
          },
          "both/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/all": {
            "expected": 8,
            "missing": 0,
            "errors": 27,
            "native_errors": 6,
            "characters": 28,
            "non_worsening": false
          },
          "neutral/short": {
            "expected": 4,
            "missing": 0,
            "errors": 16,
            "native_errors": 2,
            "characters": 12,
            "non_worsening": false
          },
          "neutral/long": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 4,
            "characters": 16,
            "non_worsening": false
          },
          "neutral/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 8,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 4,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/all": {
            "expected": 8,
            "missing": 0,
            "errors": 24,
            "native_errors": 4,
            "characters": 28,
            "non_worsening": false
          },
          "higher/short": {
            "expected": 4,
            "missing": 0,
            "errors": 10,
            "native_errors": 0,
            "characters": 12,
            "non_worsening": false
          },
          "higher/long": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 4,
            "characters": 16,
            "non_worsening": false
          },
          "higher/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 11,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          }
        },
        "active_groups": 21,
        "zero_denominator_groups": [
          "both/group4",
          "both/group5",
          "both/group6",
          "both/group7",
          "neutral/group4",
          "neutral/group5",
          "neutral/group6",
          "neutral/group7",
          "higher/group4",
          "higher/group5",
          "higher/group6",
          "higher/group7"
        ],
        "worsening_active_groups": [
          "both/all",
          "both/short",
          "both/long",
          "both/group0",
          "both/group1",
          "both/group2",
          "both/group3",
          "neutral/all",
          "neutral/short",
          "neutral/long",
          "neutral/group0",
          "neutral/group1",
          "neutral/group2",
          "neutral/group3",
          "higher/all",
          "higher/short",
          "higher/long",
          "higher/group0",
          "higher/group1",
          "higher/group2",
          "higher/group3"
        ],
        "all_33_non_worsening": false
      },
      "learned_vs_native": {
        "groups": {
          "both/all": {
            "expected": 16,
            "missing": 0,
            "errors": 52,
            "native_errors": 10,
            "characters": 56,
            "non_worsening": false
          },
          "both/short": {
            "expected": 8,
            "missing": 0,
            "errors": 24,
            "native_errors": 2,
            "characters": 24,
            "non_worsening": false
          },
          "both/long": {
            "expected": 8,
            "missing": 0,
            "errors": 28,
            "native_errors": 8,
            "characters": 32,
            "non_worsening": false
          },
          "both/group0": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group1": {
            "expected": 4,
            "missing": 0,
            "errors": 12,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group2": {
            "expected": 4,
            "missing": 0,
            "errors": 16,
            "native_errors": 6,
            "characters": 14,
            "non_worsening": false
          },
          "both/group3": {
            "expected": 4,
            "missing": 0,
            "errors": 13,
            "native_errors": 4,
            "characters": 14,
            "non_worsening": false
          },
          "both/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/all": {
            "expected": 8,
            "missing": 0,
            "errors": 20,
            "native_errors": 6,
            "characters": 28,
            "non_worsening": false
          },
          "neutral/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 2,
            "characters": 12,
            "non_worsening": false
          },
          "neutral/long": {
            "expected": 4,
            "missing": 0,
            "errors": 9,
            "native_errors": 4,
            "characters": 16,
            "non_worsening": false
          },
          "neutral/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 4,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/all": {
            "expected": 8,
            "missing": 0,
            "errors": 32,
            "native_errors": 4,
            "characters": 28,
            "non_worsening": false
          },
          "higher/short": {
            "expected": 4,
            "missing": 0,
            "errors": 13,
            "native_errors": 0,
            "characters": 12,
            "non_worsening": false
          },
          "higher/long": {
            "expected": 4,
            "missing": 0,
            "errors": 19,
            "native_errors": 4,
            "characters": 16,
            "non_worsening": false
          },
          "higher/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 8,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 9,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 9,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          }
        },
        "active_groups": 21,
        "zero_denominator_groups": [
          "both/group4",
          "both/group5",
          "both/group6",
          "both/group7",
          "neutral/group4",
          "neutral/group5",
          "neutral/group6",
          "neutral/group7",
          "higher/group4",
          "higher/group5",
          "higher/group6",
          "higher/group7"
        ],
        "worsening_active_groups": [
          "both/all",
          "both/short",
          "both/long",
          "both/group0",
          "both/group1",
          "both/group2",
          "both/group3",
          "neutral/all",
          "neutral/short",
          "neutral/long",
          "neutral/group0",
          "neutral/group1",
          "neutral/group2",
          "neutral/group3",
          "higher/all",
          "higher/short",
          "higher/long",
          "higher/group0",
          "higher/group1",
          "higher/group2",
          "higher/group3"
        ],
        "all_33_non_worsening": false
      },
      "learned_vs_baseline": {
        "groups": {
          "both/all": {
            "expected": 16,
            "missing": 0,
            "errors": 52,
            "native_errors": 51,
            "characters": 56,
            "non_worsening": false
          },
          "both/short": {
            "expected": 8,
            "missing": 0,
            "errors": 24,
            "native_errors": 26,
            "characters": 24,
            "non_worsening": true
          },
          "both/long": {
            "expected": 8,
            "missing": 0,
            "errors": 28,
            "native_errors": 25,
            "characters": 32,
            "non_worsening": false
          },
          "both/group0": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 9,
            "characters": 14,
            "non_worsening": false
          },
          "both/group1": {
            "expected": 4,
            "missing": 0,
            "errors": 12,
            "native_errors": 13,
            "characters": 14,
            "non_worsening": true
          },
          "both/group2": {
            "expected": 4,
            "missing": 0,
            "errors": 16,
            "native_errors": 18,
            "characters": 14,
            "non_worsening": true
          },
          "both/group3": {
            "expected": 4,
            "missing": 0,
            "errors": 13,
            "native_errors": 11,
            "characters": 14,
            "non_worsening": false
          },
          "both/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/all": {
            "expected": 8,
            "missing": 0,
            "errors": 20,
            "native_errors": 27,
            "characters": 28,
            "non_worsening": true
          },
          "neutral/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 16,
            "characters": 12,
            "non_worsening": true
          },
          "neutral/long": {
            "expected": 4,
            "missing": 0,
            "errors": 9,
            "native_errors": 11,
            "characters": 16,
            "non_worsening": true
          },
          "neutral/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 5,
            "characters": 7,
            "non_worsening": true
          },
          "neutral/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 8,
            "characters": 7,
            "non_worsening": true
          },
          "neutral/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 7,
            "characters": 7,
            "non_worsening": true
          },
          "neutral/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 7,
            "characters": 7,
            "non_worsening": true
          },
          "neutral/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/all": {
            "expected": 8,
            "missing": 0,
            "errors": 32,
            "native_errors": 24,
            "characters": 28,
            "non_worsening": false
          },
          "higher/short": {
            "expected": 4,
            "missing": 0,
            "errors": 13,
            "native_errors": 10,
            "characters": 12,
            "non_worsening": false
          },
          "higher/long": {
            "expected": 4,
            "missing": 0,
            "errors": 19,
            "native_errors": 14,
            "characters": 16,
            "non_worsening": false
          },
          "higher/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 4,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 8,
            "native_errors": 5,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 9,
            "native_errors": 11,
            "characters": 7,
            "non_worsening": true
          },
          "higher/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 9,
            "native_errors": 4,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          }
        },
        "active_groups": 21,
        "zero_denominator_groups": [
          "both/group4",
          "both/group5",
          "both/group6",
          "both/group7",
          "neutral/group4",
          "neutral/group5",
          "neutral/group6",
          "neutral/group7",
          "higher/group4",
          "higher/group5",
          "higher/group6",
          "higher/group7"
        ],
        "worsening_active_groups": [
          "both/all",
          "both/long",
          "both/group0",
          "both/group3",
          "higher/all",
          "higher/short",
          "higher/long",
          "higher/group0",
          "higher/group1",
          "higher/group3"
        ],
        "all_33_non_worsening": false
      }
    },
    "reazon": {
      "baseline_vs_native": {
        "groups": {
          "both/all": {
            "expected": 16,
            "missing": 0,
            "errors": 42,
            "native_errors": 2,
            "characters": 56,
            "non_worsening": false
          },
          "both/short": {
            "expected": 8,
            "missing": 0,
            "errors": 20,
            "native_errors": 0,
            "characters": 24,
            "non_worsening": false
          },
          "both/long": {
            "expected": 8,
            "missing": 0,
            "errors": 22,
            "native_errors": 2,
            "characters": 32,
            "non_worsening": false
          },
          "both/group0": {
            "expected": 4,
            "missing": 0,
            "errors": 12,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group1": {
            "expected": 4,
            "missing": 0,
            "errors": 10,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group2": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 2,
            "characters": 14,
            "non_worsening": false
          },
          "both/group3": {
            "expected": 4,
            "missing": 0,
            "errors": 9,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/all": {
            "expected": 8,
            "missing": 0,
            "errors": 19,
            "native_errors": 0,
            "characters": 28,
            "non_worsening": false
          },
          "neutral/short": {
            "expected": 4,
            "missing": 0,
            "errors": 9,
            "native_errors": 0,
            "characters": 12,
            "non_worsening": false
          },
          "neutral/long": {
            "expected": 4,
            "missing": 0,
            "errors": 10,
            "native_errors": 0,
            "characters": 16,
            "non_worsening": false
          },
          "neutral/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 4,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/all": {
            "expected": 8,
            "missing": 0,
            "errors": 23,
            "native_errors": 2,
            "characters": 28,
            "non_worsening": false
          },
          "higher/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 0,
            "characters": 12,
            "non_worsening": false
          },
          "higher/long": {
            "expected": 4,
            "missing": 0,
            "errors": 12,
            "native_errors": 2,
            "characters": 16,
            "non_worsening": false
          },
          "higher/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          }
        },
        "active_groups": 21,
        "zero_denominator_groups": [
          "both/group4",
          "both/group5",
          "both/group6",
          "both/group7",
          "neutral/group4",
          "neutral/group5",
          "neutral/group6",
          "neutral/group7",
          "higher/group4",
          "higher/group5",
          "higher/group6",
          "higher/group7"
        ],
        "worsening_active_groups": [
          "both/all",
          "both/short",
          "both/long",
          "both/group0",
          "both/group1",
          "both/group2",
          "both/group3",
          "neutral/all",
          "neutral/short",
          "neutral/long",
          "neutral/group0",
          "neutral/group1",
          "neutral/group2",
          "neutral/group3",
          "higher/all",
          "higher/short",
          "higher/long",
          "higher/group0",
          "higher/group1",
          "higher/group2",
          "higher/group3"
        ],
        "all_33_non_worsening": false
      },
      "learned_vs_native": {
        "groups": {
          "both/all": {
            "expected": 16,
            "missing": 0,
            "errors": 50,
            "native_errors": 2,
            "characters": 56,
            "non_worsening": false
          },
          "both/short": {
            "expected": 8,
            "missing": 0,
            "errors": 22,
            "native_errors": 0,
            "characters": 24,
            "non_worsening": false
          },
          "both/long": {
            "expected": 8,
            "missing": 0,
            "errors": 28,
            "native_errors": 2,
            "characters": 32,
            "non_worsening": false
          },
          "both/group0": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group1": {
            "expected": 4,
            "missing": 0,
            "errors": 12,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group2": {
            "expected": 4,
            "missing": 0,
            "errors": 10,
            "native_errors": 2,
            "characters": 14,
            "non_worsening": false
          },
          "both/group3": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 0,
            "characters": 14,
            "non_worsening": false
          },
          "both/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/all": {
            "expected": 8,
            "missing": 0,
            "errors": 25,
            "native_errors": 0,
            "characters": 28,
            "non_worsening": false
          },
          "neutral/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 0,
            "characters": 12,
            "non_worsening": false
          },
          "neutral/long": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 0,
            "characters": 16,
            "non_worsening": false
          },
          "neutral/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/all": {
            "expected": 8,
            "missing": 0,
            "errors": 25,
            "native_errors": 2,
            "characters": 28,
            "non_worsening": false
          },
          "higher/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 0,
            "characters": 12,
            "non_worsening": false
          },
          "higher/long": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 2,
            "characters": 16,
            "non_worsening": false
          },
          "higher/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 2,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 0,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          }
        },
        "active_groups": 21,
        "zero_denominator_groups": [
          "both/group4",
          "both/group5",
          "both/group6",
          "both/group7",
          "neutral/group4",
          "neutral/group5",
          "neutral/group6",
          "neutral/group7",
          "higher/group4",
          "higher/group5",
          "higher/group6",
          "higher/group7"
        ],
        "worsening_active_groups": [
          "both/all",
          "both/short",
          "both/long",
          "both/group0",
          "both/group1",
          "both/group2",
          "both/group3",
          "neutral/all",
          "neutral/short",
          "neutral/long",
          "neutral/group0",
          "neutral/group1",
          "neutral/group2",
          "neutral/group3",
          "higher/all",
          "higher/short",
          "higher/long",
          "higher/group0",
          "higher/group1",
          "higher/group2",
          "higher/group3"
        ],
        "all_33_non_worsening": false
      },
      "learned_vs_baseline": {
        "groups": {
          "both/all": {
            "expected": 16,
            "missing": 0,
            "errors": 50,
            "native_errors": 42,
            "characters": 56,
            "non_worsening": false
          },
          "both/short": {
            "expected": 8,
            "missing": 0,
            "errors": 22,
            "native_errors": 20,
            "characters": 24,
            "non_worsening": false
          },
          "both/long": {
            "expected": 8,
            "missing": 0,
            "errors": 28,
            "native_errors": 22,
            "characters": 32,
            "non_worsening": false
          },
          "both/group0": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 12,
            "characters": 14,
            "non_worsening": false
          },
          "both/group1": {
            "expected": 4,
            "missing": 0,
            "errors": 12,
            "native_errors": 10,
            "characters": 14,
            "non_worsening": false
          },
          "both/group2": {
            "expected": 4,
            "missing": 0,
            "errors": 10,
            "native_errors": 11,
            "characters": 14,
            "non_worsening": true
          },
          "both/group3": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 9,
            "characters": 14,
            "non_worsening": false
          },
          "both/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "both/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/all": {
            "expected": 8,
            "missing": 0,
            "errors": 25,
            "native_errors": 19,
            "characters": 28,
            "non_worsening": false
          },
          "neutral/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 9,
            "characters": 12,
            "non_worsening": false
          },
          "neutral/long": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 10,
            "characters": 16,
            "non_worsening": false
          },
          "neutral/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 6,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 4,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 5,
            "characters": 7,
            "non_worsening": true
          },
          "neutral/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 4,
            "characters": 7,
            "non_worsening": false
          },
          "neutral/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "neutral/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/all": {
            "expected": 8,
            "missing": 0,
            "errors": 25,
            "native_errors": 23,
            "characters": 28,
            "non_worsening": false
          },
          "higher/short": {
            "expected": 4,
            "missing": 0,
            "errors": 11,
            "native_errors": 11,
            "characters": 12,
            "non_worsening": true
          },
          "higher/long": {
            "expected": 4,
            "missing": 0,
            "errors": 14,
            "native_errors": 12,
            "characters": 16,
            "non_worsening": false
          },
          "higher/group0": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 6,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group1": {
            "expected": 2,
            "missing": 0,
            "errors": 6,
            "native_errors": 6,
            "characters": 7,
            "non_worsening": true
          },
          "higher/group2": {
            "expected": 2,
            "missing": 0,
            "errors": 5,
            "native_errors": 6,
            "characters": 7,
            "non_worsening": true
          },
          "higher/group3": {
            "expected": 2,
            "missing": 0,
            "errors": 7,
            "native_errors": 5,
            "characters": 7,
            "non_worsening": false
          },
          "higher/group4": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group5": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group6": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          },
          "higher/group7": {
            "expected": 0,
            "missing": 0,
            "errors": 0,
            "native_errors": 0,
            "characters": 0,
            "non_worsening": false
          }
        },
        "active_groups": 21,
        "zero_denominator_groups": [
          "both/group4",
          "both/group5",
          "both/group6",
          "both/group7",
          "neutral/group4",
          "neutral/group5",
          "neutral/group6",
          "neutral/group7",
          "higher/group4",
          "higher/group5",
          "higher/group6",
          "higher/group7"
        ],
        "worsening_active_groups": [
          "both/all",
          "both/short",
          "both/long",
          "both/group0",
          "both/group1",
          "both/group3",
          "neutral/all",
          "neutral/short",
          "neutral/long",
          "neutral/group0",
          "neutral/group1",
          "neutral/group3",
          "higher/all",
          "higher/long",
          "higher/group0",
          "higher/group3"
        ],
        "all_33_non_worsening": false
      }
    }
  },
  "frozen_coefficients": true,
  "actual_generalizable_speech_improvement_verified": false,
  "perceptual_qualification": false,
  "quality_goal_completed": false,
  "P5_opened": false,
  "adopted": false,
  "prior_CV_k_t_joint_qualified": 0,
  "prior_CV_s_unperformed": true,
  "D_allocation_consumed_render": 31394,
  "D_allocation_maximum": 36000,
  "limitations": "短3/長4モーラの限定診断、未対応groups4..7は0分母/不通過、e/o未学習、無声化未実装。C不通過・知覚/独立P5不足を本結果で救済しない。",
  "next": "全体封印と工程D境界をレビューし、音声改善へ届かなかった原因と残資源を基に、次の新機構/訓練資料/条件を別登録する。旧比較と24時間工程時計を巻戻さない。"
}

全体の未実施/0分母/工学不通過を保持。内容/知覚/一般化/日本語品質の認定は別。P5未開封。
