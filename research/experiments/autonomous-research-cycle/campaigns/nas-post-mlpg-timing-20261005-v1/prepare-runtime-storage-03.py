"""凍結済み合成関数を保ち、外部出力と隔離だけを追補する。"""
import json
import sys
from pathlib import Path
from paths import *
from storage_budget import StorageBudget
from budget import ROOT, read, digest, encode
HERE=ROOT/'campaigns/nas-post-mlpg-timing-20261005-v1'
NAME='post-mlpg-timing-v1'

def main():
    b=StorageBudget()
    original=(HERE/'runtime-core.py').read_text()
    code=original.replace('from acoustics import evaluate',
                          'from acoustics import evaluate\nfrom storage_output import open_output')
    code=code.replace('a.output.write_bytes(data);print(json.dumps(meta))',
                      "with open_output(a.output) as output:output.write(data)\n print(json.dumps(meta))")
    code=code.replace(';with open_output', '\n with open_output')
    assert original.split('def generate(')[1].split('def main():')[0]==code.split('def generate(')[1].split('def main():')[0]
    batch=(HERE/'runtime-batch.py').read_text().replace('from runtime import generate,verify',
                       'from runtime import generate,verify\nfrom storage_output import open_output')
    batch=batch.replace("with a.output.open('wb') as output", 'with open_output(a.output) as output')
    controller=(HERE/'isolate.py').read_text()
    controller=controller.replace('from paths import *','from paths import *\nfrom storage_budget import StorageBudget\nBudget=StorageBudget')
    controller=controller.replace("bundle=HERE/'runtime-bundle'","bundle=HERE/'runtime-storage-bundle'")
    controller=controller.replace("HERE/'runtime-core.py'","HERE/'runtime-storage.py'")
    controller=controller.replace("HERE/'runtime-batch.py'","HERE/'runtime-storage-batch.py'")
    controller=controller.replace("  mapping.update({n+'.json'", 
        "  mapping.update({n:HERE/n for n in ['storage_output.py','storage-output-config.json']});mapping['storage_guard.py']=ROOT/'storage_guard.py'\n  mapping.update({n+'.json'")
    controller=controller.replace("put(b,HERE/'isolation.sb',profile.encode(),j)",
        "profile+='(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\\n(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\\n';put(b,HERE/'isolation-storage.sb',profile.encode(),j)")
    # 全参照を新しい隔離プロファイルへ統一する。
    controller=controller.replace("'isolation.sb'","'isolation-storage.sb'")
    controller=controller.replace(" assert all(q.exists() for q in blocked)",
        " blocked.append(Path(next(v['physical'] for n,v in b.locations().items() if n.endswith('.wav'))));blocked[-1]=b.guard.root/blocked[-1]\n assert all(q.exists() for q in blocked)")
    controller=controller.replace("[str(q.relative_to(REPO)) for q in blocked]",
                                  "[str(q.relative_to(REPO)) if REPO in q.parents else str(q) for q in blocked]")
    preflight=(HERE/'preflight.py').read_text()
    preflight=preflight.replace('from paths import *','from paths import *\nfrom storage_budget import StorageBudget\nBudget=StorageBudget')
    preflight=preflight.replace("bundle=HERE/'runtime-bundle'","bundle=HERE/'runtime-storage-bundle'")
    preflight=preflight.replace("'isolation.sb'","'isolation-storage.sb'")
    preflight=preflight.replace("('preflight-'+mode+'.zip')","('preflight-storage-'+mode+'.zip')")
    preflight=preflight.replace("'runtime-preflight-requests.json'","'runtime-preflight-storage-requests.json'")
    preflight=preflight.replace("'runtime-preflight.json'","'runtime-preflight-storage.json'")
    helper=json.loads((HERE/'storage-output-helper-source.json').read_text())['source']
    sources={'runtime-storage.py':code,'runtime-storage-batch.py':batch,
             'isolate-storage.py':controller,'preflight-storage.py':preflight,'storage_output.py':helper}
    for name,source in sources.items():compile(source,name,'exec')
    with b.job(NAME,'setup','合成関数不変の外部出力追補を固定',reserve_bytes=200000) as j:
        for name,source in sources.items():b.write(HERE/name,source.encode(),j)
        b.save(HERE/'storage-output-config.json',dict(b.storage,device=b.guard.device),j)
        b.save(HERE/'runtime-storage-amendment-01.json',
               dict(original_execution_contract_sha256=digest(HERE/'execution-contract.json'),
                    original_runtime_core_sha256=digest(HERE/'runtime-core.py'),
                    synthesis_generate_function_byte_unchanged=True,
                    sources={n:digest(HERE/n) for n in sources},
                    physical_external_data_read_denied=True,output_only_media_checks=True,
                    no_neural_teacher_wave_or_lookup_added=True,quality_certified=False),j)

if __name__=='__main__':main()
