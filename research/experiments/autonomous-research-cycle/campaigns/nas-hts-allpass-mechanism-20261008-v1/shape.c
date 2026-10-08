/* 原HTSを純観測し、その励振に独立の最小位相FIRを適用する別版。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
static size_t observed,capacity;
static double *period_out,*counter_out,*source_out,*processed_out;
static int phase_mode=0;
static double phase_x=0.,phase_y=0.;
/* 一次オールパス。係数は登録時に固定し、MCPや波形から適応させない。 */
static double phase_step(double x,double *xp,double *yp) {
    double y=.95*(*yp)+(*xp)-.95*x;*xp=x;*yp=y;return y;
}
int phase_filter(const double *x,double *out,size_t n) {
    if(!x||!out||n<1||n>2880000)return 0;
    double xp=0.,yp=0.;
    for(size_t i=0;i<n;i++){if(!isfinite(x[i]))return 0;out[i]=phase_step(x[i],&xp,&yp);if(!isfinite(out[i]))return 0;}
    return 1;
}
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
    double y=phase_mode?phase_step(x,&phase_x,&phase_y):x;
    if(observed<capacity)processed_out[observed]=y;
    observed++;return y;
}
int shape_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,int selected,double *out,double *period,
    double *counter,double *source,double *processed,uint8_t *event,size_t samples) {
    if(capacity || !mcp||!lf0||!lpf||!out||!period||!counter||!source||!processed||!event || frames<1 || frames>6000 ||
       cols!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || (selected<0||selected>1))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO&&(exp(lf0[f])<70.||exp(lf0[f])>800.)))return 0;
        for(size_t j=0;j<35;j++)if(!isfinite(mcp[f*35+j]))return 0;
        for(size_t j=0;j<nlpf;j++)if(!isfinite(lpf[f*nlpf+j]))return 0;
    }
    double alpha=.55;
    phase_mode=selected;phase_x=phase_y=0.;processed_out=processed;
    observed=0;capacity=samples;period_out=period;counter_out=counter;source_out=source;event_out=event;
    HTS_Vocoder v;SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++) {
        double mc[35],lp[63];memcpy(mc,mcp+35*f,35*sizeof(double));memcpy(lp,lpf+nlpf*f,nlpf*sizeof(double));
        SHAPE_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,alpha,0.,1.,out+240*f,NULL);
    }
    size_t actual=observed;capacity=observed=0;period_out=counter_out=source_out=NULL;event_out=NULL;
    phase_mode=0;phase_x=phase_y=0.;processed_out=NULL;
    SHAPE_Vocoder_clear(&v);
    if(actual!=samples)return 0;
    for(size_t i=0;i<samples;i++)if(!isfinite(out[i])||!isfinite(period[i])||!isfinite(counter[i])||!isfinite(source[i])||!isfinite(processed[i]))return 0;
    return 1;
}

/* MCPの周波数変換と最小位相IR。alphaは通常.55、fixtureで0も照合。 */
int shape_kernel(const double *mc,double alpha,double *h,size_t length) {
    if(!mc||!h||length!=1024||!isfinite(alpha)||fabs(alpha)>=1.)return 0;
    for(size_t k=0;k<35;k++)if(!isfinite(mc[k]))return 0;
    HTS_Vocoder v;double cep[1024];
    SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    HTS_freqt(&v,mc,34,cep,1023,-alpha);
    HTS_c2ir(cep,1024,h,1024);
    SHAPE_Vocoder_clear(&v);
    for(size_t k=0;k<1024;k++)if(!isfinite(h[k]))return 0;
    return 1;
}
/* 出力時刻のIRを前frameから線形補間し、過去の励振だけを参照する。 */
int shape_fir(const double *mc,const double *source,size_t frames,double *out) {
    if(!mc||!source||!out||frames<1||frames>6000)return 0;
    double previous[1024],current[1024];
    if(!shape_kernel(mc,.55,previous,1024))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!shape_kernel(mc+35*f,.55,current,1024))return 0;
        for(size_t j=0;j<240;j++) {
            size_t n=f*240+j,maximum=n<1023?n:1023;
            double u=(double)j/240.,y=0.;
            for(size_t k=0;k<=maximum;k++) {
                double h=previous[k]+u*(current[k]-previous[k]);
                y+=h*source[n-k];
            }
            if(!isfinite(y))return 0;
            out[n]=y;
        }
        memcpy(previous,current,sizeof(previous));
    }
    return 1;
}
