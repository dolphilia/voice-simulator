// 固定上流の比較モジュール末尾に一時的に読み込み、非公開の観測点を記録する。
pub fn research_formants(path: &str) -> Result<(), String> {
    type Source = (String, Vec<(f64, f64, String)>, Vec<usize>);
    type Request = (Vec<f64>, BTreeMap<String, (bool, BTreeMap<String, Source>)>);
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let (centers, utterances): Request = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let mut output = BTreeMap::new();
    for (id, (female, sources)) in utterances {
        let phones: BTreeMap<_, Vec<_>> = sources
            .iter()
            .map(|(name, (_, intervals, _))| {
                let phones = intervals.iter().map(|(t0, t1, label)| {
                    let segment = arpabet_to_segments(label).pop();
                    let (ipa, stress) = segment.map(|s| (s.ipa, s.stress.unwrap_or(0)))
                        .unwrap_or_else(|| (label.clone(), 0));
                    Phone { ipa, stress, t0: *t0, t1: *t1 }
                }).collect();
                (name.as_str(), phones)
            }).collect();
        let mut matching = BTreeMap::new();
        if let Some(recording) = phones.get("recording") {
            for voice in ["upstream", "candidate"] {
                let synth = &phones[voice];
                let pairs = match_phones(recording, synth);
                let stressed: Vec<_> = pairs.iter().filter(|(_, j)| {
                    let p = &synth[*j];
                    p.stress == 1 && MONOPHTHONGS.contains(&p.ipa.as_str())
                }).map(|(i, j)| (*i, *j, synth[*j].ipa.as_str())).collect();
                matching.insert(voice, json!({"pairs": pairs, "stressed": stressed}));
            }
        }
        let mut observed = BTreeMap::new();
        for (name, (wave, _, indexes)) in &sources {
            let (x, fs) = read_wav(wave)?;
            if fs != crate::FS {
                return Err(format!("{wave}: 48 kHzの入力が必要です"));
            }
            let sig = Sig::new(&x, fs, female);
            let rows: Vec<_> = indexes.iter().map(|&i| {
                let phone = &phones[name.as_str()][i];
                let baseline = sig.formants(phone, female);
                let windows: Vec<_> = centers.iter().map(|&q| {
                    research_formant_window(&sig, phone, female, q)
                }).collect();
                json!({"index": i, "baseline_hz": baseline, "windows": windows})
            }).collect();
            observed.insert(name, rows);
        }
        output.insert(id, json!({"matching": matching, "sources": observed}));
    }
    println!("{}", serde_json::to_string(&output).map_err(|e| e.to_string())?);
    Ok(())
}

fn research_formant_window(sig: &Sig<'_>, phone: &Phone, female: bool, q: f64) -> Value {
    // 任意の中心を調べる。基準中心の中央値は Sig::formants の直接呼び出しと照合する。
    let fs = sig.fs / DEC as f64;
    let len = (0.025 * fs) as usize;
    let t = phone.t0 + q * (phone.t1 - phone.t0);
    let start = (t * fs) as isize - (len / 2) as isize;
    if start < 0 || start as usize + len > sig.lo.len() {
        return json!({"start_sample": start, "poles": [], "f1_f2_hz": null, "reason": "outside_wave"});
    }
    let frame = &sig.lo[start as usize..start as usize + len];
    let opts = FormantOpts {
        order: Some(if female { 12 } else { 14 }),
        max_bw: Some(600.0),
        min_freq: Some(150.0),
        ..Default::default()
    };
    let poles = estimate_formants(frame, fs, opts);
    let f1 = poles.iter().find(|f| f.freq < 1300.0 && f.bw < 500.0);
    let f2 = f1.and_then(|one| poles.iter().find(|f| f.freq > one.freq + 200.0 && f.freq < 3500.0));
    let pair = f1.zip(f2).map(|(one, two)| [one.freq, two.freq]);
    let reason = if f1.is_none() { Some("no_f1") } else if f2.is_none() { Some("no_f2") } else { None };
    let poles: Vec<_> = poles.iter().map(|p| [p.freq, p.bw]).collect();
    json!({"start_sample": start, "poles": poles, "f1_f2_hz": pair, "reason": reason})
}
