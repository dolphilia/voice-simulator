//! 固定版辞書の読みを声調番号付きで採取する。

use chimera::phonetics::mandarin::MandarinLexicon;
use std::{collections::BTreeMap, error::Error, io};

fn main() -> Result<(), Box<dyn Error>> {
    let path = std::env::args().nth(1).ok_or("漢字列を含むケースを指定してください")?;
    let input: serde_json::Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let words: Vec<String> = serde_json::from_value(input["song_plan"]["mandarin_words"].clone())?;
    let data = std::process::Command::new("gzip")
        .args(["-dc", "public/data/mandarin.txt.gz"])
        .output()?;
    if !data.status.success() {
        return Err("固定版の中国語辞書を展開できません".into());
    }
    let mut lexicon = MandarinLexicon::new();
    lexicon.load(std::str::from_utf8(&data.stdout)?);
    let readings: BTreeMap<_, _> = words.iter().map(|word| (word, lexicon.read(word))).collect();
    serde_json::to_writer_pretty(io::stdout().lock(), &readings)?;
    Ok(())
}
