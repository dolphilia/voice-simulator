"""保存済み全6コホートを事後整理し、旧ゲート・原費用・採否を保持する。"""
from pathlib import Path
import sys,ast,math,re
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(ROOT)]
from paths import *
from collections import Counter
COHORTS=['nas-absolute-f0-20261008-v1','nas-voicing-ap-20261008-v1','nas-vocoder-f0-20261008-v1',
         'nas-mcp-postfilter-20261008-v1','nas-gv-ablation-20261008-v1','nas-gv-ap-interaction-20261008-v1']
def edits(reference,hypothesis):
    n,m=len(reference),len(hypothesis);d=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n+1):d[i][0]=i
    for j in range(m+1):d[0][j]=j
    for i in range(1,n+1):
        for j in range(1,m+1):d[i][j]=min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(reference[i-1]!=hypothesis[j-1]))
    i,j=n,m;ops=[]
    while i or j:
        if i and j and reference[i-1]==hypothesis[j-1] and d[i][j]==d[i-1][j-1]:i-=1;j-=1
        elif i and j and d[i][j]==d[i-1][j-1]+1:ops.append(dict(kind='substitution',reference_index=i-1,reference=reference[i-1],hypothesis=hypothesis[j-1]));i-=1;j-=1
        elif i and d[i][j]==d[i-1][j]+1:ops.append(dict(kind='deletion',reference_index=i-1,reference=reference[i-1],hypothesis=''));i-=1
        else:assert j and d[i][j]==d[i][j-1]+1;ops.append(dict(kind='insertion',reference_index=i,reference='',hypothesis=hypothesis[j-1]));j-=1
    assert len(ops)==d[n][m]
    return d[n][m],list(reversed(ops))
def grouped(pairs):
    groups={}
    for condition in ['both','neutral','higher']:
        for group in ['all','short','long']+['group'+str(i) for i in range(8)]:
            chosen=[r for r in pairs if (condition=='both' or r['condition']==condition)
                and (group=='all' or r['length']==group or (group.startswith('group') and r['challenge_group']==int(group[5:])))]
            assert chosen;errors=sum(r['errors'] for r in chosen);native=sum(r['native_errors'] for r in chosen);chars=sum(r['characters'] for r in chosen)
            groups[condition+'/'+group]=dict(expected=len(chosen),missing=0,errors=errors,native_errors=native,
                characters=chars,non_worsening=chars>0 and errors<=native)
    assert len(groups)==33
    return groups
def verify():
    c=read(HERE/'execution-contract.json')
    for n,h in c['source_hashes'].items():assert digest(HERE/n)==h,n
    assert digest(HERE/'registration.json')==c['registration_sha256']
    for n,h in c['input_seal_hashes'].items():assert digest(REPO/n)==h,n
def main():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    fixture=dict(equal=edits('アイ','アイ')[0]==0,substitution=edits('アイ','アウ')[0]==1,
        insertion=edits('カ','カン')[0]==1,deletion=edits('カン','カ')[0]==1,empty=edits('','')[0]==0)
    assert all(fixture.values())
    all_details=[];all_aggregates={};lines=['# 既存6コホートの不採択理由整理','',
        '全方式を保持し、各比較内のnativeと照合した。コホート間の総率をpoolして優劣を推定しない。事後の記述診断で、旧ゲート・採否・知覚資格は変更していない。','',
        '|コホート/方式|件数|ピッチ通過|支持通過|支持欠測区間|Whisper誤り|Reazon誤り|悪化群W/R|','|---|---:|---:|---:|---:|---:|---:|---|']
    with b.job(NAME,'audit','全992既存波形記録・全1984ASR個票のhashと固定33群の再集計',reserve_bytes=60_000_000) as job:
        for folder in COHORTS:
            base=ROOT/'campaigns'/folder;p=read(base/'protocol.json');seal=read(base/'artifact-seal.json')['files']
            compact=base/'aggregate-summary.json';summary=read(compact if compact.exists() else base/'summary.json')
            def sealed(path):
                key=str(path.relative_to(REPO));assert key in seal and digest(path)==seal[key],key
            sealed(base/'protocol.json')
            methods={}
            for method in p['variants']:
                reasons=Counter();local_missing=Counter();source_known=Counter();content={};cases=[];support_pass=0
                for row in p['rows']:
                    for condition,q in p['conditions'].items():
                        path=base/'render'/row['id']/condition/(method+'.json');sealed(path);v=read(path);sealed(REPO/v['wav'])
                        pitch=v['pitch_gate'];measurement=v['measurement'];meta=v['meta']
                        flags=dict(E0_or_invariant=not(v['E0_pass'] and v['invariants_pass']),
                            DIO_missing_or_outside=not(pitch['dio_error_semitones'] is not None and pitch['dio_error_semitones']<=1.),
                            ACF_missing_or_outside=not(pitch['acf_error_semitones'] is not None and pitch['acf_error_semitones']<=1.),
                            ACF_low_confidence=measurement['acf_confidence']<.6,
                            inadequate_native_support=len(measurement['support'])<3,
                            candidate_missing_fixed_support=bool(measurement['missing_support']))
                        assert pitch['passed']==(not any(flags[k] for k in flags if k!='E0_or_invariant'))
                        reasons.update(k for k,x in flags.items() if x);support_pass+=measurement['support_complete']
                        fill=meta.get('control',{}).get('fill',{});by_index={x['index']:x for x in fill.get('intervals',[])}
                        missing=[]
                        for i in measurement['missing_support']:
                            phone=re.search(r'\-([^+]+)\+',row['full_context_labels'][i]).group(1)
                            local_missing[phone]+=1;known=by_index.get(i)
                            after=(known['native_voiced_frames']+known['filled_frames']) if known else None
                            whole=after==known['frames'] if known else None
                            source_known['fully_voiced_after_control' if whole else ('partly_voiced_after_control' if known else 'source_voicing_unknown')]+=1
                            missing.append(dict(index=i,phone=phone,source_after_control_voiced_frames=after,
                                source_frames=known['frames'] if known else None,source_fully_voiced=whole,
                                inferred_from_existing_control_metadata_only=True,not_actual_WORLD_excitation_truth=True))
                        case=dict(cohort=folder,id=v['id'],method=method,condition=condition,length=row['length'],
                            source_record_sha256=digest(path),wave_sha256=v['wav_sha256'],failure_flags=flags,
                            pitch_gate=pitch,missing_support=missing,generated_lf0_median_hz=meta.get('generated_lf0_median_hz'),
                            drive_at_requested_semitone_error=abs(12*math.log2(meta['generated_lf0_median_hz']/q['requested_f0'])) if meta.get('generated_lf0_median_hz') else None,
                            no_perceived_pitch_truth_claim=True)
                        cases.append(case)
                expected=summary['engineering'][method]['expected']
                assert len(cases)==expected==32
                assert sum(not any(c['failure_flags'].values()) for c in cases)==summary['engineering'][method]['pitch_pass_count']
                for engine in ['whisper','reazon']:
                    pairs=[];hist=Counter()
                    for row in p['rows']:
                        for condition in p['conditions']:
                            apath=base/'asr'/engine/row['id']/condition/(method+'.json');npath=apath.with_name('native.json');sealed(apath);sealed(npath)
                            a,n=read(apath),read(npath);assert a['status']==n['status']=='completed' and a['reference_kana']==n['reference_kana']
                            distance,ops=edits(a['reference_kana'],a['predicted_kana'])
                            assert distance==a['errors'];assert edits(n['reference_kana'],n['predicted_kana'])[0]==n['errors']
                            hist.update(x['kind'] for x in ops)
                            pairs.append(dict(id=a['id'],condition=condition,length=row['length'],challenge_group=row['challenge_group'],
                                errors=distance,native_errors=n['errors'],characters=a['characters'],
                                operations=ops,source_sha256=digest(apath),native_sha256=digest(npath)))
                    groups=grouped(pairs);assert groups==summary['content'][method][engine]['groups']
                    content[engine]=dict(groups=groups,edit_operations=dict(hist),
                        worsening_groups=[k for k,x in groups.items() if not x['non_worsening']],old_groups_exact_match=True)
                    all_details.append(dict(cohort=folder,method=method,engine=engine,pairs=pairs,diagnostic_only=True))
                methods[method]=dict(expected=expected,pitch_pass_count=summary['engineering'][method]['pitch_pass_count'],
                    E0_pass_count=summary['engineering'][method]['E0_pass_count'],support_pass_count=support_pass,
                    overlapping_failure_counts=dict(reasons),missing_phone_counts=dict(local_missing),
                    missing_source_voicing=dict(source_known),content=content,old_qualification=summary['qualifications'][method],
                    observational_association_not_causation=True)
                all_details.append(dict(cohort=folder,method=method,cases=cases,diagnostic_only=True))
                w=content['whisper']['groups']['both/all'];r=content['reazon']['groups']['both/all']
                lines.append(f"|{folder.removeprefix('nas-').removesuffix('-20261008-v1')}/{method}|32|{methods[method]['pitch_pass_count']}|{support_pass}|{sum(local_missing.values())}|{w['errors']}/{w['characters']}|{r['errors']}/{r['characters']}|{len(content['whisper']['worsening_groups'])}/{len(content['reazon']['worsening_groups'])}|")
            all_aggregates[folder]=dict(methods=methods,protocol_sha256=digest(base/'protocol.json'),seal_sha256=digest(base/'artifact-seal.json'),
                old_qualifications_unchanged=True,within_cohort_pairs_only=True)
        b.write_data(HERE/'detailed-summary.json',encode(all_details),job)
        b.save(HERE/'aggregate-summary.json',dict(cohorts=all_aggregates,negative_fixtures=fixture,total_wave_records=992,
            total_existing_ASR_records=1984,new_waveform_or_tracker_or_AI=0,
            old_group_counts_exact_match=True,no_cross_cohort_pooled_ranking=True,
            drive_voicing_is_not_actual_excitation_or_perceived_pitch_truth=True,
            old_qualifications_unchanged=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
            detailed_summary_path=str((HERE/'detailed-summary.json').relative_to(REPO)),detailed_summary_sha256=digest(HERE/'detailed-summary.json')),job)
        lines+=['','理由の件数は重複を許す。源LF0支持は保存control metadataで判別できるものだけを表示し、未知を推定で補完しない。',
            'kana編集区分は保存済み認識結果の記述整理で、音素時刻対応や因果の証明には使わない。',
            '第18回の人工周期資格と第22回の実励振周期診断は適用範囲を保持し、旧測定ゲート・採否・知覚資格へ広げない。',
            '新しい生成・音響測定・ASR・教師・fit・逆推定・取得・一時ファイルは0。全体品質未達、P5未開封。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),job)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
