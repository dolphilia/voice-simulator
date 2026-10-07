"""旧契約を保持し、初回順序修復版だけを新入口として封印する。"""
from paths import *
import ast
def main():
    b=Budget();b.recover()
    old=read(HERE/'execution-contract.json')
    assert all(digest(HERE/n)==h for n,h in old['source_hashes'].items())
    assert digest(HERE/'protocol.json')==old['protocol_sha256'] and digest(HERE/'registration.json')==old['registration_sha256']
    with b.job(NAME,'setup','初回順序修復版の共有bundleと実行契約を固定',reserve_bytes=150000) as job:
        bundle=HERE/'runtime-bundle';manifest=read(bundle/'manifest.json')
        for name in ['runtime_v2.py','runtime_batch_v2.py','postfilter_v2.py','postfilter_v2.c','postfilter_v2.dylib']:
            b.write(bundle/name,(HERE/name).read_bytes(),job);manifest['files'][name]=digest(bundle/name)
        manifest.update(initial_native_MCP_preserved=True,previous_manifest_sha256=digest(bundle/'manifest.json'),scientific_MCP_formula_unchanged=True)
        b.save(bundle/'manifest-v2.json',manifest,job)
        sources={p.name:digest(p) for p in HERE.glob('*.py')}
        for name in sources:ast.parse((HERE/name).read_text())
        contract=dict(old);contract.update(source_hashes=sources,runtime_manifest_sha256=digest(bundle/'manifest-v2.json'),previous_execution_contract_sha256=digest(HERE/'execution-contract.json'),initialization='β付きHTS一次実装と同じnative初回MCPで初期フィルタだけを設定。全frameは共有変換MCPをβ0で生成。',MCP_formula_beta_inputs_thresholds_unchanged=True,unknown_comparison_rendered_before_repair=0,C_sources={'postfilter_v2.c':digest(HERE/'postfilter_v2.c'),'vendor/HTS_vocoder.c':digest(HERE/'vendor/HTS_vocoder.c')})
        b.save(HERE/'execution-contract-v2.json',contract,job)
        b.save(HERE/'activation-audit-v2.json',dict(previous_contract_sha256=digest(HERE/'execution-contract.json'),new_contract_sha256=digest(HERE/'execution-contract-v2.json'),source_primary_verified=True,new_unknown_waveforms=0,old_artifacts_preserved=True,technical_retry_not_scientific_tuning=True),job)
    with b.locked():
        state=b._load();state['write_bytes']+=(REPO/'.gitignore').stat().st_size
        b.event(state,dict(event='repository-management-write',path='.gitignore',sha256=digest(REPO/'.gitignore'),purpose='当該MCP実験の外部詳細JSON三ファイルだけを明示除外'))
        state.setdefault('continuation_checkpoint_history',[]).append(state['continuation_checkpoint']);state['continuation_checkpoint']=dict(id='mcp-postfilter-ready-v2-20261008-0001',active_campaign=NAME,campaign_closed=False,execution_contract_sha256=digest(HERE/'execution-contract-v2.json'),next='preflight_v2.py static/compat → controller_v2.py comparison/isolate/asr → summarize_v2.py → closeout_v2.py',quality_goal_completed=False,protected_confirmation_opened=False,git_save_pending=True);b._write_state(state)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
