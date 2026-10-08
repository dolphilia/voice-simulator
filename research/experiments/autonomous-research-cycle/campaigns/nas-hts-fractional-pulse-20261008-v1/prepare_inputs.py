from paths import *
import re,json,unicodedata
def norm(value):
    return re.sub(r'[\W_]', '', unicodedata.normalize('NFKC', value))


def collect(value, texts, labels):
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            texts.add(norm(value['text']))
        if value.get('full_context_labels'):
            labels.add(tuple(value['full_context_labels']))
        for item in value.values():
            collect(item, texts, labels)
    elif isinstance(value, list):
        for item in value:
            collect(item, texts, labels)


def inputs():
    import os
    import sys
    import tempfile
    assert Path(tempfile.gettempdir()).resolve() == Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0, str(HERE / 'runtime-bundle'))
    from japanese_frontend import analyze
    import pyopenjtalk
    history = dict(read(PREVIOUS / 'novelty-audit.json')['history_reference_hashes'])
    for directory in (ROOT / 'campaigns').iterdir():
        if directory == HERE:
            continue
        for name in ['protocol.json']:
            path = directory / name
            if path.exists():
                history[str(path.relative_to(REPO))] = digest(path)
    for name in ['protocol.json', 'novelty-audit.json']:
        path = PREVIOUS / name
        history[str(path.relative_to(REPO))] = digest(path)
    texts, labels = set(), set()
    for name, expected in history.items():
        assert not re.search('splits|protected|holdout|final-confirm', name, re.I)
        assert digest(REPO / name) == expected, name
        collect(read(REPO / name), texts, labels)
    pool = read(HERE / 'candidate-pool.json')
    rows, audit = [], []
    for length in ['short', 'long']:
        selected = []
        for text in pool['candidate_pool_' + length]:
            row = analyze(text)
            collision = norm(text) in texts or tuple(row['full_context_labels']) in labels
            valid = 3 <= len(row['full_context_labels']) <= 122
            chosen = not collision and valid and len(selected) < 8
            audit.append(dict(text=text, length=length, collision=collision,
                label_count=len(row['full_context_labels']), selected=chosen))
            if chosen:
                selected.append(row)
                texts.add(norm(text))
                labels.add(tuple(row['full_context_labels']))
        assert len(selected) == 8, '生成前に入力不足で停止'
        for group, row in enumerate(selected):
            row.update(id='fractional-fresh-' + str(len(rows)).zfill(2), length=length,
                challenge_group=group, cohort='prospective_once', kana=pyopenjtalk.g2p(row['text'], kana=True))
            rows.append(row)
    print(json.dumps(dict(rows=rows, audit=dict(history_reference_hashes=history,
        pool_checked_before_output=audit, selected_rows=[dict(id=r['id'], text=r['text'], kana=r['kana'])
        for r in rows], protected_confirmation_opened=False, final_quality_independence_claim=False)),
        ensure_ascii=False))
if __name__=='__main__':inputs()
