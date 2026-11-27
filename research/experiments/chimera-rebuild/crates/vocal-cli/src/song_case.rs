//! 歌詞・音節とMIDI番号をケースで受け取り、計画のJSONを出す。

use crate::{english_case, network_case::Destination, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{self, BufWriter},
};
use vocal_core::phonetics::{
    english::English,
    mandarin,
    song::{self, Note, SongPlan},
    syllables::{self, Syllable},
};

#[derive(Deserialize)]
struct Case {
    song_plan: Input,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    #[serde(default)]
    scores: Vec<Score>,
    #[serde(default)]
    lyric_cases: Vec<LyricExample>,
    #[serde(default)]
    spelling_cases: Vec<Spelling>,
    #[serde(default)]
    syllable_words: Vec<String>,
    #[serde(default)]
    mandarin_words: Vec<String>,
}

#[derive(Deserialize)]
struct LyricExample {
    id: String,
    text: String,
    dictionary: Option<bool>,
}

#[derive(Deserialize)]
struct Spelling {
    word: String,
    n: usize,
}

#[derive(Deserialize)]
pub(crate) struct Score {
    pub(crate) id: String,
    lyrics: Option<String>,
    syllables: Option<Vec<Syllable>>,
    dictionary: Option<bool>,
    notes: Vec<Note>,
    bpm: f64,
    start_seconds: f64,
}

impl Score {
    pub(crate) fn plan(
        &self,
        dictionary: &English<'_>,
    ) -> Result<(Vec<Syllable>, SongPlan), Box<dyn Error>> {
        let syllables = match (&self.lyrics, &self.syllables) {
            (Some(text), None) => song::lyric_syllables(text, dictionary),
            (None, Some(syllables)) => syllables.clone(),
            _ => {
                return Err(
                    format!("{} の歌詞または音節を一方だけ指定してください", self.id).into(),
                );
            }
        };
        let plan = song::plan(&syllables, &self.notes, self.bpm, self.start_seconds)
            .map_err(|error| format!("{} の歌唱計画でエラー ({error})", self.id))?;
        Ok((syllables, plan))
    }

    pub(crate) fn uses_dictionary(&self) -> bool {
        self.dictionary.unwrap_or(true)
    }
}

pub(super) fn run(value: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let data = Case::deserialize(&value)?.song_plan;
    let fixed = english_case::dictionary()?;
    let rules = English::default();
    let dictionary = |flag: Option<bool>| if flag.unwrap_or(true) { fixed } else { &rules };
    let mut scores = Vec::with_capacity(data.scores.len());
    for score in data.scores {
        let (syl, plan) = score.plan(dictionary(score.dictionary))?;
        scores.push(json!({"id":score.id,"syllables":syl,"plan":plan}));
    }
    let lyric_cases: Vec<_> = data.lyric_cases.into_iter().map(|input| {
        json!({"id":input.id,"syllables":song::lyric_syllables(&input.text,dictionary(input.dictionary))})
    }).collect();
    let spelling_cases: Vec<_> = data.spelling_cases.into_iter().map(|input| {
        json!({"word":input.word,"n":input.n,"parts":syllables::split_spelling(&input.word,input.n)})
    }).collect();
    let syllable_words: Vec<_> = data.syllable_words.into_iter().map(|word| {
        json!({"w":word,"parts":syllables::syllabify(&fixed.pronounce(&word,false).segments)})
    }).collect();
    let mut value = json!({"scores":scores,"lyric_cases":lyric_cases,"spelling_cases":spelling_cases,"syllable_words":syllable_words});
    if !data.mandarin_words.is_empty() {
        let lexicon = mandarin::fixed_lexicon();
        value["mandarin_readings"] = json!(
            data.mandarin_words
                .iter()
                .map(|word| { (word, lexicon.read(word)) })
                .collect::<std::collections::BTreeMap<_, _>>()
        );
    }
    match destination {
        Destination::Inspect => write_json(io::stdout().lock(), &value),
        Destination::Trace(path) => write_json(BufWriter::new(File::create_new(path)?), &value),
        Destination::Pcm { .. } => {
            Err("歌唱の音節・拍ケースは inspect または render で確認してください".into())
        }
    }
}
