//! 英語歌詞と歌唱区間の固定版比較。上流の公開入口で計画を作る。

use chimera::{
    anatomy::human::BodyMix,
    phonetics::{
        Syllable,
        english::EnglishG2P,
        sing::{SongOptions, SungNote, plan_song},
        syllables::{English, read_lyrics, split_spelling, syllabify_segments},
    },
};
use serde_json::{Value, json};
use std::{
    error::Error,
    io::{self, Write},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let (case, dict, body) = match args.as_slice() {
        [case, dict] => (case, dict, BodyMix::MALE),
        [case, dict, body] if body == "female" => (case, dict, BodyMix::FEMALE),
        _ => return Err("ケース、辞書、必要に応じて女性の体型を指定してください".into()),
    };
    let mut fixed = EnglishG2P::new();
    fixed.load_dict(&std::fs::read_to_string(dict)?);
    let rules = EnglishG2P::new();
    let lexicon = |value: &Value| {
        if value["dictionary"].as_bool().unwrap_or(true) {
            &fixed
        } else {
            &rules
        }
    };
    let raw: Value = serde_json::from_slice(&std::fs::read(case)?)?;
    let input = &raw["song_plan"];
    let mut scores = Vec::new();
    for row in input["scores"].as_array().unwrap() {
        let syl: Vec<Syllable> = match row["lyrics"].as_str() {
            Some(text) => read_lyrics(text, &[&English(lexicon(row))]),
            None => serde_json::from_value(row["syllables"].clone())?,
        };
        let notes: Vec<_> = row["notes"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .map(|(i, n)| SungNote {
                midi: n["midi"].as_f64().unwrap(),
                beats: n["beats"].as_f64().unwrap(),
                syl: syl[i % syl.len()].clone(),
            })
            .collect();
        let plan = plan_song(
            &notes,
            &SongOptions {
                body,
                bpm: row["bpm"].as_f64().unwrap(),
                t0: row["start_seconds"].as_f64().unwrap(),
                vibrato: 0.,
            },
        );
        let pitch: Vec<_> = plan
            .gestures
            .iter()
            .filter(|g| g.label_str() == "pitch")
            .collect();
        scores.push(json!({"id":row["id"],"syllables":syl,"segments":plan.segments,"pitch":pitch,"end":plan.end}));
    }
    let lyrics:Vec<_> = input["lyric_cases"].as_array().unwrap().iter().map(|row|
        json!({"id":row["id"],"syllables":read_lyrics(row["text"].as_str().unwrap(),&[&English(lexicon(row))])})).collect();
    let spellings: Vec<_> = input["spelling_cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            let word = row["word"].as_str().unwrap();
            let n = row["n"].as_u64().unwrap();
            json!({"word":word,"n":n,"parts":split_spelling(word,n as usize)})
        })
        .collect();
    let words: Vec<_> = input["syllable_words"]
        .as_array()
        .unwrap()
        .iter()
        .map(|word| {
            let w = word.as_str().unwrap();
            json!({"w":w,"parts":syllabify_segments(&fixed.word(w,false))})
        })
        .collect();
    let value = json!({"scores":scores,"lyric_cases":lyrics,"spelling_cases":spellings,"syllable_words":words});
    let mut output = io::stdout().lock();
    serde_json::to_writer_pretty(&mut output, &value)?;
    writeln!(output)?;
    Ok(())
}
