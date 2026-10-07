"""固定教師の重みを未知文生成前に検証する。音声生成は行わない。"""
from paths import *
def main():
 b=Budget()
 with b.job(NAME,'setup','JVNV/日本語BERTの固定CPU読込・推論重み照合',reserve_bytes=200000) as j:
  from jvnv_loader2 import load
  model,audit=load()
  b.save(HERE/'teacher-load-audit.json',audit,j)
 print({'teacher_weights_exact':True,'audio_generated':0},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
