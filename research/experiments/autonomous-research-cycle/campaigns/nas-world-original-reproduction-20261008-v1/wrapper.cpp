// 一次synthesis.cppの処理を変更せず、公開名だけを衝突防止のため変更する。
#define Synthesis ArcBareSynthesisV1
#include "synthesis.cpp"
#undef Synthesis
extern "C" int BareRun(const double *f0,int n,const double * const *sp,const double * const *ap,
 int fft,double frame,int fs,int length,double *wave) {
 ArcBareSynthesisV1(f0,n,sp,ap,fft,frame,fs,length,wave);
 return 1;
}
