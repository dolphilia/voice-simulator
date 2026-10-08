/* 独自の正規化波伝搬。媒体形状の生理正解や移動壁の仕事は主張しない。 */
#include <math.h>
#include <stddef.h>
int tube_render(const double *drive,const double *area,size_t samples,size_t sections,
                double rg,double rl,double *out,double *energy) {
 if(!drive||!area||!out||!energy||samples<1||samples>96000||sections<2||sections>44)return 0;
 if(!isfinite(rg)||!isfinite(rl)||fabs(rg)>=1.||fabs(rl)>=1.)return 0;
 for(size_t n=0;n<samples;n++) {
  if(!isfinite(drive[n]))return 0;
  for(size_t j=0;j<sections;j++) {
   double a=area[n*sections+j];if(!isfinite(a)||a<.05||a>12.)return 0;
  }
 }
 double right[44]={0},left[44]={0},nr[44],nl[44];
 for(size_t n=0;n<samples;n++) {
  out[n]=(1.+rl)*right[sections-1];
  nr[0]=drive[n]+rg*left[0];nl[sections-1]=rl*right[sections-1];
  for(size_t j=0;j+1<sections;j++) {
   double a=area[n*sections+j],b=area[n*sections+j+1];
   double k=(a-b)/(a+b),t=sqrt(1.-k*k);
   nr[j+1]=t*right[j]-k*left[j+1];nl[j]=k*right[j]+t*left[j+1];
  }
  double e=0.;for(size_t j=0;j<sections;j++) {
   right[j]=nr[j];left[j]=nl[j];e+=nr[j]*nr[j]+nl[j]*nl[j];
  }
  if(!isfinite(out[n])||!isfinite(e))return 0;energy[n]=e;
 }
 return 1;
}
