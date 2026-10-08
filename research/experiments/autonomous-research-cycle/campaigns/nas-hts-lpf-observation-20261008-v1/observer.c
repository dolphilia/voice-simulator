/* 対応一次実装を純粋観測し、周期・位相・実パルス発生を記録する。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
static double *tr_period=NULL,*tr_counter=NULL;
static uint8_t *tr_pulse=NULL;
static size_t tr_index=0,tr_capacity=0;
static double *tr_lp,*tr_lp_periodic,*tr_filtered_periodic;
static double tr_ring[63],tr_filter_state[512];
static double tr_observe(HTS_Vocoder *v,const double *lpf);
static void tr_filter_observe(HTS_Vocoder *v,size_t m,double alpha,double volume);
#define HTS_Vocoder_initialize TRACE_Vocoder_initialize
#define HTS_Vocoder_synthesize TRACE_Vocoder_synthesize
#define HTS_Vocoder_clear TRACE_Vocoder_clear
#include "HTS_vocoder_observed.c"
#undef HTS_Vocoder_initialize
#undef HTS_Vocoder_synthesize
#undef HTS_Vocoder_clear
static double tr_observe(HTS_Vocoder *v,const double *lpf) {
    double p=v->pitch_of_curr_point,c=v->pitch_counter;
    uint8_t pulse=p>0. && c+1.>=p;
    /* 元の励振処理は1回だけ呼ぶ。乱数・状態・filter・係数を変更しない。 */
    size_t index=v->excite_buff_index;
    if (pulse) { double amplitude=sqrt(p);
        for (size_t i=0;i<v->excite_buff_size;i++)
            tr_ring[(index+i)%v->excite_buff_size]+=amplitude*lpf[i];
    }
    double periodic=tr_ring[index];tr_ring[index]=0.;
    double x=HTS_Vocoder_get_excitation(v,lpf);
    if (tr_index<tr_capacity) {
        tr_period[tr_index]=p;tr_counter[tr_index]=c;tr_pulse[tr_index]=pulse;
        tr_lp[tr_index]=x;tr_lp_periodic[tr_index]=periodic;
    }
    tr_index++;return x;
}
static void tr_filter_observe(HTS_Vocoder *v,size_t m,double alpha,double volume) {
    size_t i=tr_index-1;double p=tr_lp_periodic[i];
    if (p!=0.) p*=exp(v->c[0]);
    tr_filtered_periodic[i]=HTS_mlsadf(p,v->c,m,alpha,PADEORDER,tr_filter_state)*volume;
}
int trace_render(const double *mcp,const double *lf0,const double *lpf,
    const double *native_initial_mcp,int use_native_initial,size_t frames,size_t cols,size_t nlpf,
    double *out,double *period,double *counter,uint8_t *pulse,double *lp,double *lp_periodic,double *filtered_periodic,size_t samples) {
    if (tr_capacity || !mcp || !lf0 || !lpf || !native_initial_mcp || !out ||
        !period || !counter || !pulse || !lp || !lp_periodic || !filtered_periodic || frames<1 || frames>6000 || cols!=35 ||
        nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 ||
        (use_native_initial!=0 && use_native_initial!=1)) return 0;
    for (size_t f=0;f<frames;f++) {
        if (!isfinite(lf0[f]) || (lf0[f]!=LZERO && (exp(lf0[f])<70. || exp(lf0[f])>800.))) return 0;
        for (size_t j=0;j<35;j++) if (!isfinite(mcp[f*35+j])) return 0;
        for (size_t j=0;j<nlpf;j++) if (!isfinite(lpf[f*nlpf+j])) return 0;
    }
    for (size_t j=0;j<35;j++) if (!isfinite(native_initial_mcp[j])) return 0;
    HTS_Vocoder v;TRACE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    if (use_native_initial) {
        double p=lf0[0]==LZERO ? 0. : v.rate/exp(lf0[0]);
        HTS_Vocoder_initialize_excitation(&v,p,nlpf);
        HTS_mc2b(native_initial_mcp,v.c,34,.55);
        v.is_first=FALSE;
    }
    memset(tr_ring,0,sizeof(tr_ring));memset(tr_filter_state,0,sizeof(tr_filter_state));
    tr_lp=lp;tr_lp_periodic=lp_periodic;tr_filtered_periodic=filtered_periodic;
    tr_period=period;tr_counter=counter;tr_pulse=pulse;tr_capacity=samples;tr_index=0;
    for (size_t f=0;f<frames;f++) {
        double mc[35],lp[63];memcpy(mc,mcp+f*35,35*sizeof(double));
        memcpy(lp,lpf+f*nlpf,nlpf*sizeof(double));
        TRACE_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,.55,0.,1.,out+f*240,NULL);
    }
    size_t actual=tr_index;
    tr_lp=NULL;tr_lp_periodic=NULL;tr_filtered_periodic=NULL;
    tr_period=NULL;tr_counter=NULL;tr_pulse=NULL;tr_index=0;tr_capacity=0;
    TRACE_Vocoder_clear(&v);
    if (actual!=samples) return 0;
    for (size_t i=0;i<samples;i++) if (!isfinite(out[i]) || !isfinite(period[i]) ||
        !isfinite(counter[i]) || period[i]<0.) return 0;
    return 1;
}