"""Safariの試験音をAudio ClientのI/O開始時刻へ対応づける。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from xml.etree import ElementTree

from filter_worklet_audioipc_syscalls import field_value
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_process_tap_calibration import INSPECTOR, SAFARI, identified_process, inspect_graph, read_json
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WEB, UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/safari-audio-client-trace.json'
XCTRACE = ('xcrun', 'xctrace')
SCHEMA = 'audio-hal-client-io-cycle'


def read_cycles(source, pid, *, include_overloads=False):
    root = ElementTree.parse(source).getroot()
    nodes = [node for node in root.findall('node') if node.find(f"schema[@name='{SCHEMA}']") is not None]
    if len(nodes) != 1:
        raise ValueError('Audio ClientのI/O区間の表を一意に取得できません')
    node = nodes[0]
    columns = [column.findtext('mnemonic') for column in node.find('schema')]
    rows, values, cycles = node.findall('row'), {}, []
    for row in rows:
        for cell in row.iter():
            if 'id' in cell.attrib and cell.tag in ('process', 'thread', 'pid', 'tid', 'start-time', 'duration',
                                                     'narrative', 'narrative-text'):
                child = cell.find('narrative-text') if cell.tag == 'narrative' else None
                values[cell.attrib['id']] = field_value(child if child is not None else cell, values)
        fields = dict(zip(columns, row, strict=True))
        if field_value(fields['process'], values) != str(pid):
            continue
        narrative = fields['description'].find('narrative-text')
        description = field_value(narrative if narrative is not None else fields['description'], values)
        if description != 'Cycle' and not (include_overloads and description == 'Cycle; Overload'):
            continue
        start = int(field_value(fields['start'], values))
        duration = int(field_value(fields['duration'], values))
        cycle = {'start_ns': start, 'duration_ns': duration, 'tid': int(field_value(fields['thread'], values))}
        if include_overloads:
            cycle['description'] = description
        cycles.append(cycle)
    return cycles, len(rows)


def inspect_trace(label, folder, pid, execute):
    trace = folder / f'{label}.trace'
    toc, source = (folder / f'{label}-{name}.xml' for name in ('toc', 'cycles'))
    execute([*XCTRACE, 'export', '--input', str(trace), '--toc', '--output', str(toc)])
    execute([*XCTRACE, 'export', '--input', str(trace), '--xpath', f'/trace-toc/run/data/table[@schema="{SCHEMA}"]',
             '--output', str(source)])
    clock = ElementTree.parse(toc)
    origin = datetime.fromisoformat(clock.findtext('.//start-date')).timestamp() * 1000
    cycles, row_count = read_cycles(source, pid)
    return {'trace_start_epoch_ms': origin, 'trace_duration_ms': float(clock.findtext('.//duration')) * 1000,
            'table_rows': row_count, 'cycles': cycles}


def measure(spec, playback, reference, artifacts, execute):
    inspector = artifacts / 'coreaudio-output-processes'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(INSPECTOR), '-o', str(inspector)])
    client = spec['client_trace']
    configured = artifacts / 'capture-spec.json'
    configured.write_text(json.dumps(playback | {'client_trace': client}, ensure_ascii=False, indent=2) + '\n')
    execute(['node', str(SAFARI), str(configured), str(artifacts), str(inspector), '', '', 'audio-client'], cwd=WEB,
            stdout=artifacts / 'browser-command.log')
    capture = read_json(artifacts / 'capture.json')
    target = capture.get('confirmedTarget')
    result = {'phase': capture['phase'], 'target': target, 'browser_error': capture.get('error'), 'traces': {}}
    checks = {'target_reconfirmed': identified_process(capture),
              'both_traces_completed': capture['phase'] == 'audio_client_trace_complete'}
    graph_span = None
    active_playback = playback | {'graph_capture_quanta': client['active_graph_quanta']}
    for name, graph_spec in [('pilot-marker', playback), ('capture-marker', active_playback)]:
        found = (artifacts / f'{name}.json').is_file() and (artifacts / f'{name}.f32le').is_file()
        checks[f'{name}/observed'] = found
        if found:
            local, pcm = inspect_graph(artifacts, name, graph_spec)
            checks.update({f'{name}/{key}': value for key, value in local.items()})
            if name == 'pilot-marker':
                checks['graph_matches_reference'] = pcm.tobytes() == reference.read_bytes()
            else:
                times = read_json(artifacts / f'{name}.json')['callbackEpochMs']
                graph_span = (times[0], times[-1])
    if target:
        for label, run in capture.get('clientTrace', {}).items():
            if not run['completed']:
                result['traces'][label] = {'error': run.get('error')}
                continue
            try:
                result['traces'][label] = inspect_trace(label, artifacts, target['pid'], execute)
            except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError, subprocess.CalledProcessError) as error:
                result['traces'][label] = {'error': str(error)}
    idle = result['traces'].get('idle', {})
    active = result['traces'].get('active', {})
    checks['idle_without_target_cycles'] = idle.get('cycles') == []
    overlap = []
    if graph_span and 'cycles' in active:
        origin = active['trace_start_epoch_ms']
        overlap = [r for r in active['cycles'] if graph_span[0] <= origin + r['start_ns'] / 1e6
                   and origin + (r['start_ns'] + r['duration_ns']) / 1e6 <= graph_span[1]]
        active['graph_span_epoch_ms'] = graph_span
        active['overlapping_cycles'] = len(overlap)
    checks['cycles_overlap_playing_graph'] = len(overlap) >= client['minimum_overlapping_cycles']
    checks['one_ordered_client_thread'] = (bool(overlap) and len({r['tid'] for r in overlap}) == 1
                                          and all(a['start_ns'] < b['start_ns'] for a, b in zip(overlap, overlap[1:])))
    checks['nominal_cycle_matches_quantum_multiple'] = False
    if len(overlap) > 1:
        intervals = [(b['start_ns'] - a['start_ns']) / 1e6 for a, b in zip(overlap, overlap[1:])]
        frame_equivalent = median(intervals) * playback['sample_rate_hz'] / 1000
        quantum = playback['quantum_frames']
        nominal_frames = round(frame_equivalent / quantum) * quantum
        checks['nominal_cycle_matches_quantum_multiple'] = (nominal_frames > 0 and
            abs(frame_equivalent - nominal_frames) <= client['maximum_nominal_frame_error'])
        active.update(median_interval_ms=median(intervals), min_interval_ms=min(intervals), max_interval_ms=max(intervals),
                      equivalent_frames_at_graph_rate=frame_equivalent, nearest_quantum_multiple_frames=nominal_frames,
                      median_callback_ms=median(r['duration_ns'] for r in overlap) / 1e6)
    return result | {'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    spec = read_json(CASE)
    revision = spec['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    playback_case = CASE.parent / spec['playback_case']
    playback = read_json(playback_case)
    previous = run_manifest(spec['graph_reference_run'], playback['id'], revision)
    if previous[1]['status'] != 'pass' or not previous[1].get('graph_control'):
        parser.error('先行信号を検証済みのグラフ対照が必要です')
    reference = verified_path(previous, 'artifacts/pilot-marker.f32le')
    files = [CASE, playback_case, Path(__file__).resolve(), previous[0] / 'manifest.json', reference, INSPECTOR, SAFARI,
             SAFARI.with_name('safari-webdriver.mjs'), SAFARI.with_name('shared-context-marker-worklet.js')]
    files.extend(WORKSPACE / 'tools' / name for name in ('measure_safari_process_tap_calibration.py',
                 'measure_worklet_live_song_process_tap.py', 'filter_worklet_audioipc_syscalls.py',
                 'measure_fan_crossing_allocations.py', 'measure_uniform_tube.py', 'measure_worklet_fixed.py'))
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'reference_run': previous[0].name,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'xctrace': subprocess.check_output([*XCTRACE, 'version'], text=True).strip(),
               'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
               'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, files, details,
                              lambda artifacts, execute: measure(spec, playback, reference, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
