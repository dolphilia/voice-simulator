"""16入力のうち共有韻律4変数だけを使う非ニューラル予測。"""
import numpy as np
INDEX=[10,11,12,13]
FEATURES=['high','mora_position','phrase_position','after_accent']
def predict(model,x):
 if model['type']!='prosody-ridge' or model['features']!=FEATURES:raise ValueError('固定4特徴モデル')
 a=np.asarray(x,dtype=float)
 if a.ndim!=2 or a.shape[1]!=16 or not np.isfinite(a).all():raise ValueError('有限の16入力行列')
 return ((a[:,INDEX]-model['x_mean'])/model['x_scale'])@np.asarray(model['coefficients'])
def tests():
 m={'type':'prosody-ridge','features':FEATURES,'x_mean':[0.]*4,'x_scale':[1.]*4,'coefficients':[1.,2.,3.,4.]}
 a=np.arange(32.).reshape(2,16);v=predict(m,a);a[:,:10]+=999;a[:,14:]-=999
 assert np.array_equal(v,predict(m,a))
 for x in [np.full((2,16),float('nan')),np.zeros((2,15))]:
  try:predict(m,x)
  except ValueError:pass
  else:raise AssertionError('不正入力拒否')
 return {'phone_and_adjacent_features_invariant':True,'invalid_shape_nonfinite_rejected':True,'actual_coefficients':4,'quality_certified':False}
