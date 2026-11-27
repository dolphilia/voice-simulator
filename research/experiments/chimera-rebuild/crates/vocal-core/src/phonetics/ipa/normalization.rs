//! IPA用の限定された正準化。表は固定CHIMERA由来（MIT、LICENSE-CHIMERA）。

use super::SourceSpan;
use serde::Deserialize;
use std::collections::HashMap;
use std::sync::LazyLock;

#[derive(Clone, Copy)]
pub(super) struct Unit {
    pub letter: char,
    pub span: SourceSpan,
}

#[derive(Deserialize)]
struct TableData {
    ccc: Vec<(u32, u32, u8)>,
    decomp: Vec<(u32, Vec<u32>)>,
    comp: Vec<(u32, u32, u32)>,
}

struct NormalizationTable {
    classes: Vec<(u32, u32, u8)>,
    decompositions: HashMap<char, Vec<char>>,
    compositions: HashMap<(char, char), char>,
}

static NFC: LazyLock<NormalizationTable> = LazyLock::new(|| {
    let data: TableData =
        serde_json::from_str(include_str!("nfc.generated.json")).expect("固定のIPA正準化表");
    let letter = |value| char::from_u32(value).expect("正準化表のUnicodeスカラー値");
    NormalizationTable {
        classes: data.ccc,
        decompositions: data
            .decomp
            .into_iter()
            .map(|(key, entries)| (letter(key), entries.into_iter().map(letter).collect()))
            .collect(),
        compositions: data
            .comp
            .into_iter()
            .map(|(base, mark, result)| ((letter(base), letter(mark)), letter(result)))
            .collect(),
    }
});

impl NormalizationTable {
    fn rank(&self, letter: char) -> u8 {
        let code = u32::from(letter);
        let index = self.classes.partition_point(|&(_, last, _)| last < code);
        self.classes
            .get(index)
            .filter(|&&(first, _, _)| first <= code)
            .map_or(0, |&(_, _, rank)| rank)
    }
}

pub(super) fn normalize(text: &str, start_byte: usize) -> Vec<Unit> {
    let table = &*NFC;
    let mut units = Vec::with_capacity(text.len());
    for (index, letter) in text.char_indices() {
        let start = start_byte + index;
        let span = SourceSpan {
            start_byte: start,
            end_byte: start + letter.len_utf8(),
        };
        let decomposition = table
            .decompositions
            .get(&letter)
            .map_or_else(|| std::slice::from_ref(&letter), Vec::as_slice);
        units.extend(decomposition.iter().map(|&letter| Unit { letter, span }));
    }

    // 基底文字を区切りとして結合文字を安定ソートする。先頭の結合文字列も並べる。
    let mut start = 0;
    while start < units.len() {
        if table.rank(units[start].letter) == 0 {
            start += 1;
            continue;
        }
        let end = units[start..]
            .iter()
            .position(|unit| table.rank(unit.letter) == 0)
            .map_or(units.len(), |offset| start + offset);
        units[start..end].sort_by_key(|unit| table.rank(unit.letter));
        start = end;
    }

    // 前の未合成記号の順位が現在の文字を妨げる場合は、そのまま出力する。
    let mut result: Vec<Unit> = Vec::with_capacity(units.len());
    let mut base: Option<usize> = None;
    let mut blocked_by = 0;
    for unit in units {
        let rank = table.rank(unit.letter);
        if let Some(index) = base
            && (blocked_by == 0 || blocked_by < rank)
            && let Some(&combined) = table.compositions.get(&(result[index].letter, unit.letter))
        {
            let original = &mut result[index];
            original.letter = combined;
            original.span = original.span.join(unit.span);
            continue;
        }
        if rank == 0 {
            base = Some(result.len());
        }
        blocked_by = rank;
        result.push(unit);
    }
    result
}

pub(super) fn replace(units: &mut Vec<Unit>, from: &str, to: &str) {
    let count = from.chars().count();
    let mut i = 0;
    while let Some(remaining) = units.get(i..i + count) {
        if remaining.iter().map(|unit| unit.letter).eq(from.chars()) {
            let span = remaining
                .iter()
                .map(|unit| unit.span)
                .reduce(SourceSpan::join)
                .expect("変換前の表記は空ではない");
            units.splice(i..i + count, to.chars().map(|letter| Unit { letter, span }));
            i += to.chars().count();
        } else {
            i += 1;
        }
    }
}
