//! 人間の固定声道と可動声道を呼気と声門で駆動する。

use std::num::NonZeroUsize;

use crate::airway::human::{HumanAirway, TurbulenceSettings};
use crate::airway::network::NetworkSample;
use crate::airway::tract_control::HumanTractControl;
use crate::anatomy::{AreaSample, Articulation, BodyMix, BodyName, Point};
use crate::articulators::{ARTICULATOR_COUNT, Articulator, ArticulatorBank, BlendedTarget};
use crate::breath::{Breath, BreathControl, BreathSample, BreathSettings};
use crate::glottis::{
    DEFAULT_CYCLE_SEED, DEFAULT_VIBRATO_RATE_HZ, Glottis, GlottisParameters, GlottisSample,
};

use crate::phonetics::beatbox::male_ready_targets;
#[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
use crate::render_allocation_probe::{Phase as AllocationPhase, scope as allocation_scope};
use crate::score::{CONTROL_COUNT, ControlKey, Gesture, blend_at};

#[derive(Clone, Copy, Debug)]
pub struct FixedVoiceSettings {
    pub pressure_cm_h2o: f64,
    pub gate: f64,
    pub f0_hz: f64,
    pub breathiness: f64,
    pub tension: f64,
}

pub struct VoiceSample {
    pub breath: BreathSample,
    pub glottis: GlottisSample,
    pub glottal_flow_cm3_s: f64,
    pub abduction_cm2: f64,
    pub glottal_physical_pressure_dyn_cm2: f64,
    pub glottal_input_pressure_dyn_cm2: f64,
    pub subglottal_pressure_dyn_cm2: f64,
    pub supraglottal_pressure_dyn_cm2: f64,
    pub lip_flow_cm3_s: f64,
    pub nose_flow_cm3_s: f64,
    pub radiation: NetworkSample,
}

pub struct FixedVoice {
    airway: HumanAirway,
    breath: Breath,
    glottis: Glottis,
    breath_control: BreathControl,
    abduction_cm2: f64,
    base_abduction_cm2: f64,
    base_f0_hz: f64,
    smoothed_f0_hz: f64,
    control_block_samples: usize,
    samples_until_control: usize,
}

impl FixedVoice {
    pub fn new(
        airway: HumanAirway,
        internal_rate_hz: u32,
        control_block_samples: usize,
        settings: FixedVoiceSettings,
    ) -> Result<Self, &'static str> {
        let FixedVoiceSettings {
            pressure_cm_h2o,
            gate,
            f0_hz,
            breathiness,
            tension,
        } = settings;
        if !(0.0..=1.5).contains(&gate)
            || ![breathiness, tension]
                .into_iter()
                .all(|x| (0.0..=1.0).contains(&x))
        {
            return Err("呼気ゲートは0〜1.5、ブレス感と緊張は0〜1で指定してください");
        }
        let body = airway.body;
        let area_scale = body.scale * body.scale;
        let base_abduction_cm2 = (0.1 * breathiness * breathiness) * area_scale;
        let breath = Breath::new(
            internal_rate_hz,
            BreathSettings {
                pressure_cm_h2o,
                body_scale: body.scale,
                control_block_samples,
                series_resistance_cgs: airway.lung_series_resistance_cgs,
                compensate: true,
            },
        )?;
        // 上流の標準の明るさで、周期とピッチの変動を0にした条件。
        // 振動面積は声帯の振動部長と移動距離の積、静的な開口は体型の面積比に従う。
        let glottis = Glottis::new(
            internal_rate_hz,
            GlottisParameters {
                f0_hz,
                amplitude_cm2: 0.17 * body.fold_length * body.scale,
                chink_cm2: (0.008 + 0.03 * breathiness) * area_scale,
                open_quotient: 0.78 - 0.36 * tension + body.open_phase,
                open_with_abduction: 0.98,
                skew: 0.56 + 0.16 * tension,
                closure_sharpness: 0.4 * tension + 1.375 * (tension - 0.6).max(0.0),
                effort: 0.0,
                closure: 0.0,
                threshold_dyn_cm2: 2.5 * 980.665,
                jitter: 0.0,
                shimmer: 0.0,
                cycle_seed: DEFAULT_CYCLE_SEED,
                drift_cents: 0.0,
                vibrato_depth_cents: 0.0,
                vibrato_rate_hz: DEFAULT_VIBRATO_RATE_HZ,
                fry: 0.0,
                diplophonia: 0.0,
                chaos: 0.0,
            },
        )?;
        Ok(Self {
            airway,
            breath,
            glottis,
            breath_control: BreathControl {
                performer_gate: gate,
                score_level: 0.0,
                score_activity: 0.0,
            },
            abduction_cm2: base_abduction_cm2,
            base_abduction_cm2,
            base_f0_hz: f0_hz,
            smoothed_f0_hz: f0_hz,
            control_block_samples,
            samples_until_control: 0,
        })
    }

    /// 次の制御更新で使う演奏者の呼気目標を変更する。
    pub fn set_performer_gate(&mut self, goal: f64) -> Result<(), &'static str> {
        if !(0.0..=1.5).contains(&goal) {
            return Err("呼気ゲートは0〜1.5の範囲で指定してください");
        }
        self.breath_control.performer_gate = goal;
        Ok(())
    }

    fn apply_score(
        &mut self,
        blend: &[BlendedTarget; CONTROL_COUNT],
        dt: f64,
    ) -> Result<(), &'static str> {
        let blended = |key: ControlKey| blend[key.index()];
        let opening = blended(ControlKey::Abduction);
        let closure = blended(ControlKey::Closure);
        let breath = blended(ControlKey::Breath);
        let pitch = blended(ControlKey::F0);
        let vibrato = blended(ControlKey::Vibrato);
        for target in [opening, closure, breath, pitch, vibrato] {
            target.validate()?;
        }
        let scale = self.airway.body.scale;
        let next_opening = self.base_abduction_cm2
            + opening.value * (opening.weight / 2.0).min(1.0) * (scale * scale);
        if !next_opening.is_finite() || next_opening < 0.0 {
            return Err("スコアによる声門の開大面積が範囲外です");
        }
        let closure = (closure.value * (closure.weight / 2.0).min(1.0)).max(0.0);
        let vibrato = (vibrato.value * vibrato.weight) / (0.05 + vibrato.weight);
        let (target_f0, glide) = if pitch.weight > 0.0 {
            (
                (self.base_f0_hz * 0.02 + pitch.value * pitch.weight) / (0.02 + pitch.weight),
                0.03,
            )
        } else {
            (self.base_f0_hz, 0.06)
        };
        self.update_pitch(target_f0, dt, glide, closure, vibrato)?;
        self.abduction_cm2 = next_opening;
        self.breath_control.score_activity = breath.weight.min(1.0);
        self.breath_control.score_level = breath.value;
        Ok(())
    }

    fn update_pitch(
        &mut self,
        target_f0: f64,
        dt: f64,
        glide: f64,
        closure: f64,
        vibrato: f64,
    ) -> Result<(), &'static str> {
        let next_f0 = self.smoothed_f0_hz
            * libm::pow(
                target_f0 / self.smoothed_f0_hz,
                1.0 - libm::exp(-dt / glide),
            );
        self.glottis.set_score_controls(next_f0, closure, vibrato)?;
        self.smoothed_f0_hz = next_f0;
        Ok(())
    }

    pub fn step(&mut self) -> Result<VoiceSample, &'static str> {
        self.step_source(None, None)
    }

    /// 固定声道の比較で、声門枝の流量を気管から咽頭へ向かう cm³/s で指定する。
    /// 声帯振動の観測値は参考値として計算する。放射に寄与する枝の流量は指定値に従う。
    pub fn step_with_prescribed_glottal_flow(
        &mut self,
        flow_cm3_s: f64,
    ) -> Result<VoiceSample, &'static str> {
        if !flow_cm3_s.is_finite() {
            return Err("指定する声門流量には有限の値が必要です");
        }
        self.step_source(None, Some(flow_cm3_s))
    }

    fn step_source(
        &mut self,
        pressure_override: Option<f64>,
        prescribed_flow_cm3_s: Option<f64>,
    ) -> Result<VoiceSample, &'static str> {
        let airway = &mut self.airway;
        let network = &mut airway.network;
        if self.samples_until_control == 0 {
            self.breath.control(self.breath_control);
            self.samples_until_control = self.control_block_samples;
        }
        self.samples_until_control -= 1;
        let breath = self.breath.step(network.branch_flow(airway.lung_port));
        self.glottis.set_effort(breath.effort)?;
        network.set_fixed_pressure(airway.lungs, breath.boundary_pressure_dyn_cm2)?;
        let physical_pressure_drop =
            network.pressure(airway.subglottal) - network.pressure(airway.pharynx_entry);
        let input_pressure_drop = pressure_override.unwrap_or(physical_pressure_drop);
        let glottis = self.glottis.step(input_pressure_drop, self.abduction_cm2);
        #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
        crate::render_phase_probe::mark_airway_sample(
            crate::render_phase_probe::Phase::AirwayStart,
        );
        let radiation = if let Some(flow) = prescribed_flow_cm3_s {
            network.set_port_area(airway.glottis_port, 0.0)?;
            network.step_with_prescribed_flow(
                airway.pharynx_entry,
                0.0,
                Some((airway.glottis_port, flow)),
            )
        } else {
            network.set_port_area(airway.glottis_port, glottis.area_cm2)?;
            network.step(airway.pharynx_entry, 0.0)
        };
        #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
        crate::render_phase_probe::mark_airway_sample(crate::render_phase_probe::Phase::AirwayEnd);
        Ok(VoiceSample {
            breath,
            glottis,
            radiation,
            glottal_flow_cm3_s: network.branch_flow(airway.glottis_port),
            abduction_cm2: self.abduction_cm2,
            glottal_physical_pressure_dyn_cm2: physical_pressure_drop,
            glottal_input_pressure_dyn_cm2: input_pressure_drop,
            subglottal_pressure_dyn_cm2: network.pressure(airway.subglottal),
            supraglottal_pressure_dyn_cm2: network.pressure(airway.pharynx_entry),
            lip_flow_cm3_s: network.radiation_flow(airway.lips).expect("口端の放射負荷"),
            nose_flow_cm3_s: network
                .radiation_flow(airway.nostrils)
                .expect("鼻端の放射負荷"),
        })
    }
}

/// 調音、声道形状、呼気と声門を共通の内部クロックで更新する人間の音源。
pub struct ArticulatedVoice {
    voice: FixedVoice,
    tract: HumanTractControl,
    bank: ArticulatorBank,
    blend: [BlendedTarget; ARTICULATOR_COUNT],
    control_seconds: f64,
    base_weight: f64,
    project_contacts: bool,
    score: Option<Vec<Gesture>>,
    turbulence: Option<TurbulenceSettings>,
    clock_seconds: f64,
    internal_rate_hz: u32,
    initial_source: FixedVoiceSettings,
}

impl ArticulatedVoice {
    pub fn new(
        internal_rate_hz: u32,
        control_block_samples: usize,
        bank: ArticulatorBank,
        base_weight: f64,
        project_contacts: bool,
        settings: FixedVoiceSettings,
    ) -> Result<Self, &'static str> {
        Self::for_body(
            internal_rate_hz,
            control_block_samples,
            bank,
            base_weight,
            project_contacts,
            settings,
            BodyName::Male.into(),
        )
    }

    pub fn for_body(
        internal_rate_hz: u32,
        control_block_samples: usize,
        bank: ArticulatorBank,
        base_weight: f64,
        project_contacts: bool,
        settings: FixedVoiceSettings,
        body: BodyMix,
    ) -> Result<Self, &'static str> {
        Self::for_tract(
            internal_rate_hz,
            control_block_samples,
            bank,
            base_weight,
            project_contacts,
            settings,
            (body, None),
        )
    }

    /// 体型と任意の口腔セル数から可動声道を初期化する。
    pub fn for_tract(
        internal_rate_hz: u32,
        control_block_samples: usize,
        bank: ArticulatorBank,
        base_weight: f64,
        project_contacts: bool,
        settings: FixedVoiceSettings,
        (body, oral_cells): (BodyMix, Option<NonZeroUsize>),
    ) -> Result<Self, &'static str> {
        if !base_weight.is_finite() || base_weight < 0.0 {
            return Err("基準の調音重みには有限の非負値を指定してください");
        }
        let tract =
            HumanTractControl::with_oral_cells(internal_rate_hz, body, bank.posture(), oral_cells)?;
        let airway = HumanAirway::from_targets(internal_rate_hz, tract.targets())?;
        let voice = FixedVoice::new(airway, internal_rate_hz, control_block_samples, settings)?;
        Ok(Self {
            voice,
            tract,
            bank,
            blend: [BlendedTarget::default(); ARTICULATOR_COUNT],
            control_seconds: control_block_samples as f64 / f64::from(internal_rate_hz),
            base_weight,
            project_contacts,
            score: None,
            turbulence: None,
            clock_seconds: 0.0,
            internal_rate_hz,
            initial_source: settings,
        })
    }

    /// 発話・歌唱で共有する成人男性の調音初期化。
    pub fn for_speech(
        internal_rate_hz: u32,
        control_block_samples: usize,
        posture: Articulation,
        settings: FixedVoiceSettings,
    ) -> Result<Self, &'static str> {
        Self::for_speech_with_body(
            internal_rate_hz,
            control_block_samples,
            posture,
            settings,
            BodyName::Male.into(),
        )
    }

    /// 発話用の自由舌先と接触補正を選択体型の声道へつなぐ。
    pub fn for_speech_with_body(
        internal_rate_hz: u32,
        control_block_samples: usize,
        posture: Articulation,
        settings: FixedVoiceSettings,
        body: BodyMix,
    ) -> Result<Self, &'static str> {
        let bank = ArticulatorBank::new(posture, true)?;
        Self::for_body(
            internal_rate_hz,
            control_block_samples,
            bank,
            0.05,
            true,
            settings,
            body,
        )
    }

    /// 次の制御更新で使う調音入力。
    pub fn control_inputs(
        &mut self,
    ) -> (
        &mut ArticulatorBank,
        &mut [BlendedTarget; ARTICULATOR_COUNT],
    ) {
        (&mut self.bank, &mut self.blend)
    }

    /// 中立姿勢から新しい声道を作り、手動目標と音源設定を渡す。
    pub fn switch_manual_body(&mut self, body: BodyMix) -> Result<(), &'static str> {
        if self.score.is_some() || self.turbulence.is_some() {
            return Err("手動発声の体型変更は調音スコアと同時に使用できません");
        }
        let mut bank = ArticulatorBank::new(Articulation::neutral(), self.bank.tip_free())?;
        for key in Articulator::ALL {
            bank.set_target(key, self.bank.state(key).target);
        }
        let source = FixedVoiceSettings {
            gate: self.voice.breath_control.performer_gate,
            f0_hz: 110.0,
            ..self.initial_source
        };
        let mut next = Self::for_tract(
            self.internal_rate_hz,
            self.voice.control_block_samples,
            bank,
            self.base_weight,
            self.project_contacts,
            source,
            (body, self.tract.targets().oral_cells_override),
        )?;
        next.set_base_pitch(body.default_f0_hz())?;
        *self = next;
        Ok(())
    }

    pub fn set_performer_gate(&mut self, goal: f64) -> Result<(), &'static str> {
        self.voice.set_performer_gate(goal)
    }

    /// 成人男性の打音に使う声門の揺らぎ、基準F0、準備姿勢の目標、乱流を設定する。
    pub fn configure_beatbox(
        &mut self,
        base_pitch_hz: f64,
        noise_scale: f64,
    ) -> Result<(), &'static str> {
        self.voice.glottis.use_beatbox_variation();
        self.set_base_pitch(base_pitch_hz)?;
        let ready = male_ready_targets();
        for axis in Articulator::ALL {
            if let Some(target) = ready.get(ControlKey::Artic(axis)) {
                self.bank.set_target(axis, target);
            }
        }
        self.enable_turbulence(noise_scale)
    }

    /// 現在のF0から滑らかに遷移する基準値を設定する。
    pub fn set_base_pitch(&mut self, f0_hz: f64) -> Result<(), &'static str> {
        if !self.voice.glottis.valid_pitch(f0_hz) {
            return Err("発話の基準F0が範囲外です");
        }
        self.voice.base_f0_hz = f0_hz;
        Ok(())
    }

    /// 声門の周期揺らぎや位相を保ったまま、低速のピッチドリフトの大きさを設定する。
    pub fn set_pitch_drift_cents(&mut self, cents: f64) -> Result<(), &'static str> {
        self.voice.glottis.set_pitch_drift_cents(cents)
    }

    /// 次の声門周期から適用する、周期倍率の無次元の揺らぎ係数を設定する。
    pub fn set_period_jitter(&mut self, amount: f64) -> Result<(), &'static str> {
        self.voice.glottis.set_period_jitter(amount)
    }

    /// 次の声門周期から適用する、振動面積の無次元の揺らぎ係数を設定する。
    pub fn set_amplitude_shimmer(&mut self, amount: f64) -> Result<(), &'static str> {
        self.voice.glottis.set_amplitude_shimmer(amount)
    }

    /// ビブラートなどの声門変調が掛かる前の、対数補間後のF0（Hz）。
    pub fn smoothed_pitch_hz(&self) -> f64 {
        self.voice.smoothed_f0_hz
    }

    /// 既存の時計上で次の制御フレームからスコアを評価する。
    pub fn set_score(&mut self, score: Vec<Gesture>) -> Result<(), &'static str> {
        for gesture in &score {
            gesture.validate()?;
        }
        self.score = Some(score);
        Ok(())
    }

    /// 次の制御フレームで既存のスコアに重ねる。速度保持を終えたジェスチャーは除く。
    pub fn append_score(&mut self, gestures: &mut Vec<Gesture>) -> Result<(), &'static str> {
        for gesture in gestures.iter() {
            gesture.validate()?;
        }
        let score = self.score.get_or_insert_with(Vec::new);
        score.retain(|gesture| gesture.speed_end() >= self.clock_seconds);
        score.append(gestures);
        Ok(())
    }

    /// 予約と進行中のスコアを消す。音源の状態は次の制御更新から減衰する。
    pub fn cancel_score(&mut self) {
        if let Some(score) = &mut self.score {
            score.clear();
        }
    }

    /// 次の調音制御更新が評価する音源の時刻（秒）。
    pub fn clock_seconds(&self) -> f64 {
        self.clock_seconds
    }

    /// 形状の更新ごとに乱流源を配置する。倍率0でも配置とフィルタの更新は進む。
    pub fn enable_turbulence(&mut self, scale: f64) -> Result<(), &'static str> {
        self.enable_turbulence_with_glottis_gain(scale, 1.0)
    }

    /// 声門の乱流源を配置したまま、そのゲインに掛ける倍率を指定する。
    pub fn enable_turbulence_with_glottis_gain(
        &mut self,
        scale: f64,
        glottis_gain_multiplier: f64,
    ) -> Result<(), &'static str> {
        self.enable_turbulence_with_source_gains(scale, glottis_gain_multiplier, 1.0)
    }

    /// 声門・狭窄の乱流源を配置したまま、各ゲインに掛ける倍率を指定する。
    pub fn enable_turbulence_with_source_gains(
        &mut self,
        scale: f64,
        glottis_gain_multiplier: f64,
        constriction_gain_multiplier: f64,
    ) -> Result<(), &'static str> {
        self.enable_turbulence_with_settings(TurbulenceSettings {
            scale,
            glottis_gain_multiplier,
            constriction_gain_multiplier,
            ..TurbulenceSettings::default()
        })
    }

    pub fn enable_turbulence_with_settings(
        &mut self,
        settings: TurbulenceSettings,
    ) -> Result<(), &'static str> {
        if !settings.glottis_gain_multiplier.is_finite() || settings.glottis_gain_multiplier < 0.0 {
            return Err("声門の乱流源の倍率は有限で0以上の値を指定してください");
        }
        if !settings.constriction_gain_multiplier.is_finite()
            || settings.constriction_gain_multiplier < 0.0
        {
            return Err("狭窄の乱流源の倍率は有限で0以上の値を指定してください");
        }
        if !settings.teeth_lowpass_floor_hz.is_finite() || settings.teeth_lowpass_floor_hz < 0.0 {
            return Err("歯の低域通過周波数の下限は有限で0 Hz以上の値を指定してください");
        }
        self.voice.airway.network.set_noise_scale(settings.scale)?;
        self.voice
            .airway
            .register_turbulence(self.tract.targets(), settings)?;
        self.turbulence = Some(settings);
        Ok(())
    }

    pub fn articulators(&self) -> &ArticulatorBank {
        &self.bank
    }

    /// 最後の調音更新で求めた下唇端の矢状面座標。
    pub fn lower_lip_edge_cm(&self) -> Point {
        self.tract.lower_lip_edge_cm()
    }

    /// 最後に確定した調音制御周期の測定線。音響セルへの再標本化前の量。
    pub fn tract_area_samples(&self) -> &[AreaSample] {
        self.tract.area_samples()
    }

    pub fn airway(&self) -> &HumanAirway {
        &self.voice.airway
    }

    pub fn step(&mut self) -> Result<VoiceSample, &'static str> {
        self.step_with_glottal_pressure(None)
    }

    /// 声帯モデルへ渡す圧差をこの内部サンプルだけ指定する。
    /// 気道の圧力と声門を通る流量は、それぞれの状態から計算する。
    pub fn step_with_glottal_pressure(
        &mut self,
        pressure_override: Option<f64>,
    ) -> Result<VoiceSample, &'static str> {
        if pressure_override.is_some_and(|pressure| !pressure.is_finite()) {
            return Err("声門モデルへ渡す圧差には有限の値を指定してください");
        }
        if self.voice.samples_until_control == 0 {
            #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
            let _allocation = allocation_scope(AllocationPhase::Control);
            #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
            crate::render_phase_probe::mark(crate::render_phase_probe::Phase::ControlStart);
            if let Some(score) = &self.score {
                let blend = blend_at(score, self.clock_seconds);
                self.voice.apply_score(&blend, self.control_seconds)?;
                self.blend.copy_from_slice(&blend[..ARTICULATOR_COUNT]);
            } else if self.voice.base_f0_hz != self.voice.smoothed_f0_hz {
                self.voice.update_pitch(
                    self.voice.base_f0_hz,
                    self.control_seconds,
                    0.06,
                    0.0,
                    0.0,
                )?;
            }
            self.clock_seconds += self.control_seconds;
            self.bank
                .step(self.control_seconds, &self.blend, self.base_weight)?;
            let targets = self
                .tract
                .apply(self.bank.posture(), self.control_seconds)?;
            if let Some(settings) = self.turbulence {
                self.voice.airway.register_turbulence(targets, settings)?;
            }
            if self.project_contacts
                && self.bank.enforce_tongue_contacts(
                    targets.tip_contact,
                    targets.body_contact,
                    targets.body_scale(),
                )
            {
                self.tract.reapply(self.bank.posture())?;
                if let Some(settings) = self.turbulence {
                    self.voice
                        .airway
                        .register_turbulence(self.tract.targets(), settings)?;
                }
            }
            self.voice
                .airway
                .begin_tract_block(self.tract.targets(), self.voice.control_block_samples)?;
            #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
            crate::render_phase_probe::mark(crate::render_phase_probe::Phase::ControlEnd);
        }
        self.voice.step_source(pressure_override, None)
    }
}

impl FixedVoice {
    /// CLIなどで更新後の圧力と流量を読み出す。
    #[inline]
    pub fn airway(&self) -> &HumanAirway {
        &self.airway
    }
}
