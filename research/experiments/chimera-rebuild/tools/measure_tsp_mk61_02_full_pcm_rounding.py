"""同文の男性体型MK61_02で、変換前の誤差とPCMの丸めを照合する。"""

from pathlib import Path

import measure_tsp_fk61_02_full_pcm_rounding as female


CASE = female.radiation.WORKSPACE / 'cases/tsp-mk61-02-full-pcm-rounding.json'
SAVED_FILES = female.SAVED_FILES


def error_ratios(current, prior):
    return {
        signal: {key: current['full'][signal][key] / prior['full'][signal][key] for key in ('peak', 'rms')}
        for signal in ('precast', 'pcm')
    }


def analyze(study, out, saved_pcm, saved_summary, previous_summary, config, gain, coeff):
    result = female.analyze_observation(study, out, saved_pcm, saved_summary, config, gain, coeff)
    prior = previous_summary['comparison']
    ratios = error_ratios(result['comparison'], prior)
    lo, hi = study['measurement']['precast_rms_ratio_limits']
    result['hypotheses']['precast_rms_male_over_female_between_0p5_and_2'] = lo <= ratios['precast']['rms'] <= hi
    result['male_over_female'] = ratios
    result['fk61_02_comparison'] = {key: prior[key] for key in ('full', 'pcm_one_ulp', 'pcm_more_than_one_ulp')}
    return result


if __name__ == '__main__':
    raise SystemExit(female.run_case(CASE, analyze, __doc__, entrypoint=Path(__file__).resolve()))
