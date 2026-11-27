//! 発声の物理モデル。音声デバイスとファイル入出力は呼び出し側が扱う。

pub mod airway;
pub mod anatomy;
pub mod articulators;
pub mod axial;
pub mod breath;
mod creature_midi;
pub mod glottis;
pub mod lip_reed;
pub mod output;
pub mod phonetics;
mod random;
#[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
pub mod render_allocation_probe;
#[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
pub mod render_phase_probe;
pub mod score;
pub mod seal_breath;
pub mod seal_voice;
pub mod songbird_voice;
pub mod syrinx;
pub mod voice;
