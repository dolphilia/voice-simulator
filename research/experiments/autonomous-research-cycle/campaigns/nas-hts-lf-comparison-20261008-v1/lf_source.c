/* 独自LF周期関数。係数は固定時間比とゼロ面積の式から求め、波形からfitしない。 */
#include <math.h>
#include <stddef.h>
int lf_evaluate(const double *phase,double *out,size_t n,const double *c,size_t cols) {
 if(!phase||!out||!c||!n||cols!=7)return 0;
 for(size_t j=0;j<7;j++)if(!isfinite(c[j]))return 0;
 const double tp=c[0],te=c[1],ta=c[2],ep=c[3],a=c[4],e0=c[5],scale=c[6];
 if(!(0.<tp&&tp<te&&te<1.&&ta>0.&&ta<1.-te&&ep>0.&&a>0.&&e0>0.&&scale>0.))return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(phase[i])||phase[i]<0.||phase[i]>1.)return 0;
 const double w=3.14159265358979323846264338327950288/tp,end=exp(-ep*(1.-te));
 for(size_t i=0;i<n;i++){
  double t=phase[i];
  double g=t<=te?e0*exp(a*t)*sin(w*t):-(exp(-ep*(t-te))-end)/(ep*ta);
  out[i]=g*scale;if(!isfinite(out[i]))return 0;
 }
 return 1;
}
