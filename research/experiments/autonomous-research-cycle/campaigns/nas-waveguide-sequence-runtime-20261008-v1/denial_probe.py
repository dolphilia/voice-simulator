"""禁止された実データ読取りとネットワーク接続が権限で拒否されるかを確認。"""
import sys,json,socket,errno
rows=[]
for path in json.loads(sys.stdin.read()):
 try:
  with open(path,'rb') as f:f.read(1)
 except PermissionError as e:rows.append(dict(path=path,denied=True,error=type(e).__name__))
 except OSError as e:rows.append(dict(path=path,denied=False,error=type(e).__name__))
 else:rows.append(dict(path=path,denied=False,error=None))
s=socket.socket();s.settimeout(2.)
try:s.connect(('1.1.1.1',80))
except OSError as e:network=e.errno in (errno.EPERM,errno.EACCES)
else:network=False
finally:s.close()
print(json.dumps(dict(files=rows,network_denied=network,all_denied=all(r['denied'] for r in rows) and network)))
