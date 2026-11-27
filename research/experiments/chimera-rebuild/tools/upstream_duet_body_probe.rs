//! 固定上流の混合体型で、通常の歌唱描画と乱流の採取を同じ出力時計で実行する。

use chimera::{
    anatomy::human::BodyMix,
    phonetics::{
        english::EnglishG2P,
        sing::{SongOptions, SungNote, midi_to_hz, plan_song},
        syllables::{English, read_lyrics},
    },
    voice::human_voice::{HumanVoice, SourcePatch, VoiceTelemetry},
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [path, dictionary, audio_path] = args.as_slice() else {
        return Err("入力、発音辞書、PCM出力を指定してください".into());
    };
    let input: Value = serde_json::from_str(&fs::read_to_string(path)?)?;
    let body: BodyMix = serde_json::from_value(input["body"].clone())?;
    let score = &input["score"];
    let mut dict = EnglishG2P::new();
    dict.load_dict(&fs::read_to_string(dictionary)?);
    let syllables = read_lyrics(
        score["lyrics"].as_str().ok_or("歌詞がありません")?,
        &[&English(&dict)],
    );
    let notes: Vec<[f64; 2]> = serde_json::from_value(score["notes"].clone())?;
    if notes.is_empty() || notes.len() != syllables.len() {
        return Err("この観測では音節と有音の音符が一対一で必要です".into());
    }
    let initial_f0 = midi_to_hz(notes[0][0]);
    let notes: Vec<_> = notes
        .into_iter()
        .zip(syllables)
        .map(|([midi, beats], syl)| SungNote { midi, beats, syl })
        .collect();
    let opts = SongOptions {
        body,
        bpm: score["bpm"].as_f64().ok_or("テンポがありません")?,
        t0: score["t0"].as_f64().ok_or("最初の拍がありません")?,
        vibrato: score["vibrato"].as_f64().ok_or("ビブラートがありません")?,
    };
    let rate = input["sample_rate_hz"]
        .as_f64()
        .ok_or("出力レートがありません")?;
    let plan = plan_song(&notes, &opts);
    let mut voice = HumanVoice::new(rate, body.body(), 2);
    // 固定上流の render::notes と同じ音源設定と描画順序を使う。
    voice.set_source(&SourcePatch {
        f0: Some(initial_f0),
        voiced: Some(true),
        pressure: Some(9.0),
        tension: Some(0.55),
        ..Default::default()
    });
    voice.schedule(&plan.gestures);
    let airway = &voice.airway;
    let layout = json!({
        "pharynx": {"base": airway.pharynx.branch_base, "cells": airway.pharynx.n},
        "oral": {"base": airway.oral.branch_base, "cells": airway.oral.n},
        "glottis_port": airway.glottis_port, "sample_rate_hz": rate as u32,
    });
    let hop = input["hop_samples"]
        .as_u64()
        .ok_or("観測間隔がありません")? as usize;
    let mut pcm = vec![0.0f32; (rate * (plan.end + 0.4)).round() as usize];
    let mut rows = Vec::with_capacity(pcm.len() / hop + 1);
    let mut t = VoiceTelemetry::default();
    let mut snapshot = |voice: &mut HumanVoice, sample: usize| {
        voice.telemetry(&mut t);
        rows.push(
            json!({"sample": sample, "phLen": t.ph_len as f32, "orLen": t.or_len as f32,
                         "noiseLevel": t.noise_level as f32, "noiseNode": t.noise_node}),
        );
    };
    snapshot(&mut voice, 0);
    for (index, chunk) in pcm.chunks_mut(hop).enumerate() {
        for block in chunk.chunks_mut(128) {
            voice.render(block);
        }
        if chunk.len() == hop {
            snapshot(&mut voice, (index + 1) * hop);
        }
    }
    let mut out = BufWriter::new(File::create_new(audio_path)?);
    for value in &pcm {
        out.write_all(&value.to_le_bytes())?;
    }
    out.flush()?;
    serde_json::to_writer(
        std::io::stdout().lock(),
        &json!({"frames": pcm.len(), "layout": layout, "rows": rows}),
    )?;
    Ok(())
}
