"""排他保存する数値資産と凍結契約の照合。"""
from io import BytesIO
import numpy as np
from campaign import *

def npz_bytes(**values):
    buf=BytesIO();np.savez_compressed(buf,**values);return buf.getvalue()

def verify_protocol():
    p=read(RESULT/'protocol.json')
    for n,h in p['source_hashes'].items():assert digest(ROOT/n)==h,(n,'コードが変わりました')
    for n,h in p['input_hashes'].items():assert digest(REPO/n)==h,(n,'参照が変わりました')
    for row in p['rows']:assert digest(REPO/row['truth'])==row['truth_sha256']
    return p
