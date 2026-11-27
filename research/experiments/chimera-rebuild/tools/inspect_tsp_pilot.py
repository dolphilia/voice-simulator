"""TSPの本文を発話計画の入口に通し、合成できる入力範囲を確認する。"""

import argparse
import csv
import json
from pathlib import Path
import subprocess

from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-active-duration-pilot.json'
SETTINGS = WORKSPACE / 'cases/human-body-english.json'
TRANSCRIPTS = UPSTREAM / 'tools/tsp/sentences.tsv'


def inspect_all(binary, output, metadata, settings, posture):
    registration = metadata['reference']
    speakers = {record_id[:2] for record_id in registration['calibration_ids'] + registration['held_out_ids']}
    observations = {}
    case_path = output / 'speech-input.json'
    with TRANSCRIPTS.open(newline='') as stream:
        for record_id, speaker, text in csv.reader(stream, delimiter='\t'):
            if speaker not in speakers:
                continue
            body = 'female' if speaker.startswith('F') else 'male'
            config = {'speech_voice': {
                'input': {'id': record_id, 'text': text, 'rate': metadata['synthesis']['speech_rate']},
                'body': body,
                'language': 'english',
                'posture': posture,
                'internal_sample_rate_hz': settings['internal_sample_rate_hz'],
                'voice': settings['voice'],
                'turbulence': {'scale': 1.0},
            }}
            case_path.write_text(json.dumps(config, ensure_ascii=False) + '\n')
            process = subprocess.run([binary, 'inspect', case_path], capture_output=True, text=True)
            result = {'speaker': speaker, 'input_sha256': sha256(case_path), 'exit_code': process.returncode}
            if process.returncode == 0:
                result['output_frames'] = json.loads(process.stdout)['output_frames']
            else:
                result['error'] = process.stderr.strip()
            observations[record_id] = result
        case_path.unlink()
    return observations


def common_sentences(probes, registered):
    female, male = sorted({record_id[:2] for record_id in registered})
    shared = [record_id[2:] for record_id, row in probes.items() if row['speaker'] == female
              and row['exit_code'] == 0 and probes.get(male + record_id[2:], {}).get('exit_code') == 0]
    return [speaker + sentence for speaker in (female, male) for sentence in sorted(shared)[:2]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    metadata = json.loads(CASE.read_text())
    settings = json.loads(SETTINGS.read_text())
    posture_path = WORKSPACE / 'cases' / settings['neutral_case']
    posture = json.loads(posture_path.read_text())['posture']
    binary = WORKSPACE / 'target/release/vocal-cli'

    def measure(artifacts, execute):
        execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
        probes = inspect_all(binary, artifacts, metadata, settings, posture)
        ids = metadata['reference']
        registered = {split: {name: probes[name] for name in ids[f'{split}_ids']}
                      for split in ('calibration', 'held_out')}
        feasible_pairs = {split: common_sentences(probes, rows) for split, rows in registered.items()}
        return {
            'checks': {'registered_utterances_supported': all(probe['exit_code'] == 0 for rows in registered.values()
                                                             for probe in rows.values())},
            'registered': registered,
            'feasible_pairs': feasible_pairs,
            'inspect_argv': ['$WORKSPACE/target/release/vocal-cli', 'inspect', '$ARTIFACTS/speech-input.json'],
            'candidate_binary_sha256': sha256(binary),
            'observations': probes,
        }

    inputs = [Path(__file__).resolve(), CASE, SETTINGS, posture_path, TRANSCRIPTS, WORKSPACE / 'Cargo.lock']
    return record_measurement(args.run_id, CASE, inputs,
                              {'case_id': metadata['id'], 'upstream_revision': metadata['upstream_revision'],
                               'operation': 'inspect-inputs'}, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
