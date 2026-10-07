/* 対応版HTSヘッダと既存vocoderを使う全フレーム配列入口。BSD通知を同梱。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stddef.h>
#include <string.h>
int hts_arrays_render(const double *mcp,const double *lf0,const double *lpf,
                      size_t frames,size_t nmcp,size_t nlpf,double *out,size_t samples) {
    if (!mcp || !lf0 || !lpf || !out || frames<1 || frames>6000 ||
        nmcp!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240) return 0;
    for (size_t f=0;f<frames;f++) {
        if (!isfinite(lf0[f]) || (lf0[f]!=LZERO && (exp(lf0[f])<70 || exp(lf0[f])>800))) return 0;
        for (size_t j=0;j<nmcp;j++) if (!isfinite(mcp[f*nmcp+j])) return 0;
        for (size_t j=0;j<nlpf;j++) if (!isfinite(lpf[f*nlpf+j])) return 0;
    }
    HTS_Vocoder v;
    HTS_Vocoder_initialize(&v,nmcp-1,0,FALSE,48000,240);
    for (size_t f=0;f<frames;f++) {
        double mc[35],lp[63];
        memcpy(mc,mcp+f*nmcp,nmcp*sizeof(double));
        memcpy(lp,lpf+f*nlpf,nlpf*sizeof(double));
        HTS_Vocoder_synthesize(&v,nmcp-1,lf0[f],mc,nlpf,lp,.55,0.,1.,out+f*240,NULL);
    }
    HTS_Vocoder_clear(&v);
    for (size_t i=0;i<samples;i++) if (!isfinite(out[i])) return 0;
    return 1;
}
