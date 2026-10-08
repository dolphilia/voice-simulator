/* 独自の全極合成lattice。前frameからの反射係数/対数gainを標本ごとに補間する。 */
#include <math.h>
#include <stddef.h>
int lattice_filter(const double *k,const double *logg,const double *x,double *y,
                   size_t frames,size_t order,size_t samples) {
    if(!k||!logg||!x||!y||frames<1||frames>6000||order<1||order>34||samples!=frames*240)return 0;
    for(size_t f=0;f<frames;f++){
        if(!isfinite(logg[f])||fabs(logg[f])>100.)return 0;
        for(size_t m=0;m<order;m++)if(!isfinite(k[f*order+m])||fabs(k[f*order+m])>=.99999999)return 0;
    }
    for(size_t i=0;i<samples;i++)if(!isfinite(x[i]))return 0;
    double state[34]={0};
    for(size_t f=0;f<frames;f++){
        size_t p=f?f-1:0;
        for(size_t j=0;j<240;j++){
            double u=(double)j/240.;
            double v=x[f*240+j]*exp(logg[p]+u*(logg[f]-logg[p]));
            for(size_t m=order;m>0;m--){
                double r=k[p*order+m-1]+u*(k[f*order+m-1]-k[p*order+m-1]);
                v-=r*state[m-1];
                if(m<order)state[m]=r*v+state[m-1];
            }
            state[0]=v;y[f*240+j]=v;
            if(!isfinite(v))return 0;
        }
    }
    return 1;
}
