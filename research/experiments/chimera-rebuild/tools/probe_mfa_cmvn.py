"""MFAの通常CLIの中でCMVN統計の参照を交換し、特徴量を採取する。"""

import json
from pathlib import Path
import sys

import numpy as np
from _kalpy import transform
from _kalpy.util import RandomAccessBaseDoubleMatrixReader
from kalpy.feat.data import FeatureArchive
from kalpy.utils import generate_read_specifier
from montreal_forced_aligner.command_line.mfa import mfa_cli
from montreal_forced_aligner.corpus.acoustic_corpus import AcousticCorpusMixin
from montreal_forced_aligner.db import Utterance


class FeatureCapture:
    def __init__(self, case, output):
        self.uid = case['utterance']
        self.conditions = case['measurement']['conditions']
        self.output = output
        self.matrices = {}
        self.ids = {}
        self.calc_cmvn = AcousticCorpusMixin.calc_cmvn
        self.generate_final_features = AcousticCorpusMixin.generate_final_features

    def capture_and_replace(self, aligner):
        self.calc_cmvn(aligner)
        if len(aligner.jobs) != 1 or not aligner.uses_cmvn or getattr(aligner, 'sliding_cmvn', False):
            raise ValueError('登録した1ジョブ・発話ごとのCMVNを使用していません')
        if aligner.mfcc_computer.dither != 0 or aligner.uses_speaker_adaptation:
            raise ValueError('ディザまたは話者適応が有効になっています')
        names = {f'{self.uid}-{mode}': mode for mode in self.conditions}
        path = aligner.corpus_output_directory
        raw = FeatureArchive(path / 'feats.scp')
        # MFAは全体のCMVN索引を数値の話者ID順で書き出す。
        original = RandomAccessBaseDoubleMatrixReader(generate_read_specifier(path / 'cmvn.scp', sorted=False))
        try:
            with aligner.session() as session:
                utterances = session.query(Utterance).filter_by(ignored=False).all()
                by_mode = {names[utt.speaker.name]: utt for utt in utterances}
                if set(by_mode) != self.conditions.keys() or len(utterances) != len(self.conditions):
                    raise ValueError('各条件に1話者・1発話が必要です')
                native_references = {mode: utt.speaker.cmvn for mode, utt in by_mode.items()}
                for mode, utt in by_mode.items():
                    self.ids[mode] = (utt.kaldi_id, str(utt.speaker_id))
                    self.matrices[f'{mode}_uncompressed'] = aligner.mfcc_computer.compute_mfccs(utt.segment).copy()
                    self.matrices[f'{mode}_input'] = raw[utt.kaldi_id].numpy().copy()
                    self.matrices[f'{mode}_own_stats'] = original.Value(str(utt.speaker_id)).numpy().copy()
                    utt.speaker.cmvn = native_references[self.conditions[mode]['statistics']]
                session.commit()
        finally:
            original.Close()
            raw.close()
        job = aligner.jobs[0]
        cmvn_path = job.construct_path(aligner.split_directory, 'cmvn', 'scp')
        references = {self.ids[mode][1]: native_references[selection['statistics']]
                      for mode, selection in self.conditions.items()}
        current = dict(line.split(maxsplit=1) for line in cmvn_path.read_text().splitlines() if line.strip())
        if current.keys() != references.keys():
            raise ValueError('ジョブのCMVN索引と観測する話者が一致しません')
        cmvn_path.write_text(''.join(f'{sid} {references[sid]}\n' for sid in current))
        selected = RandomAccessBaseDoubleMatrixReader(generate_read_specifier(cmvn_path))
        raw = FeatureArchive(path / 'feats.scp')
        try:
            for mode, (utt, speaker) in self.ids.items():
                stats = selected.Value(speaker)
                self.matrices[f'{mode}_used_stats'] = stats.numpy().copy()
                self.matrices[f'{mode}_normalized'] = transform.apply_cmvn(raw[utt], stats, norm_vars=False).numpy().copy()
        finally:
            raw.close()
            selected.Close()

    def capture_final(self, aligner):
        self.generate_final_features(aligner)
        final = FeatureArchive(aligner.jobs[0].feats_scp_path)
        try:
            for mode, (utt, _) in self.ids.items():
                self.matrices[f'{mode}_final'] = final[utt].numpy().copy()
        finally:
            final.close()
        if not self.ids:
            raise ValueError('正規化統計の採取処理が呼ばれていません')
        np.savez_compressed(self.output, **self.matrices)


def run_probe(capture):
    def calc_cmvn(aligner):
        capture.capture_and_replace(aligner)

    def generate_final_features(aligner):
        capture.capture_final(aligner)

    AcousticCorpusMixin.calc_cmvn = calc_cmvn
    AcousticCorpusMixin.generate_final_features = generate_final_features
    mfa_cli()


def main():
    case = json.loads(Path(sys.argv.pop(1)).read_text())
    run_probe(FeatureCapture(case, Path(sys.argv.pop(1))))


if __name__ == '__main__':
    main()
