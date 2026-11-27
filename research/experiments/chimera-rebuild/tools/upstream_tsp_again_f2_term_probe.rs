// 固定上流の比較モジュールへ一時的に読み込み、F2を差し替える位置を観測する。
#[derive(serde::Deserialize)]
struct TermProbeInput {
    #[serde(flatten)]
    corpus: TermProbeCorpus,
    target_id: String,
    target_speaker: String,
    target_interval: [f64; 2],
    replacements_hz: [f64; 2],
    ipa: String,
    term: String,
}

#[derive(serde::Deserialize)]
struct TermProbeCorpus {
    recordings: Vec<String>,
    dataset_dir: String,
    synth_dir: String,
    female: Option<bool>,
    held: Option<bool>,
    candidate_dir: Option<String>,
    pcm_tolerance: Option<f64>,
}

fn term_probe_value(v: &Values, r: &Reference, term: &str) -> Value {
    let c = costs(v, r);
    let (raw_score, groups) = fold(&c);
    let (log2_hz, term_cost) = c[term];
    json!({
        "support": v.support[term], "log2_hz": log2_hz, "cost": term_cost,
        "score": raw_score, "groups": groups,
    })
}

fn term_probe_pairs(input: &TermProbeCorpus) -> Result<(Vec<Pair>, BTreeMap<String, Value>, String, BTreeMap<String, Value>), String> {
    let all = load_utts()?;
    let utts: Vec<_> = all.iter().filter(|utt| input.recordings.contains(&utt.id)).collect();
    if utts.len() != input.recordings.len() {
        return Err("登録した収録が上流の注釈に揃いません".into());
    }
    let mut said = say_all(&utts, 4)?;
    let mut render_comparison = BTreeMap::new();
    if let Some(root) = &input.candidate_dir {
        let tolerance = input.pcm_tolerance.ok_or("PCMの許容差がありません")?;
        for utt in &utts {
            let source = said.get_mut(&(utt.sentence().to_string(), utt.female()))
                .ok_or_else(|| format!("{} の固定合成がありません", utt.id))?;
            let (wave, rate) = read_wav(&format!("{root}/{}.wav", utt.id))?;
            if rate != crate::FS || wave.is_empty() || wave.iter().any(|x| !x.is_finite()) {
                return Err(format!("{} の試験用PCMの形式が一致しません", utt.id));
            }
            let count = source.x.len().min(wave.len());
            let mut first_difference = None;
            let mut first_above = None;
            let mut maximum = 0.0_f64;
            for (index, (&a, &b)) in source.x.iter().zip(&wave).enumerate() {
                let delta = (a - b).abs();
                if a != b && first_difference.is_none() {
                    first_difference = Some(index);
                }
                if delta > tolerance && first_above.is_none() {
                    first_above = Some(index);
                }
                maximum = maximum.max(delta);
            }
            let plan = source.phones.iter().map(|p| json!([p.ipa, p.stress, p.t0, p.t1])).collect::<Vec<_>>();
            render_comparison.insert(utt.id.clone(), json!({
                "upstream_plan": plan, "upstream_frames": source.x.len(), "candidate_frames": wave.len(),
                "common_frames": count, "first_difference": first_difference,
                "first_above_tolerance": first_above, "maximum_absolute_difference": maximum,
            }));
            source.x = wave;
        }
    }
    let texts = utts.iter().map(|utt| (utt.sentence().to_string(), utt.text.clone())).collect();
    let aligned = align_synth(&g2p()?, &said, &texts, &input.synth_dir, 1)?;
    let aligner = aligner_id(&input.synth_dir)?;
    let mut pairs = Vec::with_capacity(utts.len());
    let mut matched = BTreeMap::new();
    for utt in utts {
        let key = (utt.sentence().to_string(), utt.female());
        let phones = aligned.get(&key).ok_or_else(|| format!("{} の合成整列がありません", utt.id))?;
        let pair = measure_pair(&input.dataset_dir, utt, &said[&key], phones)?;
        let correspondence = match_phones(&utt.phones, phones);
        let mut tokens = Vec::new();
        for (slot, (&(i, j), (human, synth))) in correspondence.iter()
            .zip(pair.human.1.iter().zip(&pair.synth.1)).enumerate() {
            let phone = &utt.phones[i];
            tokens.push(json!({
                "slot": slot, "recording_index": i, "synth_index": j, "ipa": human.ipa,
                "stressed": human.stressed,
                "recording_interval": [phone.t0,phone.t1], "synth_interval": [phones[j].t0,phones[j].t1],
                "recording_f2_hz": human.f2, "synth_f2_hz": synth.f2,
            }));
        }
        matched.insert(pair.id.clone(), json!({"speaker": pair.speaker, "tokens": tokens}));
        pairs.push(pair);
    }
    Ok((pairs, matched, aligner, render_comparison))
}

pub fn research_tsp_f2_collect(input_path: &str) -> Result<(), String> {
    let input: TermProbeCorpus = serde_json::from_reader(std::fs::File::open(input_path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let (pairs, matched, aligner, renders) = term_probe_pairs(&input)?;
    if pairs.iter().any(|pair| pair.female != input.female.unwrap_or(true)
        || held_out(&pair.speaker) != input.held.unwrap_or(false)) {
        return Err("登録した性別か学習・確認の区分に合わない録音があります".into());
    }
    let mut result = json!({"correspondence": matched, "aligner": aligner});
    if input.candidate_dir.is_some() {
        result["render_comparison"] = json!(renders);
    }
    println!("{result}");
    Ok(())
}

pub fn research_tsp_again_f2_term(input_path: &str) -> Result<(), String> {
    let input: TermProbeInput = serde_json::from_reader(std::fs::File::open(input_path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let (mut pairs, matched, aligner, _) = term_probe_pairs(&input.corpus)?;
    let missing = "差し替える母音が対応音素にありません";
    let pair_index = pairs.iter().position(|pair| pair.id == input.target_id).ok_or(missing)?;
    let slots = matched[&input.target_id]["tokens"].as_array().ok_or(missing)?;
    let mut selected = slots.iter().enumerate().filter(|(_, row)| {
        row["ipa"] == input.ipa && row["stressed"] == true
            && input.target_interval.iter().enumerate().all(|(i, &expected)| {
                row["recording_interval"][i].as_f64().is_some_and(|t| (t - expected).abs() <= 1e-6)
            })
    });
    let (token_index, _) = selected.next().ok_or(missing)?;
    if selected.next().is_some() {
        return Err("差し替える母音が2件以上あります".into());
    }
    let baseline = pairs[pair_index].human.1[token_index].f2;
    let defs = term_defs();
    let mut profiles = BTreeMap::new();
    for pair in &pairs {
        profiles.entry(pair.speaker.clone()).or_insert_with(Vec::new)
            .push((&pair.human.0, pair.human.1.as_slice()));
    }
    let train: BTreeMap<_, _> = profiles.iter().filter(|(speaker, _)| !held_out(speaker))
        .map(|(speaker, tokens)| (speaker.clone(), values(&defs, tokens))).collect();
    let reference_female = reference(true, &train);
    let four_train: BTreeMap<_, _> = train.iter().take(MIN_SPEAKERS - 1)
        .map(|(speaker, v)| (speaker.clone(), v.clone())).collect();
    let four_reference = reference(true, &four_train);
    let held = profiles.get(&input.target_speaker).ok_or("確認用話者の録音がありません")?;
    let target_tokens: Vec<_> = held.iter().flat_map(|(_, tokens)| tokens.iter())
        .filter(|t| t.ipa == input.ipa && t.stressed && t.f2.is_finite()).take(MIN_TOKENS).cloned().collect();
    let control_utterance = &pairs[pair_index].human.0;
    let mut support_controls = BTreeMap::new();
    for count in [MIN_TOKENS - 1, MIN_TOKENS] {
        let keep = &target_tokens[..count.min(target_tokens.len())];
        support_controls.insert(count.to_string(), term_probe_value(
            &values(&defs, &[(control_utterance, keep)]), &reference_female, &input.term,
        ));
    }
    let prefix: Vec<_> = pairs.iter().filter(|pair| pair.speaker == input.target_speaker).take(2)
        .map(|pair| (&pair.human.0, pair.human.1.as_slice())).collect();
    let prefix_value = term_probe_value(&values(&defs, &prefix), &reference_female, &input.term);
    let mut conditions = BTreeMap::new();
    for (label, frequency) in [
        ("default", baseline), ("before", input.replacements_hz[0]),
        ("after", input.replacements_hz[1]), ("missing", f64::NAN)
    ] {
        pairs[pair_index].human.1[token_index].f2 = frequency;
        let rows: Vec<_> = pairs.iter().filter(|p| p.speaker == input.target_speaker)
            .map(|p| (&p.human.0, p.human.1.as_slice())).collect();
        let value = values(&defs, &rows);
        let grade = score(&pairs, &aligner).json;
        conditions.insert(label, json!({
            "input_f2_hz": frequency, "human_term": term_probe_value(&value,&reference_female,&input.term),
            "held_human_score_report": grade["human"]["held"][&input.target_speaker],
            "held_synth_report": grade["held"]["female"],
            "four_training_speakers": term_probe_value(&value,&four_reference,&input.term),
        }));
    }
    let references: BTreeMap<_, _> = train.iter().map(|(speaker, v)| (
        speaker, json!({"support": v.support[&input.term], "log2_hz": v.terms[&input.term]})
    )).collect();
    println!("{}", json!({
        "correspondence": matched, "target_slot": token_index, "training": references,
        "reference": reference_female.terms[&input.term], "four_speaker_reference": four_reference.terms[&input.term],
        "conditions": conditions, "support_controls": support_controls, "first_two_recordings": prefix_value,
        "minimum_tokens": MIN_TOKENS, "minimum_training_speakers": MIN_SPEAKERS, "aligner": aligner,
    }));
    Ok(())
}
