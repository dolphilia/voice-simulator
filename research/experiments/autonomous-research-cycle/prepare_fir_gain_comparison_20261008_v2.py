"""科学契約登録前の参照先誤置換だけを別版で修正し、元の構築ソースを保存する。"""
import ast
from pathlib import Path
from budget import ROOT,digest
from long_horizon_budget import LongHorizonBudget as Budget

def main():
    b=Budget();assert not b.snapshot()['jobs']
    old=ROOT/'hts_fir_gain_comparison_20261008.py';text=old.read_text()
    bad="previous_speech_seal_sha256=digest(ROOT/'campaigns/nas-hts-fir-gain-comparison-20261008-v1/artifact-seal.json')"
    good="previous_speech_seal_sha256=digest(ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1/artifact-seal.json')"
    assert text.count(bad)==1;text=text.replace(bad,good).replace("ROOT/'hts_fir_gain_closeout_20261008.py'","ROOT/'hts_fir_gain_closeout_20261008_v2.py'")
    ast.parse(text);new=ROOT/'hts_fir_gain_comparison_20261008_v2.py';b.write(new,text.encode())
    oldclose=ROOT/'hts_fir_gain_closeout_20261008.py';close=oldclose.read_text().replace('from hts_fir_gain_comparison_20261008 import','from hts_fir_gain_comparison_20261008_v2 import')
    ast.parse(close);newclose=ROOT/'hts_fir_gain_closeout_20261008_v2.py';b.write(newclose,close.encode())
    b.save(ROOT/'fir-gain-static-source-correction-v2.json',dict(reason='構築時のcampaign名置換が前の結果封印参照も自己参照へ変えていた。静的検査で科学契約登録前に検出。',original_source_sha256=digest(old),original_closeout_sha256=digest(oldclose),corrected_source_sha256=digest(new),corrected_closeout_sha256=digest(newclose),generator_sha256=digest(Path(__file__)),scientific_campaign_registered_before_detection=False,new_scientific_outputs_before_correction=0,methods_costs_gates_and_module_unchanged=True))
    print('科学登録前の前結果封印参照を別版へ修正',flush=True)

if __name__=='__main__':main()
