"""実媒体の所有一時領域で合成台帳を使い、強制と後始末の拒否経路を検証。"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
from unittest.mock import patch

from budget import Budget, LIMITS, encode, read, digest
from long_horizon_budget import LongHorizonBudget, TOTALS, AMENDMENT, CLOSING_SECONDS, VALIDATION_SOURCES


def refused(action, error=RuntimeError):
    try:
        action()
    except error:
        return
    raise AssertionError('拒否すべき処理が通過しました')


def run_tests(directory):
    root = Path(directory) / 'fixture-cycle'; root.mkdir()
    mount = Path(directory) / 'fixture-volume'
    media = mount / 'voice-simulator-data'; media.mkdir(parents=True)
    marker = encode(dict(project='voice-simulator', fixture=True))
    (media / 'identity.json').write_bytes(marker)
    original = Budget(root, {**LIMITS, 'bytes':266776643584,'experiment_bytes':262776643584})
    original.initialize({'fixture': True}, initial_seconds=65558)
    with original.locked():
        s = original._load(False)
        s['counts'] = dict(render=10672,teacher=117,ai=10288,dsp=30327,train=11,inverse=97,download=1669966871)
        s['campaigns'] = {f'old-{i}':dict(closed=True,limits={'seconds':14400},counts={},prefix=f'campaigns/old-{i}',payload_bytes=0) for i in range(28)}
        s['storage_amendment'] = 'fixture'
        original._write_state(s)
    config = dict(mount=str(mount),data_root=str(media),volume_uuid='fixture',
                  marker_sha256=hashlib.sha256(marker).hexdigest(),cycle_directory='fixture-cycle',
                  amendment_id='fixture',internal_experiment_bytes=18000000000,
                  external_experiment_bytes=244776643584,external_closing_bytes=2000000000)
    (original.control/'storage-config.json').write_bytes(encode(config))
    info = plistlib.dumps(dict(VolumeUUID='fixture',WritableVolume=True))
    checks = []
    with patch('storage_guard.subprocess.check_output',return_value=info), patch('storage_guard.os.path.ismount',return_value=True):
        refused(lambda:LongHorizonBudget(root));checks.append('未承認拒否')
        base = read(original.state_path)
        approval = dict(status='approved_pending_implementation',explicit_user_approval='合成fixtureの承認',cycle=base['cycle'],base_state=base)
        (root/'approval.json').write_bytes(encode(approval))
        with original.locked():
            s=original._load(False);s['limits'].update(TOTALS);s['limits'].pop('campaigns')
            s['long_horizon']=dict(id=AMENDMENT,status='applied',approval_path='approval.json',approval_sha256=digest(root/'approval.json'),
                                  scientific_completed=0,last_review=dict(seconds=s['seconds'],scientific_completed=0))
            original._write_state(s)
        b=LongHorizonBudget(root);b.resume()
        assert b.snapshot()['counts']==base['counts'] and b.snapshot()['campaigns']==base['campaigns']
        checks.append('旧28契約・全消費継承')
        limits=dict(seconds=3600,bytes=20000000,write_bytes=60000000,render=10,teacher=2,ai=10,dsp=10,train=2,inverse=2,download=100,setup=20,audit=30)
        refused(lambda:b.start_campaign('unverified','campaigns/unverified',limits,'fixture'));checks.append('検証前科学拒否')
        source_root=Path(__file__).resolve().parent
        for name in VALIDATION_SOURCES:
            b.write(root/name,(source_root/name).read_bytes())
        b.save(root/'validation.json',dict(passed=True,validated_sources={n:digest(root/n) for n in VALIDATION_SOURCES}))
        with b.locked():
            s=b._load();s['long_horizon'].update(validation_path='validation.json',validation_sha256=digest(root/'validation.json'));b._write_state(s)
        for key, amount in [('seconds',28801),('bytes',4000000001),('render',6001),('dsp',30001)]:
            refused(lambda key=key,amount=amount:b.start_campaign('oversize','campaigns/oversize',{**limits,key:amount},'fixture',expansion_reason='上限の拒否fixture'))
        refused(lambda:b.start_campaign('reason','campaigns/reason',{**limits,'render':3001},'fixture'))
        checks.append('個別上限・拡張理由強制')
        baseline=b.snapshot()
        for key,total in TOTALS.items():
            near=json.loads(json.dumps(baseline))
            if key in ('seconds','write_bytes'):
                near[key]=total-limits[key]+1
            else:
                near['counts'][key]=total-limits[key]+1
            with patch.object(b,'_load',return_value=near):
                refused(lambda:b.start_campaign('total','campaigns/total',limits,'fixture'))
        checks.append('全累計資源予約超過拒否')
        b.start_campaign('new','campaigns/new',limits,'fixture')
        assert len(b.snapshot()['campaigns'])==29
        checks.append('件数停止撤廃・記録継続')
        refused(lambda:b.reserve('new','render','回数超過',count=11))
        refused(lambda:b.reserve('new','render','個別時間',expected_seconds=3600))
        refused(lambda:b.reserve('new','render','保存超過',reserve_bytes=20000000))
        with patch('long_horizon_budget.shutil.disk_usage',return_value=type('Usage',(),{'free':19999999999})()):
            refused(lambda:b.reserve('new','render','内蔵不足'))
        actual_usage=__import__('shutil').disk_usage
        with patch('long_horizon_budget.shutil.disk_usage',side_effect=lambda p:type('Usage',(),{'free':1999999999})() if Path(p)==mount else actual_usage(p)):
            refused(lambda:b.reserve('new','render','外部不足'))
        checks.append('秒・回数・容量・内蔵外部実空き拒否')
        before=b.snapshot()['counts']['render'];write_before=b.snapshot()['write_bytes']
        for i in range(3):
            try:
                with b.job('new','render','技術失敗',reserve_bytes=3000000) as job:
                    with b.workspace(job,'失敗後回収fixture',maximum_bytes=100000,maximum_write_bytes=200000) as (path,env):
                        assert all(env[k]==str(path) for k in ('TMPDIR','TMP','TEMP','HF_HOME','MPLCONFIGDIR'))
                        (path/'small').write_bytes(b'fixture')
                        raise RuntimeError('意図した技術失敗')
            except RuntimeError as e:
                assert str(e)=='意図した技術失敗'
        refused(lambda:b.reserve('new','render','技術失敗',reserve_bytes=3000000))
        s=b.snapshot();assert s['counts']['render']==before+3 and s['write_bytes']>write_before and not s['jobs']
        assert all(v['absence_verified'] and not os.path.lexists(v['path']) for v in s['temporary_work'].values())
        checks.append('失敗attempt計数・2再試行・環境設定・finally回収・無返金')
        with b.job('new','render','正常外部出力',reserve_bytes=3000000) as job:
            with b.workspace(job,'正常終了fixture',maximum_bytes=100000,maximum_write_bytes=200000) as (path,env):
                (path/'small').write_bytes(b'success')
                b.write(root/'campaigns/new/test.wav',b'fixture-audio',job)
        assert (root/'campaigns/new/test.wav').is_symlink() and b.audit_data_hashes()==1
        checks.append('外部振分・位置・hash・正常回収')
        try:
            with b.job('new','audit','一時超過',reserve_bytes=3000000) as job:
                with b.workspace(job,'一時上限fixture',maximum_bytes=2,maximum_write_bytes=2) as (path,env):
                    (path/'over').write_bytes(b'123')
        except RuntimeError as e:
            assert '一時領域の予約超過' in str(e)
        else: raise AssertionError('一時超過を見逃しました')
        assert not os.path.lexists(path) and not b.snapshot()['jobs']
        checks.append('一時超過記録・失敗後不存在')
        with b.locked():
            s=b._load();s['counts']['render']=TOTALS['render'];b._write_state(s)
        refused(lambda:b.reserve('new','render','包括回数上限'))
        checks.append('残資源を換算しない')
        b.close_campaign('new');refused(lambda:b.close_campaign('new'))
        with b.locked():
            s=b._load();s['seconds']=TOTALS['seconds']-CLOSING_SECONDS;s['session']['checkpoint']=__import__('time').time();b._write_state(s)
        refused(lambda:b.start_campaign('late','campaigns/late',limits,'fixture'))
        close={**limits,**{k:0 for k in ('render','teacher','ai','dsp','train','inverse','download')}}
        b.start_campaign('close','campaigns/close',close,'fixture',purpose='closeout')
        with b.job('close','audit','終了専用監査',reserve_bytes=1000000):pass
        b.close_campaign('close');b.reconcile();b.suspend()
        checks.append('最後12時間の科学拒否・終了監査許可・二重終了拒否')
    return dict(passed=True,checks=checks,fixture_only=True,quality_evidence=False,
                temporary_directory=str(directory),no_P5_text_read=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--owned-directory',required=True)
    args=parser.parse_args();print(json.dumps(run_tests(args.owned_directory),ensure_ascii=False))
