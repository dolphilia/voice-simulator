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

/* 声道と放射の共通正規化状態。lossは遠方音圧ではない。 */
int tube_radiated(const double*drive,const double*area,size_t samples,size_t sections,double fs,double rg,const double*initial,double*final,double*out,double*energy){
 if(!drive||!area||!initial||!final||!out||!energy||samples<1||samples>96000||sections<2||sections>44||!isfinite(fs)||fs<16000||fs>96000||!isfinite(rg)||fabs(rg)>=1.)return 0;
 for(size_t j=0;j<2*sections+2;j++)if(!isfinite(initial[j]))return 0;
 for(size_t i=0;i<samples;i++){
  if(!isfinite(drive[i]))return 0;
  for(size_t j=0;j<sections;j++)if(!isfinite(area[i*sections+j])||area[i*sections+j]<.05||area[i*sections+j]>12.)return 0;
  double radius=.01*sqrt(area[i*sections+sections-1]/3.14159265358979323846);
  if(radius<.003||radius>.03)return 0;
 }
 double right[44],left[44],nr[44],nl[44],z0=initial[2*sections],z1=initial[2*sections+1],K[12];
 for(size_t j=0;j<sections;j++){right[j]=initial[j];left[j]=initial[sections+j];}
 for(size_t i=0;i<samples;i++){
  const double*a=area+i*sections;double radius=.01*sqrt(a[sections-1]/3.14159265358979323846);
  if(!port_matrix(fs,radius,0,K))return 0;
  double incident=right[sections-1];double v0=K[0]*z0+K[1]*z1+K[2]*incident,v1=K[3]*z0+K[4]*z1+K[5]*incident;
  nl[sections-1]=K[6]*z0+K[7]*z1+K[8]*incident;out[i]=K[9]*z0+K[10]*z1+K[11]*incident;
  nr[0]=drive[i]+rg*left[0];
  for(size_t j=0;j+1<sections;j++){
   double k=(a[j]-a[j+1])/(a[j]+a[j+1]),t=sqrt(1.-k*k);
   nr[j+1]=t*right[j]-k*left[j+1];nl[j]=k*right[j]+t*left[j+1];
  }
  z0=v0;z1=v1;double E=z0*z0+z1*z1;
  for(size_t j=0;j<sections;j++){right[j]=nr[j];left[j]=nl[j];E+=right[j]*right[j]+left[j]*left[j];}
  energy[i]=E;
 }
 for(size_t j=0;j<sections;j++){final[j]=right[j];final[sections+j]=left[j];}
 final[2*sections]=z0;final[2*sections+1]=z1;return 1;
}
