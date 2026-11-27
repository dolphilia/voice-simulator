//! ネイティブテストで、計画ABIの重ならない工程を計数する。

use std::cell::Cell;

use crate::tests::ALLOCATIONS;

#[derive(Clone, Copy)]
pub(super) enum Phase {
    DictionaryIndex,
    SpeechPlan,
    SpeechValue,
    ScoreWords,
    ReportValue,
    ReportJson,
}

const PHASE_COUNT: usize = Phase::ReportJson as usize + 1;
pub(crate) const PHASE_NAMES: [&str; PHASE_COUNT] = [
    "dictionary_index",
    "speech_plan",
    "speech_value",
    "score_words",
    "report_value",
    "report_json",
];

thread_local! {
    static COUNTS: Cell<Option<[usize; PHASE_COUNT]>> = const { Cell::new(None) };
}

pub(crate) fn measure<T>(operation: impl FnOnce() -> T) -> (T, [usize; PHASE_COUNT]) {
    struct Reset;
    impl Drop for Reset {
        fn drop(&mut self) {
            COUNTS.set(None);
        }
    }
    assert!(COUNTS.get().is_none(), "計画の計数は入れ子にできません");
    COUNTS.set(Some([0; PHASE_COUNT]));
    let _reset = Reset;
    let result = operation();
    (result, COUNTS.get().unwrap())
}

pub(super) fn scope(phase: Phase) -> impl Drop {
    struct Scope(Phase, Option<usize>);
    impl Drop for Scope {
        fn drop(&mut self) {
            if let Some(before) = self.1 {
                let mut counts = COUNTS.get().unwrap();
                counts[self.0 as usize] += ALLOCATIONS.get() - before;
                COUNTS.set(Some(counts));
            }
        }
    }
    Scope(phase, COUNTS.get().map(|_| ALLOCATIONS.get()))
}
