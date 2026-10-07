/* 対応HTS一次式のMCP後処理入口。元BSD通知をvendorと同梱する。 */
#define HTS_Vocoder_initialize PF_Vocoder_initialize
#define HTS_Vocoder_synthesize PF_Vocoder_synthesize
#define HTS_Vocoder_clear PF_Vocoder_clear
#include "HTS_vocoder.c"
#include <string.h>
#include <stddef.h>
/* β0の無変更とβ0.2の既存エネルギー補正を共有する。 */
int mcp_postfilter(const double *input,size_t frames,size_t cols,double beta,
                   double *output,double *before,double *after) {
    if (!input || !output || !before || !after || frames<1 || frames>6000 ||
        cols!=35 || (beta!=0. && beta!=.2)) return 0;
    for(size_t i=0;i<frames*cols;i++) if(!isfinite(input[i])) return 0;
    HTS_Vocoder v;
    PF_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++){
        double b[35];
        memcpy(output+f*35,input+f*35,35*sizeof(double));
        HTS_mc2b(output+f*35,b,34,.55);
        before[f]=HTS_b2en(&v,b,34,.55);
        HTS_Vocoder_postfilter_mcp(&v,output+f*35,34,.55,beta);
        HTS_mc2b(output+f*35,b,34,.55);
        after[f]=HTS_b2en(&v,b,34,.55);
    }
    PF_Vocoder_clear(&v);
    for(size_t f=0;f<frames;f++) if(!isfinite(before[f]) || !isfinite(after[f]) ||
        before[f]<=0 || after[f]<=0) return 0;
    for(size_t i=0;i<frames*35;i++) if(!isfinite(output[i])) return 0;
    return 1;
}
/* 工学fixtureだけに使うHTS内部β付き生成。最終経路は前処理→β0生成。 */
int pf_reference_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,double beta,double *out,size_t samples){
    if(!mcp || !lf0 || !lpf || !out || frames<1 || frames>6000 || cols!=35 ||
        nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || (beta!=0. && beta!=.2)) return 0;
    for(size_t f=0;f<frames;f++){
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO && (exp(lf0[f])<70 || exp(lf0[f])>800))) return 0;
        for(size_t j=0;j<35;j++) if(!isfinite(mcp[f*35+j])) return 0;
        for(size_t j=0;j<nlpf;j++) if(!isfinite(lpf[f*nlpf+j])) return 0;
    }
    HTS_Vocoder v;PF_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++){
        double mc[35],lp[63];memcpy(mc,mcp+f*35,35*sizeof(double));
        memcpy(lp,lpf+f*nlpf,nlpf*sizeof(double));
        PF_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,.55,beta,1.,out+f*240,NULL);
    }
    PF_Vocoder_clear(&v);
    for(size_t i=0;i<samples;i++) if(!isfinite(out[i])) return 0;
    return 1;
}
