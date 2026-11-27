// 観測済みのF2を固定上流の参照集約へ渡す。

#[derive(serde::Deserialize)]
struct ReferenceProbeInput {
    term: String,
    ipa: String,
    training: BTreeMap<String, Vec<(String, usize, f64)>>,
    intervention_speakers: Option<Vec<String>>,
    held_recording: Vec<f64>,
    held_synth: Vec<f64>,
    replacements: BTreeMap<String, f64>,
}

fn reference_probe_token(ipa: &str, f2: f64) -> Tok {
    Tok {
        ipa: ipa.into(),
        stressed: true,
        t0: 0.0,
        secs: f64::NAN,
        next: Next::End,
        dur: f64::NAN,
        level: f64::NAN,
        burst: f64::NAN,
        centroid: f64::NAN,
        mel: [f64::NAN; N_MEL],
        voiced: f64::NAN,
        f1: f64::NAN,
        f2,
        bands: [f64::NAN; 5],
        h1h2: f64::NAN,
    }
}

fn reference_probe_profile(defs: &[TermDef], ipa: &str, frequencies: &[f64]) -> Values {
    let utterance = UttMeas { rate: f64::NAN, f0_range: f64::NAN };
    let tokens: Vec<_> = frequencies.iter().map(|&f| reference_probe_token(ipa, f)).collect();
    values(defs, &[(&utterance, &tokens)])
}

fn reference_probe_report(training: &BTreeMap<String, Values>, recording: &Values, synth: &Values, term: &str) -> Value {
    let r = reference(true, training);
    json!({
        "reference": r.terms[term],
        "held_recording": costs(recording, &r)[term],
        "held_synth": costs(synth, &r)[term],
        "training": training.iter().map(|(speaker,v)| (
            speaker.clone(), json!({"support": v.support[term], "log2_hz": v.terms[term]})
        )).collect::<BTreeMap<_,_>>(),
    })
}

pub fn research_tsp_f2_training_reference(input_path: &str) -> Result<(), String> {
    let input: ReferenceProbeInput =
        serde_json::from_reader(std::fs::File::open(input_path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    let defs: Vec<_> = term_defs().into_iter().filter(|d| d.name == input.term).collect();
    if defs.len() != 1 {
        return Err("F2の診断項目を1件に特定できません".into());
    }
    let group = defs[0].group;
    let profile = |frequencies: &[f64]| reference_probe_profile(&defs, &input.ipa, frequencies);
    let recording = profile(&input.held_recording);
    let synth = profile(&input.held_synth);
    let mut training: BTreeMap<_, _> = input.training.iter().map(|(speaker, rows)| (
        speaker.clone(), profile(&rows.iter().map(|row| row.2).collect::<Vec<_>>())
    )).collect();
    let baseline = reference_probe_report(&training, &recording, &synth, &input.term);
    let mut interventions = Vec::new();
    for (speaker, rows) in &input.training {
        if input.intervention_speakers.as_ref().is_some_and(|names| !names.contains(speaker)) {
            continue;
        }
        let unchanged = training[speaker].clone();
        let mut frequencies: Vec<_> = rows.iter().map(|row| row.2).collect();
        for (index, (uid, slot, original)) in rows.iter().enumerate() {
            let mut scenarios = BTreeMap::new();
            for (name, replacement) in &input.replacements {
                frequencies[index] = *replacement;
                training.insert(speaker.clone(), profile(&frequencies));
                scenarios.insert(name, reference_probe_report(&training, &recording, &synth, &input.term));
            }
            frequencies[index] = *original;
            interventions.push(json!({
                "speaker": speaker, "utterance": uid, "slot": slot, "original_hz": original,
                "scenarios": scenarios,
            }));
        }
        training.insert(speaker.clone(), unchanged);
    }
    let after_restore = reference_probe_report(&training, &recording, &synth, &input.term);
    println!("{}", json!({
        "baseline": baseline, "after_restore": after_restore, "interventions": interventions,
        "held_support": {"recording": recording.support[&input.term], "synth": synth.support[&input.term]},
        "group": group, "scored": GROUPS.contains(&group),
        "minimum_tokens": MIN_TOKENS, "minimum_training_speakers": MIN_SPEAKERS,
        "spread_floor": spread_floor(&input.term),
    }));
    Ok(())
}

#[derive(serde::Deserialize)]
struct PooledReferenceInput {
    term: String,
    ipa: String,
    training: BTreeMap<String, Vec<f64>>,
    cohorts: BTreeMap<String, Vec<String>>,
    speaker: String,
    index: usize,
    replacement: f64,
    held_recording: Vec<f64>,
    held_synth: Vec<f64>,
}

fn pooled_reference_report(training: &BTreeMap<String, Values>, recording: &Values, synth: &Values, term: &str) -> Value {
    let sexes = [reference(true, training).terms[term], reference(false, training).terms[term]];
    let deviations: BTreeMap<_, _> = training.iter().filter_map(|(speaker, v)| {
        let centre = sexes[usize::from(!speaker.starts_with('F'))].0;
        let residual = v.terms[term] - centre;
        residual.is_finite().then_some((speaker.clone(), residual))
    }).collect();
    let pooled_mad = mad_sd(&deviations.values().copied().collect::<Vec<_>>());
    let mut report = reference_probe_report(training, recording, synth, term);
    report["male_reference"] = json!(sexes[1]);
    report["residuals"] = json!(deviations);
    report["pooled_mad"] = json!(pooled_mad);
    report
}

pub fn research_tsp_f2_reference_pooled_sexes(input_path: &str) -> Result<(), String> {
    let input: PooledReferenceInput =
        serde_json::from_reader(std::fs::File::open(input_path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    let defs: Vec<_> = term_defs().into_iter().filter(|d| d.name == input.term).collect();
    if defs.len() != 1 {
        return Err("F2の診断項目を1件に特定できません".into());
    }
    let profile = |frequencies: &[f64]| reference_probe_profile(&defs, &input.ipa, frequencies);
    let recording = profile(&input.held_recording);
    let synth = profile(&input.held_synth);
    let rows: BTreeMap<_, _> = input.training.iter().map(|(speaker, samples)| (speaker.clone(), profile(samples))).collect();
    let mut changed = input.training.get(&input.speaker).ok_or("介入話者がありません")?.clone();
    *changed.get_mut(input.index).ok_or("介入する測定値がありません")? = input.replacement;
    let changed = profile(&changed);
    let mut result = BTreeMap::new();
    for (name, speakers) in &input.cohorts {
        let mut training = speakers.iter().map(|speaker| {
            rows.get(speaker).map(|v| (speaker.clone(), v.clone()))
                .ok_or_else(|| format!("学習話者 {speaker} の測定値がありません"))
        }).collect::<Result<BTreeMap<_, _>, _>>()?;
        let baseline = pooled_reference_report(&training, &recording, &synth, &input.term);
        if training.insert(input.speaker.clone(), changed.clone()).is_none() {
            return Err("介入話者を含まないコホートがあります".into());
        }
        let intervened = pooled_reference_report(&training, &recording, &synth, &input.term);
        result.insert(name, json!({"baseline": baseline, "intervened": intervened}));
    }
    println!("{}", json!({
        "cohorts": result, "group": defs[0].group, "scored": GROUPS.contains(&defs[0].group),
        "minimum_tokens": MIN_TOKENS, "minimum_training_speakers": MIN_SPEAKERS,
        "spread_floor": spread_floor(&input.term),
    }));
    Ok(())
}

#[derive(serde::Deserialize)]
struct F2OverSetsInput {
    term: String,
    ipa: String,
    held: BTreeMap<String, Vec<f64>>,
    short_count: usize,
    references: BTreeMap<String, BTreeMap<String, [f64; 2]>>,
}

pub fn research_tsp_f2_held_synth_over_sets(input_path: &str) -> Result<(), String> {
    let input: F2OverSetsInput =
        serde_json::from_reader(std::fs::File::open(input_path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    let defs: Vec<_> = term_defs().into_iter().filter(|d| d.name == input.term).collect();
    let Some(definition) = defs.first() else { return Err("F2の診断項目がありません".into()) };
    let fk = input.held.get("FK").ok_or("FKのF2がありません")?;
    let fl = input.held.get("FL").ok_or("FLのF2がありません")?;
    let fk_short = fk.get(..input.short_count).ok_or("FKの不足対照を切り出せません")?;
    let fl_short = fl.get(..input.short_count).ok_or("FLの不足対照を切り出せません")?;
    let profile = |rows: &[f64]| reference_probe_profile(&defs, &input.ipa, rows);
    let held = BTreeMap::from([("FK", profile(fk)), ("FL", profile(fl))]);
    let variants = BTreeMap::from([
        ("over_sets", over_sets(&[held["FK"].clone(), held["FL"].clone()])),
        ("token_pool", profile(&fk.iter().chain(fl.iter()).copied().collect::<Vec<_>>())),
        ("fl_short", over_sets(&[held["FK"].clone(), profile(fl_short)])),
        ("both_short", over_sets(&[profile(fk_short), profile(fl_short)])),
    ]);
    let properties = |value: &Values| json!({
        "log2_hz": value.terms[&input.term], "support": value.support[&input.term],
    });
    let mut cases = BTreeMap::new();
    for (case, cohorts) in &input.references {
        let mut results = BTreeMap::new();
        for (name, &[centre, width]) in cohorts {
            let r = Reference {
                terms: BTreeMap::from([(input.term.clone(), (centre, width, f64::NAN))]),
                ceps: BTreeMap::new(),
            };
            let scores: BTreeMap<_, _> = variants.iter().map(|(key, profile)| {
                let terms = costs(profile, &r);
                let (_, diagnostics) = fold(&terms);
                (*key, json!({"cost": terms[&input.term].1, "diagnostic_cost": diagnostics.get(definition.group)}))
            }).collect();
            results.insert(name, scores);
        }
        cases.insert(case, results);
    }
    println!("{}", json!({
        "held": held.iter().map(|(key, v)| (*key, properties(v))).collect::<BTreeMap<_, _>>(),
        "variants": variants.iter().map(|(key, v)| (*key, properties(v))).collect::<BTreeMap<_, _>>(),
        "minimum_sets": held.len().div_ceil(2).max(1), "minimum_tokens": MIN_TOKENS,
        "group": definition.group, "scored": GROUPS.contains(&definition.group), "cases": cases,
    }));
    Ok(())
}
