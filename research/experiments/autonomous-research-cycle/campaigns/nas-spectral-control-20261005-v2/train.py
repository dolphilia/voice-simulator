"""同じ17文209区間の8係数目標を、直接回帰・研究NN・同サイズ学生へ移す。"""
from paths import *
import io,numpy as np
from local_control import FEATURES
from targets import projection

def mse(v,y,w):return float(np.sum(w[:,None]*(projection(v)-y)**2)/np.sum(w)/8)
def main():
 b=Budget();m=read(HERE/'target-manifest.json');assert m['fit_supported'] and not (HERE/'render-manifest.json').exists();assert (HERE/'protocol.json').exists();x=[];y=[];groups=[];used=[]
 for r in m['rows']:
  if r['status']!='accepted':continue
  g=len(used)
  for q in r['targets']:x.append(q['x']);y.append(q['target_coefficients']);groups.append(g)
  used.append(dict(id=r['id'],text=r['text'],length=r['length'],target_sha256=digest(HERE/'targets'/(r['id']+'.json')),phone_intervals=len(r['targets']),all_target_labels=[q['label_index'] for q in r['targets']]))
 x,y,groups=np.array(x,float),np.array(y,float),np.array(groups);assert x.shape==(209,16) and y.shape==(209,8) and len(used)==17 and np.isfinite(x).all() and np.isfinite(y).all();mean=x.mean(0);scale=x.std(0);scale[scale<1e-6]=1.;mean[0]=0.;scale[0]=1.;z=(x-mean)/scale;w=np.array([1./sum(groups==g) for g in groups]);normal=dict(features=FEATURES,x_mean=mean.tolist(),x_scale=scale.tolist(),output_coefficients=list(range(1,9)),L1_bound=.5)
 import torch
 from torch import nn
 torch.set_num_threads(2);torch.set_num_interop_threads(1);torch.manual_seed(20261005)
 with b.job(NAME,'setup','3fit・対象区間・重み・複雑さ・訓練seedを固定',reserve_bytes=300000) as j:
  b.save(HERE/'training-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),target_manifest_sha256=digest(HERE/'target-manifest.json'),source_sha256=digest(HERE/'train.py'),target_source_sha256=digest(HERE/'targets.py'),used=used,training_utterances=17,training_phone_intervals=209,x_shape=list(x.shape),y_shape=list(y.shape),feature_rank=int(np.linalg.matrix_rank(z)),normalization=normal,ridge_lambda=10.,planned_fits=3,seed=20261005,steps=500,NN_architecture=[16,16,16,8],NN_activations=['tanh','tanh','linear'],optimizer={'type':'Adam','lr':.005,'weight_decay':.001},per_utterance_weight_equal=True,source_time_is_prediction_not_acoustic_GT=True,quality_certified=False),j)
 with b.job(NAME,'train','直接16×8共有回帰fit',reserve_bytes=200000) as j:
  direct=np.linalg.solve(z.T@(w[:,None]*z)+10.*np.eye(16),z.T@(w[:,None]*y));b.save(HERE/'models/direct_non_neural.json',dict(normal,type='spectral-ridge',coefficients=direct.tolist(),lambda_value=10.,training_contract_sha256=digest(HERE/'training-contract.json'),runtime_neural=False),j)
 net=nn.Sequential(nn.Linear(16,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,8));tx=torch.tensor(z,dtype=torch.float32);ty=torch.tensor(y,dtype=torch.float32);tw=torch.tensor(w[:,None]/17/8,dtype=torch.float32);losses=[]
 def projected(v):return v*torch.clamp(.5/torch.clamp(v.abs().sum(1,keepdim=True),min=1e-12),max=1.)
 with b.job(NAME,'train','研究NNの8係数共有残差500step fit',reserve_bytes=200000) as j:
  opt=torch.optim.Adam(net.parameters(),lr=.005,weight_decay=.001)
  for step in range(500):
   opt.zero_grad();pred=projected(net(tx));loss=torch.sum(tw*(pred-ty)**2);assert torch.isfinite(loss);loss.backward();opt.step()
   if step in [0,99,249,499]:losses.append(dict(step=step+1,weighted_projected_MSE=float(loss.detach())))
  net.eval();out=io.BytesIO();torch.save(net.state_dict(),out);b.write(HERE/'models/neural.pt',out.getvalue(),j);b.save(HERE/'models/neural.json',dict(normal,type='spectral-neural',width=16,layers=2,weights_sha256=digest(HERE/'models/neural.pt'),training_contract_sha256=digest(HERE/'training-contract.json'),runtime_neural=True,research_only=True),j)
 with torch.no_grad():nn_raw=net(tx).numpy();student_target=projection(nn_raw)
 with b.job(NAME,'train','同じ16×8共有回帰へNN出力を蒸留fit',reserve_bytes=200000) as j:
  student=np.linalg.solve(z.T@(w[:,None]*z)+10.*np.eye(16),z.T@(w[:,None]*student_target));b.save(HERE/'models/distilled_non_neural.json',dict(normal,type='spectral-ridge',coefficients=student.tolist(),lambda_value=10.,teacher_model_sha256=digest(HERE/'models/neural.pt'),training_contract_sha256=digest(HERE/'training-contract.json'),runtime_neural=False),j)
 with b.job(NAME,'audit','3モデルを未知wave生成前固定・訓練lossを別記録',reserve_bytes=100000) as j:
  errors={k:mse(v,y,w) for k,v in [('native',np.zeros_like(y)),('direct_non_neural',z@direct),('neural',nn_raw),('distilled_non_neural',z@student)]};b.save(HERE/'model-comparison.json',dict(training_projected_MSE=errors,NN_losses=losses,model_hashes={p.name:digest(p) for p in (HERE/'models').iterdir()},all_models_fixed_before_wave=True,training_loss_not_waveform_quality=True,quality_certified=False),j)
 print('models fixed',errors,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
