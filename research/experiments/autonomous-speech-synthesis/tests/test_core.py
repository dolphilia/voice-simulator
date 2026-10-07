"""数値破綻・汚染・誤昇格・再開に対する回帰検査。"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.generator import render,lf_derivative,lf_coefficients,lf_source
from autonomous_speech_synthesis.gestures import voice_config,kana_to_phonemes
from autonomous_speech_synthesis.evaluation import evaluate,promotion,grouped_bootstrap
from autonomous_speech_synthesis.io import write_once,read
from autonomous_speech_synthesis.data import reference_features
from autonomous_speech_synthesis.export import export_bundle,audit_bundle,isolated_check
from autonomous_speech_synthesis.runner import Campaign,BudgetExhausted
from autonomous_speech_synthesis.io import append,digest


class NumericalTests(unittest.TestCase):
    def test_stationary_source_has_no_out_of_band_harmonics(self):
        for fs in (16000,24000,48000):
            for f0 in (160,220,300):
                with self.subTest(fs=fs,f0=f0):
                    x=lf_source(np.full(fs,f0,dtype=float),fs,voice_config()["source"])
                    p=abs(np.fft.rfft(x))**2
                    freq=np.fft.rfftfreq(fs,1/fs)
                    self.assertLess(np.sum(p[freq>fs*.45])/np.sum(p),1e-15)

    def test_lf_zero_area_and_analytic_spectrum(self):
        phase=np.linspace(0,1,100001)
        derivative=lf_derivative(phase)
        self.assertLess(abs(np.trapezoid(derivative,phase)),1e-7)
        expected=np.array([np.trapezoid(derivative*np.exp(-2j*np.pi*n*phase),phase) for n in range(1,16)])
        np.testing.assert_allclose(lf_coefficients(15,.4,.6,.05),expected,atol=1e-7)

    def test_all_vowel_f0_cells(self):
        for v in "aiueo":
            for f0 in (160,220,300):
                with self.subTest(v=v,f0=f0):
                    x,_=render([v],{"f0_hz":f0,"durations_seconds":[.25]})
                    result=evaluate(x,{"kind":"vowel","f0_hz":f0,"expected_duration_seconds":.25})
                    self.assertTrue(result["E0_pass"])
                    self.assertTrue(result["E1"]["f0_control_pass"])

    def test_reproducible_seed_and_gain_control(self):
        voice=voice_config()
        x,_=render(["s","a"],voice=voice,seed=19)
        same,_=render(["s","a"],voice=voice,seed=19)
        other,_=render(["s","a"],voice=voice,seed=20)
        np.testing.assert_array_equal(x,same)
        self.assertGreater(np.max(abs(x-other)),.001)
        voice["gain"]*=.5
        half,_=render(["s","a"],voice=voice,seed=19)
        np.testing.assert_allclose(half,.5*x,atol=1e-15)

    def test_consonant_closure_frication_and_silence(self):
        x,log=render(["a","Q","s","a"],{"durations_seconds":[.15,.1,.1,.15],"intonation":False})
        rms=lambda start,end:np.sqrt(np.mean(x[round(start*24000):round(end*24000)]**2))
        self.assertLess(rms(.2,.24),rms(.05,.1)*.1)
        self.assertGreater(rms(.28,.33),1e-3)
        self.assertEqual(len(log["events"]),4)

    def test_missing_and_corrupt_signals_cannot_pass(self):
        for x in ([],[float("nan")],[float("inf")],np.zeros(500),np.ones(500),np.full(500,.2)):
            self.assertFalse(evaluate(x,{})["E0_pass"])
        x,_=render(["a"],{"durations_seconds":[.2]})
        self.assertFalse(evaluate(x,{"expected_duration_seconds":.4})["E0_pass"])

    def test_unknown_phone_and_nonfinite_input_rejected(self):
        for args in [(["bad"],{}),(["a"],{"f0_hz":float("nan")}),(["a"],{"durations_seconds":[40.]})]:
            with self.assertRaises(ValueError):render(*args)


class ContractTests(unittest.TestCase):
    def test_frontend_long_geminate_nasal_and_palatalized(self):
        self.assertEqual(kana_to_phonemes("キョー、きって、ほん"),["ky","o","o","pau","k","i","Q","t","e","pau","h","o","N"])
        with self.assertRaises(ValueError):kana_to_phonemes("未知漢字")

    def test_missing_qualification_never_promotes(self):
        for q in ({},{"mandatory":["MOS"],"metrics":{"MOS":{"status":"diagnostic-only"}}}):
            self.assertEqual(promotion([{"E0_pass":True}],q,True)["state"],"inconclusive")
        q={"mandatory":["MOS"],"metrics":{"MOS":{"status":"qualified"}}}
        self.assertEqual(promotion([{"E0_pass":True}],q,True)["state"],"inconclusive")
        self.assertEqual(promotion([{"E0_pass":False}],q,True)["state"],"rejected")

    def test_empty_evidence_never_promotes(self):
        self.assertEqual(promotion([],{},True)["state"],"inconclusive")
        self.assertEqual(grouped_bootstrap([1.,2.])["state"],"inconclusive")

    def test_confirmation_read_guard(self):
        with self.assertRaises(PermissionError):reference_features({},"confirmation")

    def test_write_once_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"result.json"
            write_once(p,{"a":1});write_once(p,{"a":1})
            with self.assertRaises(FileExistsError):write_once(p,{"a":2})
            self.assertEqual(read(p),{"a":1})

    def test_export_rejects_hidden_audio_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);write_once(p/"voice-config.json",voice_config())
            bundle=export_bundle(p)
            (bundle/"hidden.wav").write_bytes(b"RIFF")
            with self.assertRaises(ValueError):audit_bundle(bundle)
            (bundle/"hidden.wav").unlink()
            (bundle/"voice-config.json").write_text("{}")
            with self.assertRaises(ValueError):audit_bundle(bundle)

    def test_standalone_exact_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);write_once(p/"voice-config.json",voice_config())
            result=isolated_check(p)
            self.assertTrue(result["passed"],result.get("stderr"))


class ResumeTests(unittest.TestCase):
    def test_failed_render_consumes_budget_and_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp,patch("autonomous_speech_synthesis.runner.ROOT",Path(tmp)):
            config=read(ROOT/"config/campaign-v1.json")
            config["budget"]["max_p34_renders"]=1
            campaign=Campaign("test-resume",config)
            try:
                calls=[]
                def broken():
                    calls.append(1);raise ValueError("故障fixture")
                result=campaign.trial("candidate","dsp","P3",{"id":"one"},1,{},broken)
                self.assertEqual(result["status"],"unavailable")
                campaign.trial("candidate","dsp","P3",{"id":"one"},1,{},broken)
                self.assertEqual(len(calls),1)
                with self.assertRaises(BudgetExhausted):campaign.trial("candidate","dsp","P3",{"id":"two"},1,{},broken)
            finally:campaign.close()

    def test_changed_config_cannot_resume_existing_id(self):
        with tempfile.TemporaryDirectory() as tmp,patch("autonomous_speech_synthesis.runner.ROOT",Path(tmp)):
            config=read(ROOT/"config/campaign-v1.json")
            campaign=Campaign("test-config",config);campaign.close()
            changed=copy.deepcopy(config);changed["seed"]+=1
            with self.assertRaises(FileExistsError):Campaign("test-config",changed)

    def test_interrupted_render_retries_with_new_attempt(self):
        with tempfile.TemporaryDirectory() as tmp,patch("autonomous_speech_synthesis.runner.ROOT",Path(tmp)):
            campaign=Campaign("test-interruption",read(ROOT/"config/campaign-v1.json"))
            try:
                task={"id":"one"}
                request={"candidate_id":"c","backend":"dsp","stage":"P3","task":task,"seed":1,"parameters":{},"identity":campaign.identity_hash}
                trial_id=digest(request)[:24]
                event={"event":"started","trial_id":trial_id,"attempt":1,"backend":"dsp","stage":"P3","budget_key":"max_p34_renders"}
                append(campaign.path/"ledger.jsonl",event);campaign.events.append(event)
                def execute():
                    x,log=render(["a"]);return x,log,24000
                result=campaign.trial("c","dsp","P3",task,1,{},execute)
                self.assertEqual(result["attempt"],2)
                self.assertEqual(sum(e["event"]=="started" for e in campaign.events),2)
            finally:campaign.close()


if __name__=="__main__":unittest.main()
