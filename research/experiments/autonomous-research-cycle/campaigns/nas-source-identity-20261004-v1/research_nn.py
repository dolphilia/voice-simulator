from paths import *
import numpy as np

def prediction():
 import torch
 from torch import nn
 model=read(SRES/'models/neural.json');assert digest(SRES/'models/neural.pt')==model['weights_sha256']
 net=nn.Sequential(nn.Linear(16,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,1))
 net.load_state_dict(torch.load(SRES/'models/neural.pt',map_location='cpu',weights_only=True));net.eval();torch.set_num_threads(2)
 def predict(x):
  z=(np.asarray(x)-np.asarray(model['x_mean']))/np.asarray(model['x_scale'])
  with torch.no_grad():return net(torch.tensor(z,dtype=torch.float32)).flatten().numpy()
 return predict
