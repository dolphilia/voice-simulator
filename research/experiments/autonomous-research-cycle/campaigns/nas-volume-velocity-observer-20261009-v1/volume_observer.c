/* 一次の平面波とRayleigh式から独自実装。正規化振幅の単位を明示する。 */
#include <math.h>
#include <stddef.h>
#include <string.h>
static int area_ok(double a){return isfinite(a)&&a>=.05&&a<=12.;}
int volume_boundary(const double*u,const double*left,const double*area,size_t n,double*right,double*pressure){
 if(!u||!left||!area||!right||!pressure||n<1||n>96000)return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(u[i])||fabs(u[i])>.001||!isfinite(left[i])||fabs(left[i])>100.||!area_ok(area[i]))return 0;
 for(size_t i=0;i<n;i++){double root=sqrt(area[i]*1e-4);right[i]=1.2*343.*u[i]/root+left[i];pressure[i]=(right[i]+left[i])/root;}
 return 1;
}
int mouth_units(const double*right,const double*left,const double*area,size_t n,double*pressure,double*volume){
 if(!right||!left||!area||!pressure||!volume||n<1||n>96000)return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(right[i])||fabs(right[i])>100.||!isfinite(left[i])||fabs(left[i])>100.||!area_ok(area[i]))return 0;
 for(size_t i=0;i<n;i++){double root=sqrt(area[i]*1e-4);pressure[i]=(right[i]+left[i])/root;volume[i]=root*(right[i]-left[i])/(1.2*343.);}
 return 1;
}
int axial_observer(const double*u,size_t n,double distance,const double*initial,double*last,double*out){
 if(!u||!initial||!last||!out||n<1||n>96000||!(distance==.5||distance==1.||distance==2.))return 0;
 int delay=(int)(distance*100.),length=delay+8;
 for(size_t i=0;i<n;i++)if(!isfinite(u[i])||fabs(u[i])>.001)return 0;
 for(int i=0;i<length;i++)if(!isfinite(initial[i])||fabs(initial[i])>.001)return 0;
 double history[209],h[9]={0.},coef[4]={4./5.,-1./5.,4./105.,-1./280.};
 for(int j=1;j<=4;j++){h[4-j]=34300.*coef[j-1];h[4+j]=-34300.*coef[j-1];}
 memcpy(history,initial,(size_t)length*sizeof(double));double factor=1.2/(2.*acos(-1.)*distance);
 for(size_t i=0;i<n;i++){
  memmove(history+1,history,(size_t)length*sizeof(double));history[0]=u[i];double sum=0.;
  for(int k=0;k<9;k++)sum+=h[k]*history[delay+k];out[i]=factor*sum;
 }
 memcpy(last,history,(size_t)length*sizeof(double));return 1;
}
