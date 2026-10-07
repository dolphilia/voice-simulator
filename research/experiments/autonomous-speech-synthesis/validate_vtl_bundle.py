#!/usr/bin/env python3
"""研究モジュール・移出モジュール・OS隔離実行の波形一致を照合する。"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import write_once,file_hash
from autonomous_speech_synthesis.backends import VTL
from vtl_japanese import render_japanese


def main():
    bundle=ROOT/'results/vtl-bundle-v2'
    spec=importlib.util.spec_from_file_location('vtl_entry',bundle/'synthesize.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    text='あたらしいちずをひろげる'
    phones=entry.kana_to_phonemes(text);analysis=entry.analysis_from_phones(phones,[0])
    vtl=VTL()
    try:audio,_,fs=render_japanese(vtl,analysis,'accent',1009)
    finally:vtl.close()
    expected=hashlib.sha256(audio.astype('<f8').tobytes()).hexdigest()
    normal=json.loads((ROOT/'.cache/vtl-bundle-normal.json').read_text())
    isolated=json.loads((ROOT/'.cache/vtl-bundle-isolated-v2.json').read_text())
    result={'passed':expected==normal['sha256_float64']==isolated['sha256_float64'],'expected_sha256_float64':expected,'normal':normal,'isolated':isolated,
      'OS_profile_sha256':file_hash(ROOT/'results/ans-pilot-v1/os-isolation-v2.sb'),'initial_nested_sandbox_error':(ROOT/'.cache/vtl-bundle-isolated.stderr').read_text(),
      'scope':'同じ未知入力の生成一致。音声品質ゲートではない。OSは参照、AIキャッシュ、ネットワークを拒否。','source_sha256':file_hash(Path(__file__))}
    output=ROOT/'results/vtl-isolation-v2';output.mkdir(exist_ok=True)
    for name in ('ans-vtl-bundle-normal.wav','ans-vtl-bundle-isolated.wav'):
        target=output/name
        if target.exists():raise FileExistsError('証拠波形は上書きしません')
        shutil.copyfile(Path('/tmp')/name,target)
    write_once(output/'verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
