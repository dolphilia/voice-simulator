"""研究NNだけの8係数予測。最終bundleへ含めない。"""
from paths import *
import numpy as np

def predictor():
 import torch
 from torch import nn
 m=read(HERE/'models/neural.json');assert digest(HERE/'models/neural.pt')==m['weights_sha256'];net=nn.Sequential(nn.Linear(16,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,8));net.load_state_dict(torch.load(HERE/'models/neural.pt',map_location='cpu',weights_only=True),strict=True);net.eval();torch.set_num_threads(2)
 def predict(x):
  z=(np.asarray(x)-np.array(m['x_mean']))/np.array(m['x_scale'])
  with torch.no_grad():return net(torch.tensor(z,dtype=torch.float32)).numpy()
 return predict
