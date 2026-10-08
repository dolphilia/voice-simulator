/* 論文の式から独自に実装。コード転載なし。固定半径の因果的反射だけ。 */
#include <math.h>
#include <stddef.h>
int radiation(const double*x,size_t n,double fs,double radius,int flanged,const double*initial,double*last,double*y,double*p,double*u){
 if(!x||!initial||!last||!y||!p||!u||n<1||n>96000||!isfinite(fs)||!isfinite(radius)||fs<16000||fs>96000||radius<.003||radius>.03||(flanged!=0&&flanged!=1))return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(x[i]))return 0;
 for(size_t i=0;i<4;i++)if(!isfinite(initial[i]))return 0;
 double n1=flanged?.182:.167,d1=flanged?1.825:1.393,d2=flanged?.649:.457;
 double q=2.*fs*radius/343.,den=1.+d1*q+d2*q*q;
 double b0=-(1.+n1*q)/den,b1=-2./den,b2=-(1.-n1*q)/den;
 double a1=(2.-2.*d2*q*q)/den,a2=(1.-d1*q+d2*q*q)/den;
 double x1=initial[0],x2=initial[1],y1=initial[2],y2=initial[3];
 for(size_t i=0;i<n;i++){
  double z=b0*x[i]+b1*x1+b2*x2-a1*y1-a2*y2;
  y[i]=z;p[i]=x[i]+z;u[i]=x[i]-z;
  x2=x1;x1=x[i];y2=y1;y1=z;
 }
 last[0]=x1;last[1]=x2;last[2]=y1;last[3]=y2;return 1;
}
