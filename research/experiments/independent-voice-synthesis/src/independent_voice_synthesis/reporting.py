"""保存済み証拠による工程状態と固定P1成果物。"""
import json
from datetime import datetime, timezone
import numpy as np
from scipy.io import wavfile
from .models import known
from .p1_connection import source_coefficients, pressure, synthesize, presentation
from .qualification import digest, save


def prepare_p1(root):
    e0_path=root/'results/e0/qualification/summary.json'
    e0=json.loads(e0_path.read_text())
    if e0['status'] != 'qualification_failed':
        raise ValueError('このK1接続経路は、記録された点検不通過を前提とします')
    cfg_path=root/'config/p1-connection.json'
    cfg=json.loads(cfg_path.read_text())
    if cfg['candidates'] != ['K1-P5']:
        raise ValueError('固定候補一覧が異なります')
    out=root/'results/p1/fixed-k1'
    out.mkdir(parents=True,exist_ok=False)
    f,flow,derivative,c=source_coefficients(cfg)
    p=known()
    coefficients=pressure(p,f,flow,cfg)
    steady=synthesize(coefficients,f,cfg)
    signals,levels=presentation([steady],cfg)
    wave=signals[0].astype(np.float32)
    wavfile.write(out/'K1-P5.wav',cfg['Fs'],wave)
    # フェードに由来する有限長の帯域外漏れも隠さず記録する。
    freqs=np.fft.rfftfreq(len(wave),1/cfg['Fs'])
    energy=abs(np.fft.rfft(wave))**2
    outside=(freqs<=100)|(freqs>=5000)
    manifest=dict(status='stimuli_ready_perception_pending',created=datetime.now(timezone.utc).isoformat(),
        e0_summary_sha256=digest(e0_path),config_sha256=digest(cfg_path),
        listening_contract_sha256=digest(root/'config/p1-listening-contract.md'),
        code_sha256={str(p.relative_to(root)):digest(p) for p in sorted((root/'src').rglob('*.py'))},
        configuration=cfg,parameters=p,lf_constants=c,levels=levels,
        file='K1-P5.wav',sha256=digest(out/'K1-P5.wav'),samples=len(wave),sample_rate=cfg['Fs'],
        sample_format='IEEE float32',finite=bool(np.all(np.isfinite(wave))),
        max_harmonic_hz=float(np.max(f)),highest_nonzero_pressure_harmonic_hz=float(np.max(f[abs(coefficients)>0])),
        after_fade_outside_energy_ratio=float(np.sum(energy[outside])/np.sum(energy)),
        final_peak_float32=float(np.max(abs(wave))),final_rms_float32=float(np.sqrt(np.mean(wave.astype(float)**2))),
        limitations=['K1は合成した既知モデル。公開測定への適合例ではない','測定位相は未確認','知覚回答未収集','フェード後には有限長窓による微小な帯域外漏れがある'])
    save(out/'manifest.json',manifest)
    save(out/'response-template.json',dict(participant_id='user-01',audio_sha256=manifest['sha256'],
         status='pending',answered_at=None,playable=None,human_voice_similarity=None,
         vowel_impression=None,specific_issue=None,origin_impression=None,device=None,play_count=None,
         source_origin_known=True,verbatim=None))
    return manifest


def status(root):
    q=root/'results/e0/qualification/summary.json'
    p=root/'results/p1/fixed-k1/manifest.json'
    return dict(E0=json.loads(q.read_text())['status'] if q.exists() else 'not_started',
                P1=json.loads(p.read_text())['status'] if p.exists() else 'not_started',
                human_response='未収集',goal_complete=False)
