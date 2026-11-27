"""MFAのMFCCアーカイブ形式を段ごとに変えて特徴量を採取する。"""

from contextlib import ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch

from _kalpy.util import BaseFloatMatrixWriter
from montreal_forced_aligner.corpus import features

from probe_mfa_cmvn import FeatureCapture, run_probe


def archive_tokens(scp):
    tokens = {}
    for line in scp.read_text().splitlines():
        key, destination = line.split(maxsplit=1)
        file, offset = destination.rsplit(':', 1)
        with Path(file).open('rb') as stream:
            stream.seek(int(offset))
            prefix = stream.read(7)
        if not prefix.startswith(b'\0B') or b' ' not in prefix[2:]:
            raise ValueError(f'Kaldiのバイナリ行列の種別を読めません ({key})')
        tokens[key] = prefix[2:].split(b' ', 1)[0].decode('ascii')
    return tokens


class ArchiveCapture(FeatureCapture):
    def capture_and_replace(self, aligner):
        self.input_tokens = archive_tokens(aligner.corpus_output_directory / 'feats.scp')
        super().capture_and_replace(aligner)

    def capture_final(self, aligner):
        super().capture_final(aligner)
        final_tokens = archive_tokens(aligner.jobs[0].feats_scp_path)
        rows = {mode: {'input': self.input_tokens[utt], 'final': final_tokens[utt]}
                for mode, (utt, _) in self.ids.items()}
        self.output.with_name('archive-formats.json').write_text(json.dumps(rows, sort_keys=True, indent=2) + '\n')


def run_uncompressed(capture, *, uncompressed_final=False):
    write_mfcc = features.MfccFunction._run
    write_final = features.FinalFeatureFunction._run

    def write_float32(job):
        if job.pitch_computer is not None:
            raise ValueError('MFCC以外の特徴量を同じジョブで書き出す条件には対応していません')
        compute = job.mfcc_computer.compute_mfccs_for_export

        def uncompressed_mfcc(segment, compress=True):
            return compute(segment, compress=False)

        with (patch.object(job.mfcc_computer, 'compute_mfccs_for_export', uncompressed_mfcc),
              patch.object(features, 'CompressedMatrixWriter', BaseFloatMatrixWriter)):
            return write_mfcc(job)

    def write_final_float32(job):
        with (patch.object(features, 'CompressedMatrix', lambda matrix: matrix),
              patch.object(features, 'CompressedMatrixWriter', BaseFloatMatrixWriter)):
            return write_final(job)

    with ExitStack() as changes:
        changes.enter_context(patch.object(features.MfccFunction, '_run', write_float32))
        if uncompressed_final:
            changes.enter_context(patch.object(features.FinalFeatureFunction, '_run', write_final_float32))
        run_probe(capture)


def main():
    storage = sys.argv.pop(1)
    case = json.loads(Path(sys.argv.pop(1)).read_text())
    capture = ArchiveCapture(case, Path(sys.argv.pop(1)))
    if storage in ('float32', 'float32_both'):
        run_uncompressed(capture, uncompressed_final=storage == 'float32_both')
    elif storage == 'compressed':
        run_probe(capture)
    else:
        raise ValueError(f'未対応のMFCC保存形式です ({storage})')


if __name__ == '__main__':
    main()
