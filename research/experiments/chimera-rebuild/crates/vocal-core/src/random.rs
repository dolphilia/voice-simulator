//! 乱数列を上流と照合するためのMulberry32。

// Copyright (c) 2026 Jameson Hodge (MIT), ../../../LICENSE-CHIMERA を参照。
pub(crate) struct Mulberry32(u32);

impl Mulberry32 {
    pub(crate) fn new(seed: u32) -> Self {
        Self(seed.max(1))
    }

    fn uniform(&mut self) -> f64 {
        self.0 = self.0.wrapping_add(0x6d2b_79f5);
        let mixed = (self.0 ^ (self.0 >> 15)).wrapping_mul(self.0 | 1);
        let final_mix = mixed ^ mixed.wrapping_add((mixed ^ (mixed >> 7)).wrapping_mul(mixed | 61));
        f64::from(final_mix ^ (final_mix >> 14)) / 4294967296.0
    }

    pub(crate) fn bipolar(&mut self) -> f64 {
        2.0 * self.uniform() - 1.0
    }

    /// 4個の一様乱数を足して、分散がほぼ1の対称な乱数にする。
    pub(crate) fn gauss(&mut self) -> f64 {
        let sum = self.uniform() + self.uniform() + self.uniform() + self.uniform();
        (sum - 2.0) * 1.7320508
    }
}
