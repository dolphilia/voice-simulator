//! ネイティブの診断ビルドで呼び出し元の割り当てカウンターを読む。

use std::cell::Cell;

#[derive(Clone, Copy)]
pub(crate) enum Phase {
    Control,
    Apply,
    Reapply,
    Contour,
    ContactGrid,
    AreaProfile,
    Resample,
    CloneCells,
    Turbulence,
    BeginTractBlock,
    RoofCumulative,
    MeasurementGrid,
    ContactSamples,
}

const PHASE_COUNT: usize = Phase::ContactSamples as usize + 1;
pub const PHASE_NAMES: [&str; PHASE_COUNT] = [
    "control",
    "apply",
    "reapply",
    "contour",
    "contact_grid",
    "area_profile",
    "resample",
    "clone_cells",
    "turbulence",
    "begin_tract_block",
    "roof_cumulative",
    "measurement_grid",
    "contact_samples",
];

#[derive(Clone, Copy, serde::Serialize)]
pub struct Count {
    pub calls: usize,
    pub allocations: usize,
}

const EMPTY: [Count; PHASE_COUNT] = [Count {
    calls: 0,
    allocations: 0,
}; PHASE_COUNT];
type Counter = fn() -> usize;

thread_local! {
    static COUNTER: Cell<Option<Counter>> = const { Cell::new(None) };
    static COUNTS: Cell<[Count; PHASE_COUNT]> = const { Cell::new(EMPTY) };
}

/// 同じスレッドで計数する関数を診断の間だけ有効にする。
pub fn trace<T>(count: Counter, render: impl FnOnce() -> T) -> T {
    struct Reset;
    impl Drop for Reset {
        fn drop(&mut self) {
            COUNTER.set(None);
        }
    }
    assert!(COUNTER.get().is_none(), "割り当て計測は入れ子にできません");
    COUNTS.set(EMPTY);
    COUNTER.set(Some(count));
    let _reset = Reset;
    render()
}

/// 指定した描画量子までに加算された各段階の件数を返し、計数を戻す。
pub fn take_counts() -> [Count; PHASE_COUNT] {
    COUNTS.replace(EMPTY)
}

pub(crate) fn scope(phase: Phase) -> impl Drop {
    struct Scope(Phase, Option<(Counter, usize)>);
    impl Drop for Scope {
        fn drop(&mut self) {
            if let Some((read, start)) = self.1 {
                let allocations = read() - start;
                let mut counts = COUNTS.get();
                let row = &mut counts[self.0 as usize];
                row.calls += 1;
                row.allocations += allocations;
                COUNTS.set(counts);
            }
        }
    }
    Scope(phase, COUNTER.get().map(|read| (read, read())))
}
