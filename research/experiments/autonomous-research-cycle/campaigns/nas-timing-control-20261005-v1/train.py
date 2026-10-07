"""同じ80文の時間配分目標を、直接回帰・研究NN・同サイズ学生へ移す。"""
from paths import *
from timing_control import FEATURES,projected,LOWER,UPPER,LOGBOUND
import io,numpy as np
def mse(v,y,w):return float(np.sum(w*(projected(v)-y)**2)/np.sum(w))
def main():
 b=Budget();m=read(HERE/'target-manifest.json');assert m['fit_supported'] and read(HERE/'self-test.json')['passed'] and not (HERE/'render-manifest.json').exists()
 x=[];y=[];groups=[];used=[]
 for r in m['rows']:
  assert r['status']=='accepted';g=len(used)
  for q in r['targets']:x.append(q['x']);y.append(q['target_log_ratio']);groups.append(g)
  used.append(dict(id=r['id'],text=r['text'],length=r['length'],target_sha256=digest(HERE/'targets'/(r['id']+'.json')),phone_intervals=len(r['targets']),all_target_labels=[q['label_index'] for q in r['targets']]))
 x,y,groups=np.array(x,float),np.array(y,float),np.array(groups);N=len(used);d=len(FEATURES);assert N==80 and d==58 and x.shape==(len(y),d) and np.isfinite(x).all() and np.isfinite(y).all()
 mean=x.mean(0);scale=x.std(0);scale[scale<1e-6]=1.;mean[0]=0.;scale[0]=1.;z=(x-mean)/scale;w=np.array([1./sum(groups==g) for g in groups]);lam=10.*N/17
 normal=dict(features=FEATURES,x_mean=mean.tolist(),x_scale=scale.tolist(),duration_ratio_bounds=[LOWER,UPPER])
 import torch
 from torch import nn
 torch.set_num_threads(2);torch.set_num_interop_threads(1);torch.manual_seed(20261005)
 with b.job(NAME,'setup','同資料3fit・入力58・scalar時計・複雑さを固定',reserve_bytes=600000) as j:
  b.save(HERE/'training-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),target_manifest_sha256=digest(HERE/'target-manifest.json'),source_sha256=digest(HERE/'train.py'),target_source_sha256=digest(HERE/'targets.py'),used=used,training_utterances=N,original_training_denominator=96,training_phone_intervals=len(y),x_shape=list(x.shape),y_shape=list(y.shape),feature_rank=int(np.linalg.matrix_rank(z)),normalization=normal,ridge_lambda=lam,average_objective_penalty=10./17,planned_fits=3,seed=20261005,steps=500,NN_architecture=[d,16,16,1],NN_activations=['tanh','tanh','linear'],optimizer={'type':'Adam','lr':.005,'weight_decay':.001},per_utterance_weight_equal=True,teacher_time_is_prediction_not_acoustic_GT=True,final_coefficients_each=d,final_normalization_values_each=2*d,quality_certified=False),j)
 with b.job(NAME,'train','同58→1直接時間回帰',reserve_bytes=200000) as j:
  direct=np.linalg.solve(z.T@(w[:,None]*z)+lam*np.eye(d),z.T@(w*y));b.save(HERE/'models/direct.json',dict(normal,type='timing-ridge',coefficients=direct.tolist(),lambda_value=lam,training_contract_sha256=digest(HERE/'training-contract.json'),runtime_neural=False),j)
 net=nn.Sequential(nn.Linear(d,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,1));tx=torch.tensor(z,dtype=torch.float32);ty=torch.tensor(y,dtype=torch.float32);tw=torch.tensor(w/N,dtype=torch.float32);losses=[]
 def projected_torch(v):return torch.clamp(v,-float(LOGBOUND),float(LOGBOUND))
 with b.job(NAME,'train','研究NN scalar時計500step',reserve_bytes=200000) as j:
  opt=torch.optim.Adam(net.parameters(),lr=.005,weight_decay=.001)
  for step in range(500):
   opt.zero_grad();pred=projected_torch(net(tx).squeeze(1));loss=torch.sum(tw*(pred-ty)**2);assert torch.isfinite(loss);loss.backward();opt.step()
   if step in [0,99,249,499]:losses.append(dict(step=step+1,weighted_projected_MSE=float(loss.detach())))
  net.eval();out=io.BytesIO();torch.save(net.state_dict(),out);b.write(HERE/'models/neural.pt',out.getvalue(),j);b.save(HERE/'models/neural.json',dict(normal,type='timing-neural',width=16,layers=2,weights_sha256=digest(HERE/'models/neural.pt'),training_contract_sha256=digest(HERE/'training-contract.json'),runtime_neural=True,research_only=True),j)
 with torch.no_grad():raw=net(tx).squeeze(1).numpy();student_target=projected(raw)
 with b.job(NAME,'train','同58→1学生へ時計を蒸留',reserve_bytes=200000) as j:
  student=np.linalg.solve(z.T@(w[:,None]*z)+lam*np.eye(d),z.T@(w*student_target));b.save(HERE/'models/student.json',dict(normal,type='timing-ridge',coefficients=student.tolist(),lambda_value=lam,teacher_model_sha256=digest(HERE/'models/neural.pt'),training_contract_sha256=digest(HERE/'training-contract.json'),runtime_neural=False),j)
 with b.job(NAME,'audit','未知波形前のモデル固定、訓練lossを別記録',reserve_bytes=100000) as j:
  errors={k:mse(v,y,w) for k,v in [('native',np.zeros_like(y)),('direct',z@direct),('neural',raw),('student',z@student)]};b.save(HERE/'model-comparison.json',dict(training_projected_MSE=errors,NN_losses=losses,model_hashes={q.name:digest(q) for q in (HERE/'models').iterdir()},all_models_fixed_before_wave=True,training_loss_not_waveform_quality=True,quality_certified=False),j)
 print('時間model固定',errors,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
