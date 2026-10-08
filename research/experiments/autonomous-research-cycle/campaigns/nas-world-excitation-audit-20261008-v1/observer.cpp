// 追加観測は専用バッファのみを書き込む。元WORLDの状態・係数を変更しない。
#include <cmath>
#include <cstring>
static int obs_length=0,obs_count=0,obs_cursor=0;
static int *obs_index,*obs_noise;
static unsigned char *obs_vuv,*obs_emit;
static double *obs_shift,*obs_ap,*obs_norm,*obs_periodic,*obs_aperiodic;
static void ObsTime(int count,int length,const int *index,const double *shift,const double *vuv) {
  obs_count=count;
  for(int i=0;i<count;++i){obs_index[i]=index[i];obs_shift[i]=shift[i];}
  for(int i=0;i<length;++i)obs_vuv[i]=vuv[i]>0.5;
}
static void ObsResponse(int size,int noise,double vuv,double ap,const double *p,const double *a) {
  int cursor=obs_cursor++,offset=obs_index[cursor]-size/2+1;
  double norm=0.,scale=std::sqrt(static_cast<double>(noise));
  for(int i=0;i<size;++i)norm+=p[i]*p[i];
  obs_noise[cursor]=noise;obs_ap[cursor]=ap;obs_norm[cursor]=norm;
  obs_emit[cursor]=(vuv>0.5 && norm>0. && noise>0);
  int lower=offset<0?-offset:0,upper=size<obs_length-offset?size:obs_length-offset;
  for(int i=lower;i<upper;++i){obs_periodic[i+offset]+=p[i]*scale/size;obs_aperiodic[i+offset]+=a[i]/size;}
}
#define Synthesis ObservedSynthesis
#include "synthesis_observed.cpp"
#undef Synthesis
extern "C" int ObsRun(const double *f0,int n,const double * const *sp,const double * const *ap,
 int fft,double frame,int fs,int length,double *wave,int *index,double *shift,int *noise,
 double *ratio,double *norm,unsigned char *vuv,unsigned char *emit,double *periodic,double *aperiodic) {
 obs_length=length;obs_count=0;obs_cursor=0;obs_index=index;obs_shift=shift;obs_noise=noise;
 obs_ap=ratio;obs_norm=norm;obs_vuv=vuv;obs_emit=emit;obs_periodic=periodic;obs_aperiodic=aperiodic;
 std::memset(periodic,0,length*sizeof(double));std::memset(aperiodic,0,length*sizeof(double));
 ObservedSynthesis(f0,n,sp,ap,fft,frame,fs,length,wave);
 return obs_cursor==obs_count?obs_count:-1;
}
