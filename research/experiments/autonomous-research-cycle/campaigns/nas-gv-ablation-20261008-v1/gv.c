/* GV補正の有効/無効を、対応版エンジンの実ストリームで確認する。 */
#include "HTS_hidden.h"
#include <stddef.h>
int gv_status(HTS_Engine *e, double *out, size_t n) {
    if (!e || !out || n != 12 || e->sss.nstream != 3) return 0;
    for (size_t s=0;s<3;s++) {
        HTS_SStream *p=&e->sss.sstream[s];
        out[s*4]=p->gv_mean != NULL;
        out[s*4+1]=p->gv_vari != NULL;
        out[s*4+2]=-1;
        out[s*4+3]=e->condition.gv_weight[s];
        if (e->pss.nstream==3) {
            HTS_PStream *q=&e->pss.pstream[s];
            if ((q->gv_mean != NULL) != (p->gv_mean != NULL) ||
                (q->gv_vari != NULL) != (p->gv_vari != NULL)) return 0;
            out[s*4+2]=q->gv_length;
            if (!q->gv_mean && q->gv_length) return 0;
        }
    }
    return 1;
}