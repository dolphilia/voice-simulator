"""旧評価の同一hash参照と新資産の排他保存。"""
import importlib.util
from io import BytesIO
import numpy as np
from campaign import *

def load_metrics():
    path=SHORT/'event_metrics.py';sha=read(QRES/'protocol.json')['source_hashes']['event_metrics.py'];assert digest(path)==sha
    spec=importlib.util.spec_from_file_location('sealed_short_event_metrics',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def npz_bytes(**values):
    out=BytesIO();np.savez_compressed(out,**values);return out.getvalue()

def verify_protocol():
    p=read(RESULT/'protocol.json')
    for n,h in p['source_hashes'].items():assert digest(ROOT/n)==h,n
    for n,h in p['input_hashes'].items():assert digest(REPO/n)==h,n
    return p
