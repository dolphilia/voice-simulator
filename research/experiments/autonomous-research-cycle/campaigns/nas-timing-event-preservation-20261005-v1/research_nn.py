"""研究NN scalar時間予測だけの入口。最終bundleには含めない。"""
from paths import *
from timing_control import FEATURES,projected
import numpy as np
def predictor():
 import torch
 from torch import nn
 m=read(HERE/'models/neural.json');assert m['features']==FEATURES and digest(HERE/'models/neural.pt')==m['weights_sha256'];d=len(FEATURES);net=nn.Sequential(nn.Linear(d,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,1));net.load_state_dict(torch.load(HERE/'models/neural.pt',map_location='cpu',weights_only=True),strict=True);net.eval();torch.set_num_threads(2)
 def predict(x):
  z=(np.asarray(x)-np.array(m['x_mean']))/np.array(m['x_scale'])
  with torch.no_grad():return projected(net(torch.tensor(z,dtype=torch.float32)).squeeze(1).numpy())
 return predict
