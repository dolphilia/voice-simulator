"""通常の固定 /i/ 発声で口腔2枝の平滑化とPCMまでの伝搬を観測する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile
from scipy.signal import firwin, lfilter

import measure_fixed_alpha_lf_fundamental_smoothed_branches as smoothing
import measure_fixed_lf as fixed_lf
import measure_fixed_vowel_i_lf_branch_loss as vowel_i
import measure_pcm_output as pcm
import measure_vowel_voice as vowel_voice
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-coupled-smoothing.json'
ROOT = WORKSPACE.parents[2]
TANGENT = smoothing.tangent
SHARED = smoothing.MEAN.shared
READ = smoothing.READ
NATIVE_VOICE = 'crates/vocal-core/src/voice.rs'
VOICE_CLI = 'crates/vocal-cli/src/geometry_case/voice.rs'
UPPER_GLOTTIS = 'crates/chimera/src/sources/glottis.rs'
PATCH = fixed_lf.patch_source
FIELDS = ('lung_boundary_dyn_cm2', 'pressure_sub_dyn_cm2', 'pressure_supra_dyn_cm2',
          'glottal_area_cm2', 'glottal_flow_cm3_s', 'lip_flow_cm3_s', 'nose_flow_cm3_s',
          'radiation_derivative_cm3_s2', 'pressure_34', 'pressure_35', 'pressure_36', 'flow_34_35', 'flow_35_36')
GATE_FIELDS = ('filtered_pressure_drop_dyn_cm2', 'glottal_voicing')
RADIATION = FIELDS.index('radiation_derivative_cm3_s2')
VARIANTS = ('baseline', 'smoothed')
REPLAY_VARIANT = 'pressure_replay'
EDITIONS = ('upstream', 'candidate')
PRESSURE_COLUMNS = ('physical_pressure_drop_dyn_cm2', 'input_pressure_drop_dyn_cm2')
RADIATION_COMPONENTS = ('wall', 'lip', 'nose', 'total')
EVIDENCE = ('observations.npz', 'upstream-network.patch', 'upstream-voice.patch', 'upstream-probe.patch',
            'candidate-network.patch', 'candidate-voice.patch', 'candidate-cli.patch')
GATE_EVIDENCE = (*EVIDENCE, 'voice-input.json')
REPLAY_EVIDENCE = (*GATE_EVIDENCE, *(f'{edition}-pressure-drive.f64' for edition in EDITIONS))

PRESSURE_LOADER = """
fn research_pressure_series(samples: usize) -> Result<Option<Vec<f64>>, Box<dyn Error>> {
    let Some(path) = std::env::var_os("CHIMERA_PRESSURE_REPLAY") else {
        return Ok(None);
    };
    let bytes = std::fs::read(path)?;
    if bytes.len() != samples * 8 {
        return Err("声門入力の圧力差の標本数が一致しません".into());
    }
    let values: Vec<_> = bytes.chunks_exact(8)
        .map(|row| f64::from_le_bytes(row.try_into().expect("8バイトのf64"))).collect();
    if values.iter().any(|value| !value.is_finite()) {
        return Err("声門入力の圧力差に非有限値を使えません".into());
    }
    Ok(Some(values))
}
"""


def archive_inputs(case):
    specs = {}
    for key in ('voice', 'geometry', 'smoothing'):
        spec = case[f'{key}_reference']
        run, manifest = specs[key] = run_manifest(spec['run'], spec['case'], case['upstream_revision'])
        if manifest['status'] != 'pass' or sha256(run / 'manifest.json') != spec['sha256']:
            raise ValueError(f'保存された基準と登録値が一致しません ({run.name})')
    voice, voice_manifest = specs['voice']
    row, = (item for item in voice_manifest['inputs'] if item['path'] == 'cases/vowel-voice-i.json')
    definition = voice / voice_manifest['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('固定 /i/ の保存ケースを照合できません')
    _, _, geometry_case = smoothing.verified_reference(case['geometry_reference'], case['upstream_revision'])
    prior = vowel_i.archive_inputs(READ(geometry_case))
    archive = {
        **{f'{key}-manifest.json': run / 'manifest.json' for key, (run, _) in specs.items()},
        **{key: prior[key] for key in smoothing.BRANCH.IMPULSE.harmonic.NETWORK_FILES},
        'voice-case.json': definition, 'geometry-case.json': geometry_case,
        'upstream-geometry.csv': verified_path(specs['geometry'], 'artifacts/upstream-geometry.csv'),
        'geometry-input.json': verified_path(specs['geometry'], 'artifacts/candidate-topology-case.json'),
        'smoothing-summary.json': verified_path(specs['smoothing'], 'summary.json'),
        **{name: verified_path(specs['voice'], f'artifacts/{name}')
           for name in ('upstream-voice.f32', 'block-128.wav', 'trace.csv', 'upstream-trace.csv')},
    }
    if reference := case.get('standard_reference'):
        record, manifest, definition = smoothing.verified_reference(reference, case['upstream_revision'])
        archive.update({'standard-manifest.json': manifest, 'standard-case.json': definition,
                        'standard-summary.json': verified_path(record, 'summary.json')})
    if reference := case.get('pressure_replay_reference'):
        record, manifest, definition = smoothing.verified_reference(reference, case['upstream_revision'])
        archive.update({'replay-reference-manifest.json': manifest, 'replay-reference-case.json': definition,
                        'replay-reference-states.npz': verified_path(record, 'artifacts/observations.npz'),
                        'replay-reference-voice.json': verified_path(record, 'artifacts/voice-input.json')})
    return archive


def voice_input(case, archive):
    original = READ(archive['voice-case.json'])
    if gate := case.get('pressure_gate'):
        original['voice']['pressure_cm_h2o'] = gate['lung_pressure_cm_h2o']
    return original


def print_observation(values, indent):
    return ''.join(indent + line + '\n' for line in (
        f'let observation = [{", ".join(values)}];',
        'print!("{:?}", observation[0]);',
        'for value in &observation[1..] { print!(",{value:?}"); }',
        'println!();',
    ))


def build(case, out, scratch, execute):
    cfg = case['measurement']
    start = cfg['activation_sample']
    width = repr(float(cfg['smoothing_width_cm3_s']))
    edges = repr(cfg['edges'])
    replay = 'pressure_replay_reference' in case
    radiation_split = 'radiation_split' in case
    if cfg['edges'] != [[34, 35], [35, 36]]:
        raise ValueError('この観測列は節点34～36の連続2枝に対応します')
    upper = scratch / 'upstream'
    upper.mkdir()
    tar = scratch / 'upstream.tar'
    execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
    execute(['tar', '-xf', str(tar), '-C', str(upper)])
    upstream_patch = TANGENT.patch_upstream(upper, law='smooth')
    upper_branch = """    pub fn research_series_flow(&self, a: usize, b: usize) -> f64 {
        let id = (0..self.n_branches).find(|&i| self.b_a[i] == a && self.b_b[i] == b && self.b_kind[i] == KIND_SERIES)
            .expect("観測する直列枝");
        self.u[id]
    }

"""
    upper_step = '                let y = net.step();'
    upper_fields = (
        'net.p[lungs]', 'net.p[sub_node]', 'net.p[supra]', 'a', 'net.u[gp]',
        'net.radiated_flow(self.airway.rad_lips)', 'net.radiated_flow(self.airway.rad_nose)', 'y',
        'net.p[34]', 'net.p[35]', 'net.p[36]', 'net.research_series_flow(34, 35)', 'net.research_series_flow(35, 36)',
    )
    extra_patch = ''
    if 'pressure_gate' in case:
        upper_fields += ('self.glottis.research_filtered_pressure()', 'self.glottis.voicing')
        mark = '    pub fn cycle_phase(&self) -> f64 {'
        extra_patch = PATCH(upper, UPPER_GLOTTIS, ((mark, '''    pub fn research_filtered_pressure(&self) -> f64 {
        self.dp_sm
    }

''' + mark),))
    if replay:
        upper_fields += ('research_physical_dp', 'research_input_dp')
    if radiation_split:
        upper_fields += ('net.research_wall_radiation', 'net.research_total_radiation()')
    upper_observation = print_observation(upper_fields, '                    ')
    upstream_patch += PATCH(upper, TANGENT.UPPER, ((
        '    pub fn research_set_loss_smoothing(', upper_branch + '    pub fn research_set_loss_smoothing('),))
    if radiation_split:
        upstream_patch += PATCH(upper, TANGENT.UPPER, (
            ('    rad_prev_total: f64,', '    rad_prev_total: f64,\n    pub research_wall_radiation: f64,'),
            ('            rad_prev_total: 0.0,', '            rad_prev_total: 0.0,\n            research_wall_radiation: 0.0,'),
            ('        let mut rad_total = wall_rad_sum;', '        self.research_wall_radiation = wall_rad_sum;\n'
             '        let mut rad_total = wall_rad_sum;'),
            ('    pub fn radiated_flow(&self, r: usize) -> f64 {', '''    pub fn research_total_radiation(&self) -> f64 {
        self.rad_prev_total
    }

    pub fn radiated_flow(&self, r: usize) -> f64 {'''),
        ))
    (out / 'upstream-network.patch').write_text(upstream_patch)
    glottis = '    pub glottis: crate::sources::glottis::ParametricGlottis,'
    init = '            glottis: crate::sources::glottis::ParametricGlottis::new(fs),'
    voice_edits = (
        (glottis, glottis + '\n    pub research_smoothing: bool,\n    pub research_observation: bool,\n    research_sample: usize,'),
        (init, init + '\n            research_smoothing: false,\n            research_observation: false,\n'
                      '            research_sample: 0,'),
        (upper_step, f"""                if self.research_smoothing && self.research_sample == {start} {{
                    net.research_set_loss_smoothing(&{edges}, {width}).expect("研究用の平滑化");
                }}
{upper_step}
                if self.research_observation {{
{upper_observation}                    self.research_sample += 1;
                }}"""),
    )
    if replay:
        voice_edits += (
            ('    pub research_observation: bool,',
             '    pub research_observation: bool,\n    pub research_pressure: Option<Vec<f64>>,'),
            ('            research_observation: false,',
             '            research_observation: false,\n            research_pressure: None,'),
            ('                let a = self.glottis.next(net.p[sub_node] - net.p[supra]);',
             f"""                let research_physical_dp = net.p[sub_node] - net.p[supra];
                let research_input_dp = if self.research_sample >= {start} {{
                    self.research_pressure.as_ref().and_then(|series| series.get(self.research_sample))
                        .copied().unwrap_or(research_physical_dp)
                }} else {{
                    research_physical_dp
                }};
                let a = self.glottis.next(research_input_dp);"""),
        )
    (out / 'upstream-voice.patch').write_text(PATCH(upper, fixed_lf.UPPER_VOICE, voice_edits) + extra_patch)
    probe = scratch / vowel_voice.PROBE.name
    shutil.copyfile(vowel_voice.PROBE, probe)
    setup = '            voice.set_gate(gate.parse()?);'
    probe_edits = (
        (setup, setup + '\n            voice.research_observation = true;\n'
                        '            voice.research_smoothing = std::env::var("CHIMERA_SMOOTHING").as_deref() == Ok("1");'),
    )
    if replay:
        probe_edits += (
            ('fn main() -> Result<(), Box<dyn Error>> {', PRESSURE_LOADER + '\nfn main() -> Result<(), Box<dyn Error>> {'),
            (setup, setup + '\n            voice.research_pressure = research_pressure_series(frames.parse::<usize>()? * factor)?;'),
        )
    (out / 'upstream-probe.patch').write_text(PATCH(scratch, probe.name, probe_edits))
    tests = (
        ('airway_adversarial', 'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'),
        ('lung_port', 'the_port_moves_neither_the_folds_pressure_nor_their_effort'),
    )
    if radiation_split:
        tests += (('airway', 'fdtd_impulse_response_agrees_with_frequency_domain_model'),)
    for test, name in tests:
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', test, name], cwd=UPSTREAM,
                stdout=out / f'upstream-{test}.log')
    upstream = SHARED.build_upstream_probe(
        probe, scratch, execute, upstream=upper, cargo_args=('--offline', '--target-dir', str(scratch / 'upper-target')))

    candidate = scratch / 'candidate'
    for path in [*SHARED.candidate_sources(), *TANGENT.CANDIDATE_DATA]:
        target = candidate / path.relative_to(WORKSPACE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    native_branch = """    pub fn research_series_flow(&self, a: usize, b: usize) -> f64 {
        self.branches.iter().find(|branch| branch.nodes == [a, b] && branch.port.is_none())
            .expect("観測する直列枝").flow
    }

"""
    native_patch = TANGENT.patch_core(candidate, law='smooth')
    native_patch += PATCH(candidate, TANGENT.CORE, ((
        '    pub fn research_set_loss_smoothing(', native_branch + '    pub fn research_set_loss_smoothing('),))
    (out / 'candidate-network.patch').write_text(native_patch)
    native_voice_edits = (
        ('impl FixedVoice {\n    pub fn new(', """impl FixedVoice {
    pub fn research_enable_smoothing(&mut self, edges: &[[usize; 2]], width: f64) -> Result<(), &'static str> {
        self.airway.network.research_set_loss_smoothing(edges, width)
    }

    pub fn new("""),
    )
    if replay:
        native_voice_edits += (('    fn step_source(', '''    pub fn research_step_with_pressure(&mut self, pressure: f64) -> Result<VoiceSample, &'static str> {
        self.step_source(Some(pressure), None)
    }

    fn step_source('''),)
    (out / 'candidate-voice.patch').write_text(PATCH(candidate, NATIVE_VOICE, native_voice_edits))
    next_sample = '        let mut sample_index = 0;\n        let mut next_sample = |voice: &mut FixedVoice| {'
    native_fields = (
        's.breath.boundary_pressure_dyn_cm2', 's.subglottal_pressure_dyn_cm2', 's.supraglottal_pressure_dyn_cm2',
        's.glottis.area_cm2', 's.glottal_flow_cm3_s', 's.lip_flow_cm3_s', 's.nose_flow_cm3_s',
        's.radiation.radiation_flow_derivative_cm3_s2', 'net.pressure(34)', 'net.pressure(35)', 'net.pressure(36)',
        'net.research_series_flow(34, 35)', 'net.research_series_flow(35, 36)',
    )
    if 'pressure_gate' in case:
        native_fields += ('s.glottis.filtered_pressure_drop_dyn_cm2', 's.glottis.voicing')
    if replay:
        native_fields += ('s.glottal_physical_pressure_dyn_cm2', 's.glottal_input_pressure_dyn_cm2')
    if radiation_split:
        native_fields += ('s.radiation.wall_radiation_flow_cm3_s', 's.radiation.radiation_flow_cm3_s')
    native_observation = print_observation(native_fields, '            ')
    cli_edits = (
        (next_sample, f"""        let enabled = std::env::var("CHIMERA_SMOOTHING").as_deref() == Ok("1");
{next_sample}
            if enabled && sample_index == {start} {{
                voice.research_enable_smoothing(&{edges}, {width})?;
            }}"""),
        ('            sample_index += 1;\n            sample',
         f"""            let s = sample?;
            let net = &voice.airway().network;
{native_observation}            sample_index += 1;
            Ok::<_, &'static str>(s)"""),
    )
    if replay:
        cli_edits += (
            ('impl Settings {', PRESSURE_LOADER + '\nimpl Settings {'),
            ('        let flow = prescribed_flow(probe, fixed.sample_count.get())?;',
             '''        let flow = prescribed_flow(probe, fixed.sample_count.get())?;
        let research_pressure = research_pressure_series(fixed.sample_count.get())?;
        if research_pressure.is_some() && flow.is_some() {
            return Err("声門圧の置換と声門流量の指定は併用できません".into());
        }'''),
            ('                None => voice.step(),', f'''                None if sample_index >= {start} => match &research_pressure {{
                    Some(pressure) => voice.research_step_with_pressure(pressure[sample_index]),
                    None => voice.step(),
                }},
                None => voice.step(),'''),
        )
    (out / 'candidate-cli.patch').write_text(PATCH(candidate, VOICE_CLI, cli_edits))
    target = scratch / 'candidate-target'
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--target-dir', str(target)],
            cwd=candidate)
    return upstream, target / 'release/vocal-cli'


def read_pcm(path, frames, rate):
    if path.suffix == '.wav':
        sample_rate, signal = wavfile.read(path)
    else:
        sample_rate, signal = rate, np.fromfile(path, dtype='<f4')
    if sample_rate != rate or signal.shape != (frames,) or signal.dtype != np.dtype('<f4') or not np.isfinite(signal).all():
        raise ValueError(f'PCMのレート・型・フレーム数が一致しません ({path.name})')
    return signal


def pressure_drop_before_step(series):
    return np.r_[0., series[:-1, 1] - series[:-1, 2]]


def save_pressure_drives(archive, out):
    drives = {edition: out / f'{edition}-pressure-drive.f64' for edition in EDITIONS}
    with np.load(archive['replay-reference-states.npz'], allow_pickle=False) as reference:
        for edition, path in drives.items():
            pressure_drop_before_step(reference[f'{edition}_baseline']).astype('<f8').tofile(path)
    return drives


def capture(case, archive, out, execute):
    cfg = case['measurement']
    count, rate, output = (cfg[key] for key in ('sample_count', 'internal_rate_hz', 'output_rate_hz'))
    frames = count * output // rate
    original = voice_input(case, archive)
    definition = archive['voice-case.json']
    if 'pressure_gate' in case:
        definition = out / 'voice-input.json'
        definition.write_text(json.dumps(original, ensure_ascii=False, indent=2) + '\n')
    voice = original['voice']
    args = ['render', 'i', rate, output, frames, *(voice[key] for key in
            ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))]
    states = {}
    replay = 'pressure_replay_reference' in case
    variants = (*VARIANTS, REPLAY_VARIANT) if replay else VARIANTS
    drives = save_pressure_drives(archive, out) if replay else {}
    with TemporaryDirectory(prefix='coupled-smoothing-', dir=out) as name:
        scratch = Path(name)
        upstream, candidate = build(case, out, scratch, execute)
        for variant in variants:
            flag = f'CHIMERA_SMOOTHING={int(variant != "baseline")}'
            env = ['env', '-u', 'CHIMERA_PRESSURE_REPLAY', flag] if replay else ['env', flag]
            upper_env = [*env, f'CHIMERA_PRESSURE_REPLAY={drives["upstream"]}'] if variant == REPLAY_VARIANT else env
            native_env = [*env, f'CHIMERA_PRESSURE_REPLAY={drives["candidate"]}'] if variant == REPLAY_VARIANT else env
            upper = scratch / variant
            upper.mkdir()
            trace = scratch / 'trace.csv'
            execute([*upper_env, str(upstream), *map(str, args), str(upper)], cwd=UPSTREAM, stdout=trace)
            states[f'upstream_{variant}'] = np.loadtxt(trace, delimiter=',', ndmin=2)
            states[f'upstream_{variant}_pcm'] = read_pcm(upper / 'upstream-voice.f32', frames, output)
            candidate_wave = scratch / f'{variant}.wav'
            execute([*native_env, str(candidate), 'render-pcm', str(definition), str(candidate_wave),
                     str(scratch / f'{variant}-pcm.csv'), str(cfg['host_block_frames'])], stdout=trace)
            states[f'candidate_{variant}'] = np.loadtxt(trace, delimiter=',', ndmin=2)
            states[f'candidate_{variant}_pcm'] = read_pcm(candidate_wave, frames, output)
    columns = len(FIELDS) + (len(GATE_FIELDS) if 'pressure_gate' in case else 0)
    pressure_end = columns + (len(PRESSURE_COLUMNS) if replay else 0)
    radiation_split = 'radiation_split' in case
    width = pressure_end + (2 if radiation_split else 0)
    for name, data in tuple(states.items()):
        if name.endswith('_pcm'):
            continue
        if data.shape != (count, width) or not np.isfinite(data).all():
            raise ValueError('内部標本の数、観測列、有限性が規定と一致しません')
        if radiation_split:
            states[f'{name}_radiation'] = data[:, [pressure_end, FIELDS.index('lip_flow_cm3_s'),
                                                  FIELDS.index('nose_flow_cm3_s'), pressure_end + 1]]
        if replay:
            states[f'{name}_pressures'] = data[:, columns:pressure_end]
        if replay or radiation_split:
            states[name] = data[:, :columns]
    np.savez_compressed(out / 'observations.npz', **states)


def same_bits(left, right):
    return left.shape == right.shape and left.dtype == right.dtype and left.tobytes() == right.tobytes()


def first_difference(left, right):
    indices = np.flatnonzero(left != right)
    return int(indices[0]) if indices.size else None


def branch_balance(case, archive, data, *, smoothed):
    cfg = case['measurement']
    _, geometry = smoothing.MEAN.fixed.read_upper_geometry(archive['upstream-geometry.csv'])
    _, topology, _ = smoothing.BRANCH.IMPULSE.source_elements(archive)
    rows = [next(row for row in topology if list(row[:2].astype(int)) == edge) for edge in cfg['edges']]
    links = np.asarray(rows)
    left, right = links[:, :2].astype(int).T
    path = np.column_stack((left, right, np.arange(len(links))))
    kf = smoothing.MEAN.drag_on_path(path, geometry)
    kb = smoothing.MEAN.drag_on_path(path[:, [1, 0, 2]], geometry)
    lookback = data[cfg['activation_sample'] - 1:]
    pressure, flow = lookback[:, 8:11], lookback[:, 11:len(FIELDS)]
    current = flow[1:]
    observed = (pressure[:-1, :2] - pressure[:-1, 1:]
                - cfg['internal_rate_hz'] * links[:, 3] * np.diff(flow, axis=0) - links[:, 4] * current)
    expected = np.where(current >= 0, kf, kb) * current * abs(current)
    if smoothed:
        expected *= 1 - np.maximum(1 - abs(current) / cfg['smoothing_width_cm3_s'], 0.)**3
    work = current * observed
    return {'pressure_relative_error': float(abs(observed - expected).max() / abs(expected).max()),
            'minimum_work_erg_s': float(work.min()),
            'negative_work_samples': int((work < -cfg['negative_work_relative_tolerance'] * abs(work).max()).sum())}


def pressure_gate_comparison(case, base, trial, first):
    cfg = case['measurement']
    gate = case['pressure_gate']
    rate = cfg['internal_rate_hz']
    start, stop = cfg['steady_window_samples']
    lo, hi = gate['pressure_bounds_dyn_cm2']
    pressure_pole = np.exp(-2 * np.pi * gate['pressure_smoothing_hz'] / rate)
    voicing_pole = np.exp(-2 * np.pi * gate['voicing_smoothing_hz'] / rate)
    variants, voicing = {}, {}
    for name, series in zip(VARIANTS, (base, trial), strict=True):
        measured_pressure, measured_voicing = series[:, -2:].T
        # 声門は気道を現在の標本へ進める前の圧力を読む。
        pressure_input = pressure_drop_before_step(series)
        filtered = lfilter([1 - pressure_pole], [1, -pressure_pole], pressure_input)
        fraction = np.clip((filtered - lo) / (hi - lo), 0., 1.)
        gate_value = fraction * fraction * (3. - 2. * fraction)
        # この固定姿勢の開大面積は接触ゲートの遷移域より小さく、閉鎖指令はゼロ。
        voicing[name] = lfilter([1 - voicing_pole], [1, -voicing_pole], gate_value)
        window = measured_pressure[start:stop]
        variants[name] = {
            'filtered_pressure_min_dyn_cm2': float(window.min()),
            'filtered_pressure_max_dyn_cm2': float(window.max()),
            'transition_fraction': float(np.mean((window > lo) & (window < hi))),
            'independent_pressure_max_error_dyn_cm2': float(abs(filtered - measured_pressure).max()),
            'independent_voicing_max_error': float(abs(voicing[name] - measured_voicing).max()),
        }
    window = slice(start, stop)
    filtered_sample, voicing_sample = (first[key] for key in GATE_FIELDS)
    area_sample = first['glottal_area_cm2']
    supra = first['pressure_supra_dyn_cm2']
    opening = gate['static_opening_cm2'] * -np.expm1(
        -(1 + np.arange(start, stop)) / (rate * gate['static_opening_time_s']))
    base_voicing = base[window, -1]
    shape = np.divide(base[window, 3] - opening, base_voicing,
                      out=np.zeros(stop - start), where=base_voicing > 0)
    reconstructed = shape * (voicing['smoothed'][window] - voicing['baseline'][window])
    measured = trial[window, 3] - base[window, 3]
    error = float(abs(reconstructed - measured).max())
    checks = {
        'independent_pressure_gate_and_area': (
            all(row['independent_pressure_max_error_dyn_cm2'] < gate['pressure_max_error_lt_dyn_cm2']
                and row['independent_voicing_max_error'] < gate['voicing_max_error_lt'] for row in variants.values())
            and error < gate['area_change_max_error_lt_cm2']),
    }
    report = {
        'variants': variants,
        'max_area_change_cm2': float(abs(measured).max()),
        'independent_area_change_max_error_cm2': error,
        'max_filtered_pressure_change_dyn_cm2': float(abs(trial[window, -2] - base[window, -2]).max()),
        'max_voicing_change': float(abs(trial[window, -1] - base[window, -1]).max()),
        'hypotheses': {
            'transition_fraction_ge_target': all(
                row['transition_fraction'] >= gate['hypothesis_minimum_transition_fraction'] for row in variants.values()),
            'pressure_then_voicing_then_area': (
                None not in (supra, filtered_sample, voicing_sample, area_sample)
                and supra < filtered_sample <= voicing_sample <= area_sample),
        },
    }
    return report, checks


def reconstruct_pcm(state, taps, factor, pole, gain, rate):
    bandlimited = lfilter(taps, [1.0], state[:, RADIATION])[factor - 1::factor]
    highpassed = lfilter([1, -1], [1, -pole], gain * bandlimited)
    return pcm.independent_limiter(highpassed, rate)[2]


def analyze_pressure_replay(case, archive, out, data, taps, factor, pole, gain, rate):
    cfg = case['measurement']
    start, stop = cfg['steady_window_samples']
    observation = slice(start, stop)
    frames = slice(start // factor, stop // factor)
    reference_case = READ(archive['replay-reference-case.json'])
    registered_voice = READ(archive['replay-reference-voice.json'])
    checks = {
        'replay_uses_registered_low_pressure_case': (
            case['measurement'] == reference_case['measurement'] and case['pressure_gate'] == reference_case['pressure_gate']
            and READ(out / 'voice-input.json') == registered_voice),
    }
    reports, area_effect, peaks = {}, {}, []
    with np.load(archive['replay-reference-states.npz'], allow_pickle=False) as reference:
        for edition in EDITIONS:
            base, coupled, replay = (data[f'{edition}_{variant}'] for variant in (*VARIANTS, REPLAY_VARIANT))
            base_pcm, coupled_pcm, replay_pcm = (data[f'{edition}_{variant}_pcm']
                                                for variant in (*VARIANTS, REPLAY_VARIANT))
            archived_base = reference[f'{edition}_baseline']
            drive = np.fromfile(out / f'{edition}-pressure-drive.f64', dtype='<f8')
            checks[f'{edition}/unmodified_and_smoothed_reference_bits'] = (
                same_bits(base, archived_base) and same_bits(coupled, reference[f'{edition}_smoothed'])
                and same_bits(base_pcm, reference[f'{edition}_baseline_pcm'])
                and same_bits(coupled_pcm, reference[f'{edition}_smoothed_pcm']))
            pair = data[f'{edition}_{REPLAY_VARIANT}_pressures']
            checks[f'{edition}/physical_and_applied_pressure_verified'] = (
                same_bits(drive, pressure_drop_before_step(archived_base))
                and same_bits(pair[:, 0], pressure_drop_before_step(replay))
                and same_bits(pair[:, 1], drive)
                and all(same_bits(data[f'{edition}_{name}_pressures'],
                                  np.repeat(pressure_drop_before_step(data[f'{edition}_{name}'])[:, None], 2, axis=1))
                        for name in VARIANTS))
            indices = [FIELDS.index('glottal_area_cm2'), *range(len(FIELDS), len(FIELDS) + len(GATE_FIELDS))]
            checks[f'{edition}/area_and_gate_reproduce_baseline'] = same_bits(replay[:, indices], base[:, indices])
            checks[f'{edition}/replay_unchanged_before_switch'] = (
                same_bits(replay[:start], base[:start]) and same_bits(replay_pcm[:frames.start], base_pcm[:frames.start]))
            balance = branch_balance(case, archive, replay, smoothed=True)
            predicted = reconstruct_pcm(replay, taps, factor, pole, gain, rate)
            pcm_error = float(abs(replay_pcm.astype(float) - predicted).max())
            checks[f'{edition}/replay_independent_pcm_and_branch_balance'] = (
                pcm_error < cfg['pcm_absolute_error_lt']
                and balance['pressure_relative_error'] < cfg['branch_pressure_law_peak_relative_error_lt']
                and balance['negative_work_samples'] == 0)
            waves = [signal.astype(float) for signal in (base_pcm, coupled_pcm, replay_pcm)]
            total = waves[1][frames] - waves[0][frames]
            direct = waves[2][frames] - waves[0][frames]
            area = waves[1][frames] - waves[2][frames]
            checks[f'{edition}/pcm_differences_add_to_total'] = np.array_equal(direct + area, total)
            norm = np.linalg.norm(total)
            projection = float(np.dot(area, total) / norm**2)
            rms_scale = np.sqrt(len(total))
            first_area = first_difference(coupled[:, 3], replay[:, 3])
            first_radiation = first_difference(coupled[:, RADIATION], replay[:, RADIATION])
            first_voice = first_difference(coupled_pcm, replay_pcm)
            first_full = first_difference(base_pcm, coupled_pcm)
            first_direct = first_difference(base_pcm, replay_pcm)
            area_effect[edition] = area
            peaks.append(max(float(abs(wave[frames]).max()) for wave in waves))
            reports[edition] = {
                'first_pressure_input_difference_from_physical_sample': first_difference(pair[:, 0], pair[:, 1]),
                'first_area_difference_from_coupled_sample': first_area,
                'first_radiation_difference_from_coupled_sample': first_radiation,
                'first_pcm_frame_full_effect': first_full, 'first_pcm_frame_without_area_path': first_direct,
                'first_pcm_frame_area_path': first_voice,
                'peak_physical_glottal_flow_change_cm3_s': float(abs(replay[observation, 4] - base[observation, 4]).max()),
                'peak_physical_pressure_not_fed_to_model_dyn_cm2': float(abs(pair[observation, 0] - pair[observation, 1]).max()),
                'total_delta_pcm_rms': float(norm / rms_scale),
                'without_area_path_delta_pcm_rms': float(np.linalg.norm(direct) / rms_scale),
                'area_path_delta_pcm_rms': float(np.linalg.norm(area) / rms_scale),
                'area_path_rms_ratio': float(np.linalg.norm(area) / norm),
                'area_path_signed_projection': projection,
                'cross_term_relative_to_total_energy': float(2 * np.dot(direct, area) / norm**2),
                'independent_pcm_error': pcm_error, **balance,
                'hypotheses': {
                    'area_path_follows_area_and_radiation': (
                        first_area is not None and first_radiation is not None and first_voice is not None
                        and first_area <= first_radiation <= (first_voice + 1) * factor - 1),
                    'direct_pcm_difference_preserves_onset': (
                        first_direct is not None and first_voice is not None
                        and first_full == first_direct and first_direct < first_voice),
                },
            }
    state_error = TANGENT.peak_error(data['candidate_pressure_replay'][observation],
                                    data['upstream_pressure_replay'][observation])
    cross_error = float(abs(area_effect['candidate'] - area_effect['upstream']).max())
    tolerance = max(cfg['pcm_delta_relative_error_lt'] * float(abs(area_effect['upstream']).max()),
                    2 * float(np.spacing(np.float32(max(peaks)))))
    checks['replay_agrees_between_implementations'] = state_error < cfg['component_peak_relative_error_lt'] and cross_error <= tolerance
    return {'editions': reports, 'state_peak_relative_error': state_error,
            'area_pcm_cross_edition_error': cross_error, 'area_pcm_cross_edition_tolerance': tolerance}, checks


def analyze(case, archive, out):
    cfg = case['measurement']
    voice, geom = (READ(archive[key]) for key in ('voice-case.json', 'geometry-input.json'))
    factor = cfg['internal_rate_hz'] // cfg['output_rate_hz']
    count, rate = cfg['sample_count'], cfg['output_rate_hz']
    frames = count // factor
    start, stop = cfg['steady_window_samples']
    activation = cfg['activation_sample']
    gain = voice['voice']['output_gain']
    archive_pcm = {'candidate': 'block-128.wav', 'upstream': 'upstream-voice.f32'}
    archive_trace = {'candidate': 'trace.csv', 'upstream': 'upstream-trace.csv'}
    taps = firwin(factor * 24 + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    pole = np.exp(-2 * np.pi * 25 / rate)
    checks = {
        'registered_voice_and_geometry': (
            voice['body'] == geom['body'] == 'male' and voice['posture'] == geom['posture']
            and voice['fixed_airway']['sample_rate_hz'] == cfg['internal_rate_hz']
            and voice['fixed_airway']['sample_count'] == count
            and voice['voice']['output_sample_rate_hz'] == rate and voice['voice']['f0_hz'] == 110
            and activation == start and stop <= count and count % factor == 0
            and all(READ(archive['smoothing-summary.json'])['checks'].values())),
    }
    results, pcm_effect = {}, {}
    gate = case.get('pressure_gate')
    fields = (*FIELDS, *GATE_FIELDS) if gate else FIELDS
    if gate:
        standard_case = READ(archive['standard-case.json'])
        actual = READ(out / 'voice-input.json')
        checks['only_registered_lung_pressure_changed'] = (
            case['measurement'] == standard_case['measurement']
            and actual == voice_input(case, archive)
            and actual == {**voice, 'voice': {**voice['voice'], 'pressure_cm_h2o': gate['lung_pressure_cm_h2o']}}
            and 0.0 < gate['lung_pressure_cm_h2o'] < voice['voice']['pressure_cm_h2o'])
    with np.load(out / 'observations.npz', allow_pickle=False) as data:
        for variant in VARIANTS:
            before = data[f'upstream_{variant}'][start:stop]
            candidate = data[f'candidate_{variant}'][start:stop]
            series = TANGENT.peak_error(candidate, before)
            upstream_pcm = data[f'upstream_{variant}_pcm']
            native_pcm = data[f'candidate_{variant}_pcm']
            error = float(abs(upstream_pcm.astype(float) - native_pcm).max())
            checks[f'{variant}/upstream_components_and_pcm_match'] = (
                series < cfg['component_peak_relative_error_lt'] and error < cfg['pcm_absolute_error_lt'])
            results[variant] = {'upstream_series_peak_relative_error': series, 'upstream_pcm_max_error': error,
                                'editions': {}}
            for edition in archive_pcm:
                state = data[f'{edition}_{variant}']
                wave = data[f'{edition}_{variant}_pcm']
                reconstructed = reconstruct_pcm(state, taps, factor, pole, gain, rate)
                pcm_error = float(abs(wave.astype(float) - reconstructed).max())
                balance = branch_balance(case, archive, state, smoothed=variant == 'smoothed')
                checks[f'{edition}/{variant}/independent_pcm_and_branch_balance'] = (
                    pcm_error < cfg['pcm_absolute_error_lt']
                    and balance['pressure_relative_error'] < cfg['branch_pressure_law_peak_relative_error_lt']
                    and balance['negative_work_samples'] == 0)
                results[variant]['editions'][edition] = {**balance, 'independent_pcm_error': pcm_error}
        for edition in archive_pcm:
            base = data[f'{edition}_baseline']
            trial = data[f'{edition}_smoothed']
            base_pcm, trial_pcm = (data[f'{edition}_{variant}_pcm'] for variant in VARIANTS)
            if not gate:
                _, samples = pcm.read_columns(archive[archive_trace[edition]], frames)
                archived = np.column_stack([samples[key] for key in FIELDS[:8]])
                checks[f'{edition}/archived_pcm_and_output_clock_observations'] = (
                    same_bits(base_pcm, read_pcm(archive[archive_pcm[edition]], frames, rate))
                    and same_bits(base[factor - 1::factor, :8], archived))
            flows = base[activation:, 11:len(FIELDS)]
            eligible = (abs(flows) < cfg['smoothing_width_cm3_s']) & (flows != 0)
            active = np.flatnonzero(eligible.any(axis=1))
            predicted = int(active[0]) + activation if active.size else None
            first = {key: first_difference(base[:, col], trial[:, col]) for col, key in enumerate(fields)}
            branch_onset = min((first[key] for key in FIELDS[-2:] if first[key] is not None), default=None)
            frame = first_difference(base_pcm, trial_pcm)
            frame_end = None if frame is None else (frame + 1) * factor - 1
            sup, flow, rad = (first[key] for key in ('pressure_supra_dyn_cm2', 'glottal_flow_cm3_s', FIELDS[RADIATION]))
            checks[f'{edition}/bitwise_before_switch'] = (
                same_bits(base[:activation], trial[:activation])
                and same_bits(base_pcm[:activation // factor], trial_pcm[:activation // factor]))
            wave_delta = trial_pcm.astype(float) - base_pcm
            pcm_effect[edition] = wave_delta
            pcm_peak = float(abs(wave_delta).max())
            scale = np.sqrt(np.mean(base_pcm.astype(float)**2))
            results[edition] = {
                'first_internal_sample': first, 'first_eligible_sample': predicted,
                'eligible_samples_by_branch': eligible.sum(axis=0).tolist(),
                'first_pcm_frame': frame, 'first_pcm_frame_internal_end': frame_end,
                'pcm_delta_peak': pcm_peak, 'pcm_delta_rms_relative_to_baseline': float(np.sqrt(np.mean(wave_delta**2)) / scale),
                'hypotheses': {'branch_change_starts_at_first_eligible_sample': branch_onset is not None and branch_onset == predicted,
                               'pressure_precedes_glottal_flow': branch_onset is not None and sup is not None
                               and flow is not None and branch_onset <= sup < flow,
                               'radiation_precedes_output_frame_end': rad is not None and frame_end is not None and rad <= frame_end},
            }
            if gate:
                report, gate_checks = pressure_gate_comparison(case, base, trial, first)
                results[edition]['pressure_gate'] = report
                checks.update({f'{edition}/{key}': value for key, value in gate_checks.items()})
        replay_report = {}
        if 'pressure_replay_reference' in case:
            report, replay_checks = analyze_pressure_replay(case, archive, out, data, taps, factor, pole, gain, rate)
            replay_report['pressure_replay'] = report
            checks.update(replay_checks)
    peak = float(abs(pcm_effect['upstream']).max())
    discrepancy = float(abs(pcm_effect['candidate'] - pcm_effect['upstream']).max())
    relative = discrepancy / peak if peak else 0.
    checks['editions_agree_on_pcm_delta'] = relative < cfg['pcm_delta_relative_error_lt'] and (peak > 0 or discrepancy == 0)
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'results': results,
            'pcm_delta_comparison': {'max_absolute_error': discrepancy, 'max_relative_error': relative}, **replay_report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case_path = args.case.resolve()
    case = READ(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(case)

    def measure(out, execute):
        capture(case, archive, out, execute)
        return analyze(case, archive, out)

    inputs = [case_path, Path(__file__), *archive.values(), vowel_voice.PROBE,
              *SHARED.candidate_sources(), *TANGENT.CANDIDATE_DATA,
              *(Path(module.__file__) for module in (smoothing, fixed_lf, vowel_i, pcm, SHARED, TANGENT)),
              UPSTREAM / TANGENT.UPPER, UPSTREAM / fixed_lf.UPPER_VOICE, UPSTREAM / 'Cargo.lock',
              *(UPSTREAM / f'crates/chimera/tests/{name}.rs' for name in ('airway_adversarial', 'lung_port'))]
    if 'pressure_gate' in case:
        inputs.extend((UPSTREAM / UPPER_GLOTTIS, UPSTREAM / 'crates/chimera/src/math.rs',
                       UPSTREAM / 'crates/chimera/src/physics.rs'))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return SHARED.record_measurement(args.run_id, case_path, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
