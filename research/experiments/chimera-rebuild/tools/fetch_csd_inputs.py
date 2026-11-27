"""固定のZenodo版から、登録した英語曲のCSVとWAVだけを作業用ディスクへ取得する。"""

import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from run_storage import WORK_DISK, WORK_UUID, mounted_volume


CASE = Path(__file__).resolve().parents[1] / 'cases/csd-song-planning.json'
METADATA_URL = 'https://zenodo.org/api/records/4916302'
CURL = ['curl', '--fail', '--silent', '--show-error', '--location', '--connect-timeout', '10', '--max-time', '90']


class RemoteZip(io.RawIOBase):
    def __init__(self, url, size, prefix):
        self.url = url
        self.size = size
        self.prefix = prefix
        self.offset = 0
        self.cache_start = size - 256 * 1024
        self.cache = self.fetch(self.cache_start, size)

    def fetch(self, start, stop):
        suffix = f'{start}-{stop-1}'
        raw = subprocess.check_output([*CURL, '--range', suffix, '--max-filesize', str(stop - start),
                                       '--write-out', '\n%{http_code} %header{content-range}', self.url])
        block, _, response = raw.rpartition(b'\n')
        if response.decode() != f'206 bytes {suffix}/{self.size}' or len(block) != stop - start:
            raise OSError('配布サーバーの応答範囲が登録版と一致しません')
        return block

    def seekable(self):
        return True

    def tell(self):
        return self.offset

    def seek(self, offset, whence=io.SEEK_SET):
        origins = {io.SEEK_SET: 0, io.SEEK_CUR: self.offset, io.SEEK_END: self.size}
        target = origins[whence] + offset
        if target < 0:
            raise OSError('ZIPの位置が先頭より前です')
        self.offset = target
        return target

    def read(self, size=-1):
        start = self.offset
        stop = self.size if size < 0 else min(start + size, self.size)
        if stop <= start:
            return b''
        if self.prefix.is_file() and stop <= self.prefix.stat().st_size:
            with self.prefix.open('rb') as stream:
                stream.seek(start)
                block = stream.read(stop - start)
            if len(block) == stop - start:
                self.offset = stop
                return block
        if not self.cache_start <= start < stop <= self.cache_start + len(self.cache):
            fetch_stop = min(self.size, max(stop, start + 65536))
            self.cache_start, self.cache = start, self.fetch(start, fetch_stop)
        self.offset = stop
        return self.cache[start - self.cache_start:stop - self.cache_start]


def main():
    case = json.loads(CASE.read_text())
    data = case['dataset']
    root = Path(data['work_root'])
    device = mounted_volume(WORK_DISK, WORK_UUID)
    if root.parent.resolve() != root.parent or root.parent.stat().st_dev != device:
        raise ValueError('評価データの作業領域を確認できません')
    root.mkdir(exist_ok=True)
    if root.resolve() != root or root.stat().st_dev != device or shutil.disk_usage(root).free < 128 * 1024**2:
        raise ValueError('評価データ用ディスクの位置と空きを確認できません')
    raw = subprocess.check_output([*CURL, METADATA_URL])
    metadata = json.loads(raw)
    file_entry, = [f for f in metadata['files'] if f['key'] == 'CSD.zip']
    if (metadata['doi'] != data['doi'] or file_entry['size'] != data['archive_bytes']
            or file_entry['checksum'] != f"md5:{data['archive_md5']}"
            or file_entry['links']['self'] != data['archive_url']
            or metadata['metadata']['license']['id'] != data['license'].lower().replace(' ', '-')):
        raise ValueError('Zenodoの配布情報が登録版と一致しません')
    inputs = {}
    prefix = root / 'CSD.zip.part'
    if not prefix.is_file():
        prefix = root / 'CSD.zip'
    with ZipFile(RemoteZip(data['archive_url'], data['archive_bytes'], prefix)) as archive:
        for song in case['songs']:
            uid = song['id']
            for kind in ('csv', 'wav'):
                name = f'CSD/english/{kind}/{uid}.{kind}'
                info = archive.getinfo(name)
                payload = archive.read(info)
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    if path.read_bytes() != payload:
                        raise ValueError(f'保存済みデータが配布元と一致しません ({name})')
                else:
                    tmp = path.with_suffix(f'{path.suffix}.part')
                    tmp.write_bytes(payload)
                    tmp.rename(path)
                inputs[name] = {'bytes': len(payload), 'crc32': f'{info.CRC:08x}',
                                'sha256': hashlib.sha256(payload).hexdigest()}
                print(f'{name} {len(payload)} bytes', flush=True)
    (root / 'zenodo-4916302.json').write_bytes(raw)
    result = {'record_doi': data['doi'], 'archive_file': file_entry, 'archive_whole_md5_verified': False,
              'method': 'HTTPS Range / ZIP CRC32', 'metadata_sha256': hashlib.sha256(raw).hexdigest(),
              'license': metadata['metadata']['license']['id'], 'files': inputs}
    (root / 'selected-inputs.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
