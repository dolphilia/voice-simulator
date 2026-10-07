"""OS隔離の拒否動作を検査する。秘密情報や内容は読み出さない。"""
import json
from pathlib import Path
import socket
import sys

checks={}
for index,path in enumerate(sys.argv[1:]):
    try:
        with Path(path).open("rb") as f:f.read(1)
        checks[f"forbidden_file_{index}"]=False
    except PermissionError:checks[f"forbidden_file_{index}"]=True
    except Exception as exc:checks[f"forbidden_file_{index}"]={"inconclusive":type(exc).__name__}
try:
    sock=socket.socket();sock.settimeout(1);sock.connect(("127.0.0.1",9))
    checks["network_denied"]=False
except PermissionError:checks["network_denied"]=True
except Exception as exc:checks["network_denied"]={"inconclusive":type(exc).__name__}
finally:
    try:sock.close()
    except NameError:pass
print(json.dumps(checks))
