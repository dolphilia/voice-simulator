/* MCPのHMM状態平均・分散だけを交換する独自shim。MLPG前に全検証する。 */
#include "HTS_hidden.h"
#include <math.h>
#include <string.h>
static int ready(const HTS_Engine *e) {
 return e && e->sss.nstream==3 && e->sss.total_state && e->sss.sstream &&
  e->sss.duration && !e->pss.total_frame && !e->gss.total_frame;
}
int mcp_transfer(HTS_Engine *dst,const HTS_Engine *src) {
 if(!ready(dst)||!ready(src)||dst->sss.total_state!=src->sss.total_state||
    dst->sss.nstate!=src->sss.nstate)return 0;
 HTS_SStream *a=&dst->sss.sstream[0];const HTS_SStream *b=&src->sss.sstream[0];
 if(a->vector_length!=35||b->vector_length!=35||a->win_size!=3||b->win_size!=3||
    a->msd||b->msd||!a->mean||!a->vari||!b->mean||!b->vari)return 0;
 for(size_t w=0;w<3;w++) {
  if(a->win_l_width[w]!=b->win_l_width[w]||a->win_r_width[w]!=b->win_r_width[w])return 0;
  for(int j=a->win_l_width[w];j<=a->win_r_width[w];j++)
   if(a->win_coefficient[w][j]!=b->win_coefficient[w][j])return 0;
 }
 for(size_t i=0;i<dst->sss.total_state;i++)for(size_t v=0;v<105;v++)
  if(!isfinite(b->mean[i][v])||!isfinite(b->vari[i][v])||b->vari[i][v]<=0.)return 0;
 for(size_t i=0;i<dst->sss.total_state;i++) {
  memcpy(a->mean[i],b->mean[i],105*sizeof(double));
  memcpy(a->vari[i],b->vari[i],105*sizeof(double));
 }
 return 1;
}
size_t mcp_gv_count(const HTS_Engine *e) {
 if(!e||!e->sss.sstream||e->sss.nstream!=3)return 0;
 size_t n=0;
 for(size_t s=0;s<3;s++) {
  const HTS_SStream *p=&e->sss.sstream[s];n+=3;
  if(p->gv_mean)n+=p->vector_length;
  if(p->gv_vari)n+=p->vector_length;
  if(p->gv_switch)n+=e->sss.total_state;
 }
 return n;
}
int mcp_gv_copy(const HTS_Engine *e,double *out,size_t n) {
 if(!out||!n||n!=mcp_gv_count(e))return 0;
 size_t k=0;
 for(size_t s=0;s<3;s++) {
  const HTS_SStream *p=&e->sss.sstream[s];
  out[k++]=p->gv_mean!=NULL;out[k++]=p->gv_vari!=NULL;out[k++]=p->gv_switch!=NULL;
  if(p->gv_mean)for(size_t j=0;j<p->vector_length;j++)out[k++]=p->gv_mean[j];
  if(p->gv_vari)for(size_t j=0;j<p->vector_length;j++)out[k++]=p->gv_vari[j];
  if(p->gv_switch)for(size_t j=0;j<e->sss.total_state;j++)out[k++]=p->gv_switch[j];
 }
 return k==n;
}
