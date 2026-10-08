/* 開閉比を固定した声門流の離散微分。元の乱数と周期時計は一度だけ進める。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define RING 2048
static double old_ring[RING],new_ring[RING];
static size_t cursor,observed,capacity;
static int mode;
static double *period_out,*counter_out;
static uint8_t *event_out;
static double shape_excitation(HTS_Vocoder *,const double *);
#define HTS_Vocoder_initialize SHAPE_Vocoder_initialize
#define HTS_Vocoder_synthesize SHAPE_Vocoder_synthesize
#define HTS_Vocoder_clear SHAPE_Vocoder_clear
#include "HTS_vocoder_shaped.c"
#undef HTS_Vocoder_initialize
#undef HTS_Vocoder_synthesize
#undef HTS_Vocoder_clear
/* 有声開始はphase原点0。それ以外は元clockの端数を同じcell内で補間する。 */
static double previous_period=0.;
static double *phase_out=NULL;
int shape_kernel(double p,int selected,double remainder,double *out,size_t n) {
    if(!isfinite(p)||p<60.||p>48000./70.||n!=9||selected<1||selected>4||!isfinite(remainder)||remainder<0.||remainder>1.)return 0;
    double position=4.-remainder,energy=0.;
    for(size_t i=0;i<n;i++)out[i]=0.;
    if(selected==1)out[4]=1.;
    else if(selected==2){out[3]=remainder;out[4]=1.-remainder;}
    else {
        for(size_t i=0;i<n;i++) {
            double d=(double)i-position;
            if(fabs(d)<=4.)out[i]=(fabs(d)<1e-12?1.:sin(M_PI*d)/(M_PI*d))*(.5+.5*cos(M_PI*d/4.));
        }
    }
    for(size_t i=0;i<n;i++)energy+=out[i]*out[i];
    if(energy<=0.)return 0;
    double sum=0.;for(size_t i=0;i<n;i++)sum+=out[i];
    if(selected==4 && sum<=1e-12)return 0;
    double scale=selected==4?sqrt(p)/sum:sqrt(p/energy);for(size_t i=0;i<n;i++)out[i]*=scale;
    return 1;
}
static double shape_excitation(HTS_Vocoder *v,const double *lpf) {
    double p=v->pitch_of_curr_point,c=v->pitch_counter;
    uint8_t event=p>0. && c+1.>=p;
    double remainder=event?fmax(0.,fmin(1.,c+1.-p)):0.;
    if(observed==0 || previous_period==0.)remainder=0.;
    if(event) {
        double kernel[9];
        if(!shape_kernel(p,mode?mode:1,remainder,kernel,9))return NAN;
        for(size_t j=0;j<v->excite_buff_size;j++) {
            old_ring[(cursor+j)%RING]+=sqrt(p)*lpf[j];
            for(size_t k=0;k<9;k++)new_ring[(cursor+j+k)%RING]+=kernel[k]*lpf[j];
        }
    }
    /* 元のget_excitationを一度だけ呼び、noise/RNG/period/counterを保存する。 */
    double x=HTS_Vocoder_get_excitation(v,lpf);
    if(observed<capacity){period_out[observed]=p;counter_out[observed]=c;phase_out[observed]=remainder;event_out[observed]=event;}
    if(mode)x+=new_ring[cursor]-old_ring[cursor];
    old_ring[cursor]=new_ring[cursor]=0.;cursor=(cursor+1)%RING;previous_period=p;observed++;
    return x;
}
int shape_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,int selected,double *out,double *period,
    double *counter,double *phase,uint8_t *event,size_t samples) {
    if(capacity || !mcp||!lf0||!lpf||!out||!period||!counter||!phase||!event || frames<1 || frames>6000 ||
       cols!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || (selected<0||selected>4))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO&&(exp(lf0[f])<70.||exp(lf0[f])>800.)))return 0;
        for(size_t j=0;j<35;j++)if(!isfinite(mcp[f*35+j]))return 0;
        for(size_t j=0;j<nlpf;j++)if(!isfinite(lpf[f*nlpf+j]))return 0;
    }
    memset(old_ring,0,sizeof(old_ring));memset(new_ring,0,sizeof(new_ring));
    cursor=observed=0;previous_period=0.;phase_out=phase;capacity=samples;mode=selected;period_out=period;counter_out=counter;event_out=event;
    HTS_Vocoder v;SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++) {
        double mc[35],lp[63];memcpy(mc,mcp+35*f,35*sizeof(double));memcpy(lp,lpf+nlpf*f,nlpf*sizeof(double));
        SHAPE_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,.55,0.,1.,out+240*f,NULL);
    }
    size_t actual=observed;capacity=observed=0;period_out=counter_out=phase_out=NULL;event_out=NULL;
    SHAPE_Vocoder_clear(&v);
    if(actual!=samples)return 0;
    for(size_t i=0;i<samples;i++)if(!isfinite(out[i])||!isfinite(period[i])||!isfinite(counter[i]))return 0;
    return 1;
}
