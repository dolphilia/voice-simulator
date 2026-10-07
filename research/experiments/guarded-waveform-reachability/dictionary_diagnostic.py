"""保存済み認識文字列だけの辞書診断。別プロセスで旧utilityを再利用する。"""
import json
from pathlib import Path
import sys
import shutil

LOCAL_ROOT = Path(__file__).resolve().parent
OUTPUT = LOCAL_ROOT/'results/nas-guarded-f0-20261003-v1'
CONTENT_ROOT = LOCAL_ROOT.parent/'acoustic-revision-content-evaluation'
sys.path.insert(0, str(CONTENT_ROOT))
from reading_audit import DictionaryReadings
from campaign import save, digest


def main():
    protocol = json.loads((OUTPUT/'engine-contract.json').read_text())
    config = protocol['reading_diagnostic']['contract']
    assert digest(CONTENT_ROOT/'reading_audit.py') == protocol['reading_diagnostic']['source_sha256']
    dictionary_path = Path(config['dictionary_path'])
    for name, sha in config['dictionary_files'].items():
        assert digest(dictionary_path/name) == sha
    assert digest(Path(config['library'])) == config['library_sha256']
    reader = DictionaryReadings(config['library'], dictionary_path, nbest=16)
    rows, cache = [], {}
    try:
        for p in sorted((OUTPUT/'asr').rglob('*.json')):
            record = json.loads(p.read_text())
            if record['status'] != 'completed':
                continue
            text = record['hypothesis']
            if text not in cache:
                cache[text] = reader.inspect(text)
            rows.append({'id': record['id'], 'engine': record['engine'], 'hypothesis': text,
                'record_sha256': digest(p), 'ambiguities': cache[text]['ambiguities'],
                'unknown_tokens': cache[text].get('unknown_tokens', []), 'raw_errors': record['errors']})
    finally:
        reader.close()
    shutil.copyfile(dictionary_path/'COPYING', OUTPUT/'DICTIONARY-COPYING')
    save(OUTPUT/'reading-diagnostic.json', {'rows': rows, 'unique_hypotheses': len(cache),
        'ambiguity_count_by_engine': {e: sum(bool(r['ambiguities']) for r in rows if r['engine'] == e)
                                     for e in ('whisper', 'reazon')},
        'dictionary_copying_sha256': digest(OUTPUT/'DICTIONARY-COPYING'),
        'settings_frozen_before_asr': True, 'gold_used_to_choose_readings': False,
        'primary_cer_modified': False, 'perception_qualified': False,
        'scope': '辞書の上位16字句経路。読み網羅・意味適合・音声の発音正解・完全音素列を仮定しない'})


if __name__ == '__main__':
    main()
