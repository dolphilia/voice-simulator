/* 対応版ヘッダで所有するHTSオブジェクトを包む。Pythonの内部ポインタは使わない。 */
#include "HTS_engine.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#define LOCAL_HALF_TONE 0.05776226504666210911810267678818

HTS_Engine *local_new(const char *voice) {
    HTS_Engine *e = calloc(1, sizeof(HTS_Engine));
    if (!e) return NULL;
    HTS_Engine_initialize(e);
    char *v = (char *)voice;
    if (!HTS_Engine_load(e, &v, 1)) { HTS_Engine_clear(e); free(e); return NULL; }
    return e;
}
void local_free(HTS_Engine *e) { if (e) { HTS_Engine_clear(e); free(e); } }
int local_states(HTS_Engine *e, char **labels, size_t n, double speed, double shift) {
    if (!e || !n || n > 122 || !isfinite(speed) || speed < .5 || speed > 2 || !isfinite(shift) || fabs(shift) > 12) return 0;
    HTS_Engine_set_speed(e, speed);
    HTS_Engine_add_half_tone(e, shift);
    return HTS_Engine_generate_state_sequence_from_strings(e, labels, n);
}
size_t local_nstate(HTS_Engine *e) { return HTS_Engine_get_nstate(e); }
size_t local_total_state(HTS_Engine *e) { return HTS_Engine_get_total_state(e); }
size_t local_nstream(HTS_Engine *e) { return HTS_Engine_get_nstream(e); }
size_t local_fperiod(HTS_Engine *e) { return HTS_Engine_get_fperiod(e); }
size_t local_fs(HTS_Engine *e) { return HTS_Engine_get_sampling_frequency(e); }
size_t local_vector(HTS_Engine *e, size_t s) { return s < e->sss.nstream ? e->sss.sstream[s].vector_length : 0; }
size_t local_windows(HTS_Engine *e, size_t s) { return s < e->sss.nstream ? e->sss.sstream[s].win_size : 0; }
size_t local_duration(HTS_Engine *e, size_t i) { return HTS_Engine_get_state_duration(e, i); }
double local_mean(HTS_Engine *e, size_t s, size_t i, size_t v) { return HTS_Engine_get_state_mean(e, s, i, v); }
double local_msd(HTS_Engine *e, size_t i) { return e->sss.sstream[1].msd ? e->sss.sstream[1].msd[i] : -1; }
int local_apply(HTS_Engine *e, double *delta, size_t n) {
    if (n != e->sss.total_state || e->sss.nstream < 2 || e->sss.sstream[1].vector_length != 1) return 0;
    for (size_t i = 0; i < n; ++i) {
        double value = HTS_Engine_get_state_mean(e, 1, i, 0) + delta[i] * LOCAL_HALF_TONE;
        if (!isfinite(delta[i]) || fabs(delta[i]) > 3 || value < 2.995732273553991 || value > 9.903487552536128) return 0;
    }
    for (size_t i = 0; i < n; ++i)
        HTS_Engine_set_state_mean(e, 1, i, 0, HTS_Engine_get_state_mean(e, 1, i, 0) + delta[i] * LOCAL_HALF_TONE);
    return 1;
}
int local_wave(HTS_Engine *e) { return HTS_Engine_generate_parameter_sequence(e) && HTS_Engine_generate_sample_sequence(e); }
size_t local_nsamples(HTS_Engine *e) { return HTS_Engine_get_nsamples(e); }
size_t local_frames(HTS_Engine *e) { return HTS_Engine_get_total_frame(e); }
double local_parameter(HTS_Engine *e, size_t s, size_t f, size_t v) { return HTS_Engine_get_generated_parameter(e, s, f, v); }
void local_copy_audio(HTS_Engine *e, double *out, size_t n) {
    if (n == HTS_Engine_get_nsamples(e)) memcpy(out, e->gss.gspeech, n * sizeof(double));
}
