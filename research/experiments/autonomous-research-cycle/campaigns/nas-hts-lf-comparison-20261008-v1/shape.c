/* 原HTSの有声LPF入力を固定LF周期関数へ置換する。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
static size_t observed,capacity;
static double *period_out,*counter_out,*source_out,*noise_out,*periodic_out,*phase_out;
static int lf_mode=0;
static double lf_coeff[7],sample_noise,sample_periodic,sample_phase;
int lf_evaluate(const double *,double *,size_t,const double *,size_t);
static uint8_t *event_out;
static double shape_excitation(HTS_Vocoder *,const double *);
#define HTS_Vocoder_initialize SHAPE_Vocoder_initialize
#define HTS_Vocoder_synthesize SHAPE_Vocoder_synthesize
#define HTS_Vocoder_clear SHAPE_Vocoder_clear
#include "HTS_vocoder_shaped.c"
#undef HTS_Vocoder_initialize
#undef HTS_Vocoder_synthesize
#undef HTS_Vocoder_clear
static double shape_excitation(HTS_Vocoder *v,const double *lpf) {
    double p=v->pitch_of_curr_point,c=v->pitch_counter;
    double x=HTS_Vocoder_get_excitation(v,lpf);
    if(observed<capacity){period_out[observed]=p;counter_out[observed]=c;source_out[observed]=x;event_out[observed]=p>0. && c+1.>=p;}
    if(observed<capacity){noise_out[observed]=sample_noise;periodic_out[observed]=sample_periodic;phase_out[observed]=sample_phase;}
    observed++;return x;
}
int shape_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,int selected,const double *coeff,double *out,double *period,
    double *counter,double *source,double *noise,double *periodic,double *phase,uint8_t *event,size_t samples) {
    if(capacity || !mcp||!lf0||!lpf||!out||!period||!counter||!source||!noise||!periodic||!phase||!coeff||!event || frames<1 || frames>6000 ||
       cols!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || (selected<0||selected>1))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO&&(exp(lf0[f])<70.||exp(lf0[f])>800.)))return 0;
        for(size_t j=0;j<35;j++)if(!isfinite(mcp[f*35+j]))return 0;
        for(size_t j=0;j<nlpf;j++)if(!isfinite(lpf[f*nlpf+j]))return 0;
    }
    double probe=0.,zero=0.;if(!lf_evaluate(&zero,&probe,1,coeff,7))return 0;
    double alpha=.55;
    lf_mode=selected;memcpy(lf_coeff,coeff,7*sizeof(double));noise_out=noise;periodic_out=periodic;phase_out=phase;
    observed=0;capacity=samples;period_out=period;counter_out=counter;source_out=source;event_out=event;
    HTS_Vocoder v;SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++) {
        double mc[35],lp[63];memcpy(mc,mcp+35*f,35*sizeof(double));memcpy(lp,lpf+nlpf*f,nlpf*sizeof(double));
        SHAPE_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,alpha,0.,1.,out+240*f,NULL);
    }
    size_t actual=observed;capacity=observed=0;period_out=counter_out=source_out=NULL;event_out=NULL;
    lf_mode=0;noise_out=periodic_out=phase_out=NULL;
    SHAPE_Vocoder_clear(&v);
    if(actual!=samples)return 0;
    for(size_t i=0;i<samples;i++)if(!isfinite(out[i])||!isfinite(period[i])||!isfinite(counter[i])||!isfinite(source[i])||!isfinite(noise[i])||!isfinite(periodic[i])||!isfinite(phase[i]))return 0;
    return 1;
}

