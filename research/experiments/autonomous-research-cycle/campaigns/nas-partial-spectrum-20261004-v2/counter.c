/* 対応版ヘッダが所有するHTSエンジンを使い、MLPGと波形生成を分ける。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stdlib.h>

int counter_prepare(HTS_Engine *e) {
    if (!e || e->pss.total_frame || e->gss.total_frame) return 0;
    if (!HTS_Engine_generate_parameter_sequence(e)) return 0;
    return e->pss.nstream == 3 && e->pss.total_frame > 0 &&
        e->pss.pstream[0].vector_length > 1 && e->pss.pstream[1].vector_length == 1 &&
        e->pss.pstream[0].msd_flag == NULL && e->pss.pstream[2].msd_flag == NULL &&
        e->condition.stage == 0 && !e->condition.stop;
}
size_t counter_frames(HTS_Engine *e) { return e ? e->pss.total_frame : 0; }
size_t counter_length(HTS_Engine *e, size_t s) { return e && s < e->pss.nstream ? e->pss.pstream[s].vector_length : 0; }
int counter_copy(HTS_Engine *e, size_t s, double *out, size_t n) {
    if (!e || !out || s >= e->pss.nstream) return 0;
    HTS_PStream *p = &e->pss.pstream[s];
    if (n != e->pss.total_frame * p->vector_length) return 0;
    size_t k = 0;
    for (size_t f = 0; f < e->pss.total_frame; f++) {
        int voiced = !p->msd_flag || p->msd_flag[f];
        for (size_t j = 0; j < p->vector_length; j++)
            out[f*p->vector_length+j] = voiced ? p->par[k][j] : LZERO;
        if (voiced) k++;
    }
    return k == p->length;
}
/* 倍率1または0.75だけ許す。c0・LF0・LPFを保持する。 */
int counter_wave(HTS_Engine *e, double factor) {
    if (!e || (!isfinite(factor) || (factor != 1.0 && factor != 0.75)) || e->gss.total_frame || e->pss.nstream != 3 || !e->pss.total_frame) return 0;
    HTS_PStream *p = &e->pss.pstream[0];
    size_t n = p->length * p->vector_length;
    double *saved = NULL;
    if (factor != 1.0) {
        saved = malloc(n * sizeof(double));
        if (!saved) return 0;
        for (size_t f = 0; f < p->length; f++)
            for (size_t j = 0; j < p->vector_length; j++) {
                saved[f*p->vector_length+j] = p->par[f][j];
                if (j) p->par[f][j] *= factor;
            }
    }
    int ok = HTS_Engine_generate_sample_sequence(e);
    e->pss.nstream = 3;
    if (saved) {
        for (size_t f = 0; f < p->length; f++)
            for (size_t j = 0; j < p->vector_length; j++) p->par[f][j] = saved[f*p->vector_length+j];
        free(saved);
    }
    return ok;
}
size_t counter_output_streams(HTS_Engine *e) { return e ? e->gss.nstream : 0; }
double counter_output(HTS_Engine *e, size_t s, size_t f, size_t j) {
    if (!e || s >= e->gss.nstream || f >= e->gss.total_frame || j >= e->gss.gstream[s].vector_length) return NAN;
    return e->gss.gstream[s].par[f][j];
}
/* 条件を同じ内部表現のままPythonへ報告する。 */
int counter_settings(HTS_Engine *e, double *out, size_t n) {
    if (!e || !out || n != 9) return 0;
    double x[] = {e->condition.stage,e->condition.use_log_gain,e->condition.sampling_frequency,e->condition.fperiod,
        e->condition.alpha,e->condition.beta,e->condition.volume,e->condition.audio_buff_size,e->condition.stop};
    for (size_t i=0;i<n;i++) out[i]=x[i];
    return 1;
}
