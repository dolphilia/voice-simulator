/* 一次反射係数の独自エネルギー状態実現。人体の移動壁の仕事ではない。 */
#include <math.h>
#include <stddef.h>
static void mul(const double a[2][2],const double b[2][2],double c[2][2]){
 for(int i=0;i<2;i++)for(int j=0;j<2;j++)c[i][j]=a[i][0]*b[0][j]+a[i][1]*b[1][j];
}
int port_matrix(double fs,double radius,int flanged,double*out){
 if(!out||!isfinite(fs)||fs<16000||fs>96000||!isfinite(radius)||radius<.003||radius>.03||(flanged!=0&&flanged!=1))return 0;
 double n1=flanged?.182:.167,d1=flanged?1.825:1.393,d2=flanged?.649:.457;
 double delta=d1*d1-2.*d2-n1*n1,sd=sqrt(delta);
 double p00=d1-n1,p01=d2,p11=d2*(d1-sd);
 double u00=sqrt(p00),u01=p01/u00,u11=sqrt(p11-u01*u01);
 double U[2][2]={{u00,u01},{0.,u11}},V[2][2]={{1./u00,-u01/(u00*u11)},{0.,1./u11}};
 double A[2][2]={{0.,1.},{-1./d2,-d1/d2}},temp[2][2],AA[2][2];mul(U,A,temp);mul(temp,V,AA);
 double B[2]={u01/d2,u11/d2},CC[2][2];
 double C[2][2]={{-1.,-n1},{-1.,sd-d1}};mul(C,V,CC);
 double h=343./(2.*fs*radius),root=sqrt(2.*h);
 double M[2][2]={{1.-h*AA[0][0],-h*AA[0][1]},{-h*AA[1][0],1.-h*AA[1][1]}};
 double det=M[0][0]*M[1][1]-M[0][1]*M[1][0];
 double inv[2][2]={{M[1][1]/det,-M[0][1]/det},{-M[1][0]/det,M[0][0]/det}};
 double plus[2][2]={{1.+h*AA[0][0],h*AA[0][1]},{h*AA[1][0],1.+h*AA[1][1]}},Ad[2][2],Cd[2][2];mul(inv,plus,Ad);mul(CC,inv,Cd);
 double ib[2]={inv[0][0]*B[0]+inv[0][1]*B[1],inv[1][0]*B[0]+inv[1][1]*B[1]};
 for(int i=0;i<2;i++){out[i*3]=Ad[i][0];out[i*3+1]=Ad[i][1];out[i*3+2]=root*ib[i];}
 for(int i=0;i<2;i++){out[(i+2)*3]=root*Cd[i][0];out[(i+2)*3+1]=root*Cd[i][1];out[(i+2)*3+2]=(i==1?1.:0.)+h*(CC[i][0]*ib[0]+CC[i][1]*ib[1]);}
 for(int i=0;i<12;i++)if(!isfinite(out[i]))return 0;return 1;
}
int radiation_port(const double*x,const double*radius,size_t n,double fs,int flanged,const double*initial,double*last,double*reflected,double*loss,double*energy){
 if(!x||!radius||!initial||!last||!reflected||!loss||!energy||n<1||n>96000||!isfinite(fs)||fs<16000||fs>96000||(flanged!=0&&flanged!=1))return 0;
 if(!isfinite(initial[0])||!isfinite(initial[1]))return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(x[i])||!isfinite(radius[i])||radius[i]<.003||radius[i]>.03)return 0;
 double z0=initial[0],z1=initial[1],K[12];
 for(size_t i=0;i<n;i++){
  if(!port_matrix(fs,radius[i],flanged,K))return 0;
  double v0=K[0]*z0+K[1]*z1+K[2]*x[i],v1=K[3]*z0+K[4]*z1+K[5]*x[i];
  reflected[i]=K[6]*z0+K[7]*z1+K[8]*x[i];loss[i]=K[9]*z0+K[10]*z1+K[11]*x[i];
  z0=v0;z1=v1;energy[i]=z0*z0+z1*z1;
 }
 last[0]=z0;last[1]=z1;return 1;
}
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

/* 左端は理想体積速度源。口元flowと源の仕事はSI、lossは収支専用。 */
int tube_volume(const double*u,const double*area,size_t n,const double*initial,double*last,double*mouth,double*source_pressure,double*loss,double*energy){
 if(!u||!area||!initial||!last||!mouth||!source_pressure||!loss||!energy||n<1||n>96000)return 0;
 for(size_t j=0;j<34;j++)if(!isfinite(initial[j])||fabs(initial[j])>100.)return 0;
 for(size_t i=0;i<n;i++){
  if(!isfinite(u[i])||fabs(u[i])>.001)return 0;
  for(size_t j=0;j<16;j++)if(!area_ok(area[16*i+j]))return 0;
  double radius=.01*sqrt(area[16*i+15]/3.14159265358979323846);if(radius<.003||radius>.03)return 0;
 }
 double r[16],l[16],nr[16],nl[16],z0=initial[32],z1=initial[33],K[12];
 for(int j=0;j<16;j++){r[j]=initial[j];l[j]=initial[16+j];}
 for(size_t i=0;i<n;i++){
  const double*a=area+16*i;double radius=.01*sqrt(a[15]/3.14159265358979323846);
  if(!port_matrix(34300.,radius,1,K))return 0;
  double incident=r[15],v0=K[0]*z0+K[1]*z1+K[2]*incident,v1=K[3]*z0+K[4]*z1+K[5]*incident;
  nl[15]=K[6]*z0+K[7]*z1+K[8]*incident;loss[i]=K[9]*z0+K[10]*z1+K[11]*incident;
  double root=sqrt(a[0]*1e-4);nr[0]=1.2*343.*u[i]/root+l[0];source_pressure[i]=(nr[0]+l[0])/root;
  mouth[i]=sqrt(a[15]*1e-4)*(incident-nl[15])/(1.2*343.);
  for(int j=0;j<15;j++){double k=(a[j]-a[j+1])/(a[j]+a[j+1]),t=sqrt(1.-k*k);nr[j+1]=t*r[j]-k*l[j+1];nl[j]=k*r[j]+t*l[j+1];}
  z0=v0;z1=v1;double E=z0*z0+z1*z1;
  for(int j=0;j<16;j++){r[j]=nr[j];l[j]=nl[j];E+=r[j]*r[j]+l[j]*l[j];}
  energy[i]=E/(1.2*343.*34300.);
 }
 for(int j=0;j<16;j++){last[j]=r[j];last[16+j]=l[j];}last[32]=z0;last[33]=z1;return 1;
}
