//! 診断用WASMで、内部サンプルの番号と処理境界をホストへ送る。

use std::cell::Cell;

#[repr(u32)]
pub enum Phase {
    LoopStart,
    LoopEnd,
    ControlStart,
    ControlEnd,
    AirwayStart,
    AirwayEnd,
}

#[link(wasm_import_module = "chimera_probe")]
unsafe extern "C" {
    fn mark_phase(phase: u32, internal_offset: u32);
}

thread_local! {
    static INTERNAL_OFFSET: Cell<Option<u32>> = const { Cell::new(None) };
}

pub fn trace_render<T>(render: impl FnOnce() -> T) -> T {
    struct Reset;
    impl Drop for Reset {
        fn drop(&mut self) {
            INTERNAL_OFFSET.set(None);
        }
    }
    let _reset = Reset;
    INTERNAL_OFFSET.set(Some(0));
    render()
}

#[inline]
pub fn next_internal_sample() {
    if let Some(offset) = INTERNAL_OFFSET.get() {
        INTERNAL_OFFSET.set(Some(offset + 1));
    }
}

#[inline]
pub fn mark(phase: Phase) {
    if let Some(offset) = INTERNAL_OFFSET.get() {
        unsafe { mark_phase(phase as u32, offset) };
    }
}

#[inline]
pub fn mark_airway_sample(phase: Phase) {
    if let Some(offset @ (0 | 32)) = INTERNAL_OFFSET.get() {
        unsafe { mark_phase(phase as u32, offset) };
    }
}
