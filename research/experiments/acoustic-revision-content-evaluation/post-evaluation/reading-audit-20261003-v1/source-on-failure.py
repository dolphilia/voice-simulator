"""既存辞書の読み候補を記録する。音声認識・生成・CER補正は行わない。"""
import csv
import ctypes
import io
import json
from pathlib import Path
import time
from collections import Counter
from campaign import ROOT, RESULT, REPO, read, save, digest, verify_seal

FOLLOWUP = ROOT/'post-evaluation/reading-audit-20261003-v1'


class DictionaryReadings:
    """MeCab公開C APIによる上位16形態素解析の読み候補診断。"""
    def __init__(self, library, dictionary, nbest=16):
        if type(nbest) is not int or not 1 <= nbest <= 32:
            raise ValueError('候補数は1〜32の整数にします')
        directory = str(Path(dictionary).resolve())
        if any(c in directory for c in ('"', '\n', '\r', '\x00')):
            raise ValueError('辞書パスを引用できません')
        if not (Path(directory)/'sys.dic').is_file():
            raise FileNotFoundError('既存の辞書だけを使用します')
        self.nbest = nbest
        self.lib = ctypes.CDLL(str(library))
        self.lib.mecab_new2.argtypes = [ctypes.c_char_p]
        self.lib.mecab_new2.restype = ctypes.c_void_p
        self.lib.mecab_destroy.argtypes = [ctypes.c_void_p]
        self.lib.mecab_destroy.restype = None
        self.lib.mecab_strerror.argtypes = [ctypes.c_void_p]
        self.lib.mecab_strerror.restype = ctypes.c_char_p
        self.lib.mecab_nbest_sparse_tostr.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
        self.lib.mecab_nbest_sparse_tostr.restype = ctypes.c_char_p
        self.handle = self.lib.mecab_new2(f'-r /dev/null -d "{directory}"'.encode())
        if not self.handle:
            raise RuntimeError(self.lib.mecab_strerror(None).decode())

    def close(self):
        if self.handle:
            self.lib.mecab_destroy(self.handle)
            self.handle = None

    def inspect(self, text):
        if not self.handle:
            raise RuntimeError('辞書ハンドルを終了しています')
        if not isinstance(text, str) or '\x00' in text or len(text.encode()) > 3000:
            raise ValueError('短いNULなしの文字列を要求します')
        if not text:
            return {'text': text, 'paths': [], 'ambiguities': [], 'empty': True,
                    'complete_reading_coverage': False}
        raw = self.lib.mecab_nbest_sparse_tostr(self.handle, self.nbest, text.encode())
        if not raw:
            raise RuntimeError(self.lib.mecab_strerror(self.handle).decode())
        paths, tokens = [], []
        for line in raw.decode().splitlines():
            if line == 'EOS':
                paths.append(tokens)
                tokens = []
            elif line:
                surface, feature = line.split('\t', 1)
                fields = next(csv.reader(io.StringIO(feature)))
                tokens.append({'surface': surface, 'features': fields,
                    'reading': fields[7] if len(fields) > 7 else None,
                    'pronunciation': fields[8] if len(fields) > 8 else None})
        if not paths:
            raise ValueError('解析経路がありません')
        base = paths[0]
        # 形態素境界・品詞・活用・原形を固定。別分割や人名への読み替えを混ぜない。
        def signature(path):
            return [(t['surface'], t['features'][:7]) for t in path]
        candidates = [p for p in paths if signature(p) == signature(base)]
        ambiguities = []
        for i, token in enumerate(base):
            readings = sorted({p[i]['reading'] for p in candidates
                               if p[i]['reading'] not in (None, '*')})
            pronunciations = sorted({p[i]['pronunciation'] for p in candidates
                                     if p[i]['pronunciation'] not in (None, '*')})
            if len(readings) > 1 or len(pronunciations) > 1:
                ambiguities.append({'token_index': i, 'surface': token['surface'],
                    'best_reading': token['reading'], 'readings': readings,
                    'pronunciations': pronunciations, 'grammar': token['features'][:7]})
        return {'text': text, 'paths': paths, 'same_grammar_paths': len(candidates),
                'ambiguities': ambiguities, 'unknown_tokens': [t['surface'] for t in base
                    if t['reading'] in (None, '*')], 'empty': False,
                'complete_reading_coverage': False,
                'scope': '上位16経路の字句読み診断。意味・文脈適合・実音の発音は未認定。OpenJTalkの助詞・数詞等の後処理前であり、完全な音素列やCERとして使わない'}


def main():
    started = time.time()
    if FOLLOWUP.exists():
        raise FileExistsError('既存の追記診断を上書きしません')
    FOLLOWUP.mkdir(parents=True)
    before = verify_seal(RESULT/'artifact-seal.json')
    import pyopenjtalk
    directory = Path(pyopenjtalk.OPEN_JTALK_DICT_DIR.decode())
    library = next(Path(pyopenjtalk.__file__).parent.glob('openjtalk*.so'))
    provenance = {'dictionary_files': {p.name: digest(p) for p in sorted(directory.iterdir()) if p.is_file()},
        'dictionary_path': str(directory), 'library': str(library), 'library_sha256': digest(library),
        'pyopenjtalk_version': pyopenjtalk.__version__, 'source_sha256': digest(Path(__file__)),
        'sources': ['https://taku910.github.io/mecab/libmecab.html',
                    'https://github.com/r9y9/pyopenjtalk/blob/master/pyopenjtalk/__init__.py'],
        'settings': {'nbest': 16, 'same_segmentation_and_first_seven_feature_fields': True,
                     'gold_reference_used_to_select_candidates': False},
        'started_epoch': started, 'followup_scope': '封印後の静的診断。旧台帳を再開しない',
        'teacher_calls': 0, 'render_calls': 0, 'ai_calls': 0, 'train_calls': 0,
        'downloads': 0, 'primary_results_modified': False}
    save(FOLLOWUP/'contract.json', provenance)
    dictionary = DictionaryReadings(library, directory)
    try:
        rows, analyses = [], {}
        for engine in ('whisper', 'reazon'):
            for row in read(RESULT/'protocol.json')['rows']:
                source = RESULT/'asr'/engine/(row['id']+'.json')
                record = read(source)
                assert record['status'] == 'completed'
                text = record['hypothesis']
                if text not in analyses:
                    analyses[text] = dictionary.inspect(text)
                analysis = analyses[text]
                rows.append({'engine': engine, 'id': row['id'], 'hypothesis': text,
                    'record_sha256': digest(source), 'frozen_errors': record['errors'],
                    'ambiguous': bool(analysis['ambiguities']),
                    'ambiguities': analysis['ambiguities'], 'unknown_tokens': analysis.get('unknown_tokens', [])})
        # 自然な読みの保証ではなく、辞書候補の取得と失敗経路の検査。
        probe = dictionary.inspect('金の響く')
        gold = next(a for a in probe['ambiguities'] if a['surface'] == '金')
        assert {'キン', 'カネ'} <= set(gold['readings'])
        assert all(a['grammar'][1] != '固有名詞' for a in probe['ambiguities'])
        assert dictionary.inspect('カネの響く')['ambiguities'] == []
        assert dictionary.inspect('')['empty']
        try:
            dictionary.inspect('金\x00の響く')
        except ValueError:
            nul_rejected = True
        else:
            raise AssertionError('NUL入力を拒否しませんでした')
        unknown = dictionary.inspect('2時が出た。')
        assert '2' in unknown['unknown_tokens']
        save(FOLLOWUP/'analyses.json', {'unique_hypotheses': len(analyses),
             'analyses': list(analyses.values()), 'known_example': probe,
             'number_postprocessing_example': unknown})
        save(FOLLOWUP/'summary.json', {'rows': rows, 'record_count': len(rows),
            'ambiguity_count_by_engine': dict(Counter(r['engine'] for r in rows if r['ambiguous'])),
            'unknown_token_count_by_engine': dict(Counter(r['engine'] for r in rows if r['unknown_tokens'])),
            'unique_ambiguous_hypotheses': len({r['hypothesis'] for r in rows if r['ambiguous']}),
            'primary_score_correction': False, 'gate_changed': False,
            'content_protection_recertified': False, 'perception_qualified': False,
            'new_phonetic_ground_truth': False,
            'tests': {'multiple_readings_found_without_gold': True, 'grammar_filter_enforced': True,
                      'single_reading_kana_control': True, 'empty_supported': True,
                      'nul_rejected': nul_rejected, 'number_unknown_not_a_complete_reading': True},
            'next_contract': '判定用の原CERを保持し、曖昧性を別欄に保存する。辞書候補がないことを音声や読みの正しさの証拠にしない。数字・未知語・分割違いを完全音素列へ黙って置換しない'})
    finally:
        dictionary.close()
    try:
        dictionary.inspect('金')
    except RuntimeError:
        closed_rejected = True
    else:
        raise AssertionError('終了したハンドルを使用しました')
    after = verify_seal(RESULT/'artifact-seal.json')
    assert before == after
    for name, sha in provenance['dictionary_files'].items():
        assert digest(directory/name) == sha
    save(FOLLOWUP/'audit.json', {'seconds': time.time()-started, 'old_seal': after,
        'old_evaluation_unchanged': True, 'dictionary_unchanged': True, 'closed_handle_rejected': closed_rejected,
        'original_goal_completed': False, 'previous_goal_turn_classification': 'progress',
        'current_turn_classification': 'progress', 'new_generation_evaluation_authorization_received': False,
        'fresh_resumed_turn': 2, 'no_live_processes': True,
        'additional_execution_proposal': 'docs/plans/acoustic-control-factorial-proposal-2026-10-02.md'})
    print(read(FOLLOWUP/'summary.json')['ambiguity_count_by_engine'])
    print('既存200認識の辞書読み監査が完了しました。生成・AI評価の追加は0回です')


if __name__ == '__main__':
    main()
