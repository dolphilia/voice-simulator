"""版固定の研究用JVNV教師を専用CPU依存で読み、推論重みを照合する。"""
from paths import *
import os,sys
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',NUMBA_DISABLE_JIT='1',HF_HOME=str(JP/'hf-home'),HF_HUB_CACHE=str(JP/'hf-home/hub'),TRANSFORMERS_CACHE=str(JP/'hf-home/hub'),USE_TORCH='1',USE_TF='0',OMP_NUM_THREADS='2',VECLIB_MAXIMUM_THREADS='2')
sys.path[:0]=[str(JP/'packages'),str(JP/'source'),str(WORLD/'packages-v2')]
import numpy as np,torch
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
from style_bert_vits2.constants import Languages
from style_bert_vits2.nlp import bert_models
from style_bert_vits2.tts_model import TTSModel
from style_bert_vits2.logging import logger
from safetensors import safe_open
logger.remove()
def equal_checkpoint(model,path,allow_training_prefix=None):
 state=model.state_dict();buffers=dict(model.named_buffers())
 if "deberta.embeddings.position_ids" in buffers:state["deberta.embeddings.position_ids"]=buffers["deberta.embeddings.position_ids"]
 matched=[];missing=[];extra=[];changed=[]
 with safe_open(str(path),framework='pt',device='cpu') as f:
  keys=set(f.keys());checkpoint_keys=keys-{'iteration'}
  for k in checkpoint_keys:
   if k not in state:missing.append(k);continue
   x=f.get_tensor(k)
   if not torch.equal(state[k],x.to(dtype=state[k].dtype)):changed.append(k)
   matched.append(k)
  for k in set(state)-checkpoint_keys:
   if allow_training_prefix and k.startswith(allow_training_prefix):continue
   # safetensorは共有weightの重複keyを省略する。実storage aliasだけを認める。
   aliases=[n for n in matched if state[n].untyped_storage().data_ptr()==state[k].untyped_storage().data_ptr() and state[n].shape==state[k].shape]
   if not aliases:extra.append(k)
 assert not missing and not changed and not extra,{'missing':missing,'changed':changed,'unmapped_extra':extra}
 return {'matched_checkpoint_tensors':len(matched),'training_only_unstored':[k for k in set(state)-checkpoint_keys if allow_training_prefix and k.startswith(allow_training_prefix)],'all_inference_weights_exactly_loaded':True,'nonpersistent_position_ids_buffer_checked':"deberta.embeddings.position_ids" in state}
def load():
 assert torch.__version__.split('+')[0]=='2.3.1' and np.__version__=='1.26.4'
 bert=bert_models.load_model(Languages.JP,str(JP/'models/bert'),device_map=None)
 bert.eval()
 tokenizer=bert_models.load_tokenizer(Languages.JP,str(JP/'models/bert'))
 directory=JP/'models/teacher/jvnv-F1-jp'
 model=TTSModel(directory/'jvnv-F1-jp_e160_s14000.safetensors',directory/'config.json',directory/'style_vectors.npy',device='cpu')
 model.load()
 audits={'BERT':equal_checkpoint(bert,JP/'models/bert/model.safetensors'),'JVNV':equal_checkpoint(model.net_g,directory/'jvnv-F1-jp_e160_s14000.safetensors','enc_q')}
 return model,{'weights':audits,'torch_version':torch.__version__,'numpy_version':np.__version__,'teacher_code_commit':read(JP/'source-tag.json')['commit'],'BERT_tokenizer_class':type(tokenizer).__name__,'numba_disabled_training_JIT':True,'CPU_only':True,'shared_final_control_trained':False,'teacher_audio_generated':0}
