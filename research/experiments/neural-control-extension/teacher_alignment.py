"""保存済み教師の記号を照合する。既知の表記差と誤読を区別する。"""
import math
from extract_controls import IPA, canonical


def align_saved(analysis, teacher):
    chars, frames = teacher['phonemes'], teacher['predicted_duration_frames']
    if len(frames) != len(chars)+2 or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in frames) or sum(frames) <= 0:
        raise ValueError('教師のtoken継続長が不正です')
    duration = teacher['duration_seconds']
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('教師の音声長が不正です')
    step = duration/sum(frames)
    cursor = frames[0]*step
    items, gaps, equivalences = [], [], []
    for index, (char, frame) in enumerate(zip(chars, frames[1:-1])):
        start, end = cursor, cursor+frame*step
        cursor = end
        if char in ' .,!?:;':
            gaps.append({'symbol':char, 'start':start, 'end':end})
            continue
        if char == 'ʲ':
            if not items:
                raise ValueError('口蓋化の先行音素がありません')
            items[-1]['end'] = end
            continue
        if char == 'ː':
            if not items or items[-1]['observed'] not in ('a','i','u','e','o'):
                raise ValueError('長音の先行母音がありません')
            phone = items[-1]['observed']
        else:
            phone = 'w' if char == 'β' else IPA.get(char, char)
        items.append({'observed':phone, 'source_symbol':char, 'token_index':index, 'start':start, 'end':end})
        if char == 'β':
            equivalences.append({'index':len(items)-1,'from':'β','to':'w','rule':'Misaki Cutletの「わ」等の記号表'})
    expected = [canonical(p) for p in analysis['phonemes']]
    if len(expected) != len(items):
        raise ValueError('音素数が一致しません')
    for i, (exp, item) in enumerate(zip(expected, items)):
        obs = item['observed']
        following = items[i+1]['observed'] if i+1 < len(items) else None
        nasal = exp == 'N' and ((item['source_symbol']=='m' and following in ('m','p','b')) or
                               (item['source_symbol']=='n' and following in ('n','t','d','r','z')) or
                               (item['source_symbol']=='ɲ' and following in ('n','ch','j')))
        if exp != obs and nasal:
            equivalences.append({'index':i,'from':item['source_symbol'],'to':'N','rule':'Misaki Cutletの後続子音に応じた撥音表記'})
        elif exp != obs:
            raise ValueError(f'未解決の音素不一致: index={i}, expected={exp}, observed={obs}')
        item['phone'] = analysis['phonemes'][i]
    for left, right in zip(items, items[1:]):
        middle = (left['end']+right['start'])/2
        left['end'], right['start'] = middle, middle
    if any(item['end'] <= item['start'] for item in items):
        raise ValueError('音素区間が非正です')
    return items, gaps, equivalences
