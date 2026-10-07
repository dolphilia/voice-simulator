"""同じ文章で教師の別声を比較する。共有モデルの再学習には使用しない。"""
import json
import sys
import time
import urllib.request
import numpy as np
from scipy.io import wavfile
from campaign import ExtensionBudget, ROOT, PILOT, RESULT, save, digest
from teacher import load_teacher

REVISION = 'f3ff3571791e39611d31c381e3a41a3af07b4987'
VOICE = 'jf_gongitsune'


def main():
    budget = ExtensionBudget()
    cache = ROOT/'.cache/teacher'
    voice_path = cache/(VOICE+'.pt')
    provenance = cache/'provenance.json'
    if not provenance.exists():
        with budget.job('setup', '固定revisionの別声取得・由来保存', 2000000):
            cache.mkdir(parents=True, exist_ok=True)
            url = f'https://huggingface.co/hexgrad/Kokoro-82M/resolve/{REVISION}/voices/{VOICE}.pt'
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read(1000001)
            if len(data) > 1000000:
                raise ValueError('声ファイルの取得上限です')
            with voice_path.open('xb') as f:
                f.write(data)
            if not digest(voice_path).startswith('1b171917'):
                raise ValueError('公式一覧のハッシュ接頭辞と不一致')
            save(provenance, {'voice': VOICE, 'url': url, 'revision': REVISION,
                              'sha256': digest(voice_path), 'bytes': len(data), 'model_license': 'Apache-2.0',
                              'source_credit': 'テレビ西日本の朗読音声（声庭 koniwa / tnc ごん狐）、原作 新美南吉',
                              'source_audio_license': 'CC BY 3.0',
                              'source_audio_license_url': 'https://creativecommons.org/licenses/by/3.0/',
                              'source_license_evidence': 'https://raw.githubusercontent.com/koniwa/koniwa/master/README.md',
                              'changes': 'Kokoro学習済み声の条件を用いて新規文章を合成。原録音を再配布しない',
                              'source_url': 'https://github.com/koniwa/koniwa/blob/master/source/tnc/tnc__gongitsune.txt',
                              'voice_notice': '公式VOICES.mdのCC BY欄に出典を記載。研究用途、最終bundleに含めない',
                              'voice_catalog': str(PILOT/'.cache/teacher/VOICES.md'),
                              'voice_catalog_sha256': digest(PILOT/'.cache/teacher/VOICES.md'),
                              'selection': '生成前にjf_gongitsune、未知文の先頭8件へ固定。声の違いを別基盤の独立性としない'})
    if digest(voice_path) != json.loads(provenance.read_text())['sha256']:
        raise ValueError('別声のハッシュ不一致')
    with budget.job('setup', '固定教師と二つの声の読込', 5000000):
        model, alpha, g2p = load_teacher()
        import torch
        voices = {'jf_alpha': alpha, VOICE: torch.load(voice_path, map_location='cpu', weights_only=True)}
    rows = json.loads((RESULT/'protocol.json').read_text())['rows']
    for name, voice in voices.items():
        for row in rows if name == 'jf_alpha' else rows[:8]:
            target = RESULT/'teacher'/name/(row['id']+'.json')
            if target.exists():
                old = json.loads(target.read_text())
                if digest(ROOT/old['wav']) != old['wav_sha256']:
                    raise ValueError('既存教師音声の変更')
                continue
            with budget.job('teacher', name+'/'+row['id'], 5000000):
                phonemes, _ = g2p(row['text'])
                unknown = sorted(set(phonemes)-set(model.vocab))
                if unknown or not 1 <= len(phonemes) <= len(voice):
                    raise ValueError('教師入力の範囲外: '+repr(unknown))
                torch.manual_seed(20261002)
                start = time.monotonic()
                with torch.inference_mode():
                    output = model(phonemes, voice[len(phonemes)-1], speed=1., return_output=True)
                audio = output.audio.detach().cpu().numpy().astype(np.float32)
                if audio.ndim != 1 or not np.isfinite(audio).all() or np.max(abs(audio)) >= 1:
                    raise ValueError('教師音声の有限値・振幅検査に不通過')
                target.parent.mkdir(parents=True, exist_ok=True)
                wav = target.with_suffix('.wav')
                if wav.exists():
                    raise FileExistsError('未記録の教師波形を上書きしません')
                wavfile.write(wav, 24000, audio)
                save(target, {'id': row['id'], 'text': row['text'], 'variant': name, 'condition': 'neutral',
                              'phonemes': phonemes, 'wav': str(wav.relative_to(ROOT)), 'wav_sha256': digest(wav),
                              'seconds': time.monotonic()-start, 'duration_seconds': len(audio)/24000,
                              'predicted_duration_frames': output.pred_dur.tolist(), 'seed': 20261002,
                              'research_only': True, 'runtime_neural': True, 'pronunciation_repair': None,
                              'used_in_training': False, 'voice_provenance': str(provenance.relative_to(ROOT)) if name == VOICE else '旧pilot固定資産'})
            print(name, row['id'], len(audio)/24000, flush=True)


if __name__ == '__main__':
    main()
