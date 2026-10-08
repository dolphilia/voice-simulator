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
/* LPFだけを単位インパルスへ置換する。3streamとLPF長は変えない。 */
int counter_wave(HTS_Engine *e, int mode) {
    if (!e || mode < 0 || mode > 1 || e->gss.total_frame || e->pss.nstream != 3 || !e->pss.total_frame) return 0;
    HTS_PStream *p = &e->pss.pstream[2];
    if (!p->vector_length || p->vector_length % 2 != 1 || p->length != e->pss.total_frame || p->msd_flag) return 0;
    size_t n = p->length * p->vector_length;
    double *saved = NULL;
    if (mode == 1) {
        saved = malloc(n * sizeof(double));
        if (!saved) return 0;
        size_t center = (p->vector_length - 1) / 2;
        for (size_t f = 0; f < p->length; f++)
            for (size_t j = 0; j < p->vector_length; j++) {
                saved[f*p->vector_length+j] = p->par[f][j];
                p->par[f][j] = j == center ? 1.0 : 0.0;
            }
    }
    int ok = HTS_Engine_generate_sample_sequence(e);
    if (saved) {
        for (size_t f = 0; f < p->length; f++)
            for (size_t j = 0; j < p->vector_length; j++) p->par[f][j] = saved[f*p->vector_length+j];
        free(saved);
    }
    return ok;
}
/* 工学自己検査専用。全LF0を無声値にして、生成後は全値を復元する。 */
int counter_unvoiced_test(HTS_Engine *e, int mode) {
    if (!e || e->pss.nstream != 3 || !e->pss.total_frame || e->gss.total_frame || mode < 0 || mode > 1) return 0;
    HTS_PStream *p = &e->pss.pstream[1];
    if (p->vector_length != 1 || !p->length) return 0;
    double *saved = malloc(p->length * sizeof(double));
    if (!saved) return 0;
    for (size_t f=0; f<p->length; f++) { saved[f]=p->par[f][0];p->par[f][0]=LZERO; }
    int ok=counter_wave(e,mode);
    for (size_t f=0; f<p->length; f++) p->par[f][0]=saved[f];
    free(saved);return ok;
}
/* 全GSS列をそのまま転送し、検証のPythonセル呼出数を減らす。 */
int counter_output_copy(HTS_Engine *e, size_t s, double *out, size_t n) {
    if (!e || !out || s >= e->gss.nstream) return 0;
    HTS_GStream *p=&e->gss.gstream[s];
    if (n != e->gss.total_frame*p->vector_length) return 0;
    for (size_t f=0; f<e->gss.total_frame; f++)
        for (size_t j=0;j<p->vector_length;j++) out[f*p->vector_length+j]=p->par[f][j];
    return 1;
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
