"""共有ランタイムへのrealpathに必要な祖先metadataのみを限定許可する。"""
import json
from controller import profile as original_profile
from paths import HERE,OLD

def profile(b,work,isolated):
    result=original_profile(b,work,isolated)
    if isolated:
        allowed=set()
        for path in [OLD/'.venv-eval',HERE/'runtime-bundle',work]:
            allowed.update(path.parents)
        result+='(allow file-read-metadata '+''.join('(literal '+json.dumps(str(p))+') ' for p in sorted(allowed))+')\n'
    return result
