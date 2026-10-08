/* HMM状態平均・MSD・総フレーム数を保持し、MLPG前の状態長だけを変更する。 */
#include "HTS_hidden.h"
#include <stdint.h>
int timing_apply(HTS_Engine *e, const size_t *values, size_t n) {
 if (!e || !values || !n || n != e->sss.total_state || !e->sss.duration ||
     e->pss.total_frame || e->gss.total_frame || !e->sss.total_frame) return 0;
 size_t sum = 0;
 for (size_t i=0;i<n;i++) {
  if (!values[i] || values[i] > e->sss.total_frame || SIZE_MAX-sum < values[i]) return 0;
  sum += values[i];
 }
 if (sum != e->sss.total_frame) return 0;
 for (size_t i=0;i<n;i++) e->sss.duration[i]=values[i];
 return 1;
}

size_t timing_vari_count(HTS_Engine *e) {
 if (!e || !e->sss.total_state || !e->sss.nstream) return 0;
 size_t n=0;
 for (size_t s=0;s<e->sss.nstream;s++) n+=e->sss.total_state*e->sss.sstream[s].vector_length*e->sss.sstream[s].win_size;
 return n;
}
int timing_vari_copy(HTS_Engine *e, double *out, size_t n) {
 if (!out || !n || n!=timing_vari_count(e)) return 0;
 size_t k=0;
 for (size_t s=0;s<e->sss.nstream;s++) {
  HTS_SStream *p=&e->sss.sstream[s];
  for (size_t i=0;i<e->sss.total_state;i++)
   for (size_t v=0;v<p->vector_length*p->win_size;v++) out[k++]=p->vari[i][v];
 }
 return k==n;
}
