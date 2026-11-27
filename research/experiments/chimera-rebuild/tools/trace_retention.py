"""比較の判定後、ケースに指定したCSVの列と区間を保存する。"""

import csv
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory


class RetainedTraces:
    def __init__(self, case_path):
        rules = json.loads(case_path.read_text()).get('retain_csv', {})
        if not isinstance(rules, dict):
            raise ValueError('retain_csv は成果の相対パスごとの設定を指定してください')
        self.selections = []
        for path, rule in rules.items():
            name = PurePosixPath(path)
            if name.is_absolute() or '..' in name.parts or name.suffix != '.csv':
                raise ValueError(f'retain_csv に不正なCSVパスがあります ({path})')
            if not isinstance(rule, dict):
                raise ValueError(f'CSVの保存設定が不正です ({path})')
            columns = rule.get('columns')
            if (not isinstance(columns, list) or not columns or
                    not all(isinstance(column, str) and column for column in columns) or
                    len(set(columns)) != len(columns)):
                raise ValueError(f'保存する列を重複なく指定してください ({path})')
            sample_column = rule.get('sample_column')
            if sample_column not in columns:
                raise ValueError(f'保存する列にサンプル番号の列を含めてください ({path})')
            ranges = rule.get('sample_ranges')
            if not isinstance(ranges, list) or not ranges or any(
                not isinstance(pair, list) or len(pair) != 2
                or not all(type(bound) is int for bound in pair) or not 0 <= pair[0] < pair[1]
                for pair in ranges
            ):
                raise ValueError(f'サンプル範囲を [開始, 終了) で指定してください ({path})')
            self.selections.append((name, columns, sample_column, ranges))

    def apply(self, artifacts, describe, manifest):
        if not self.selections:
            return
        rows = []
        with TemporaryDirectory(prefix='.retain-csv-', dir=artifacts) as scratch:
            for number, (name, columns, sample_column, ranges) in enumerate(self.selections):
                source = artifacts / name
                retained = source.with_suffix('.retained.csv')
                if source.resolve() != source or not source.is_file() or retained.exists() or retained.is_symlink():
                    raise ValueError(f'元のCSVまたは抜粋の出力先を確認してください ({name})')
                temporary = Path(scratch) / str(number)
                try:
                    row_count = project_csv(source, temporary, columns, sample_column, ranges)
                except csv.Error as error:
                    raise ValueError(f'元のCSVの読み取りに失敗しました ({name})') from error
                record = {'source': describe(source, artifacts.parent), 'columns': columns,
                          'sample_column': sample_column, 'sample_ranges': ranges, 'rows': row_count,
                          'path': retained.relative_to(artifacts.parent).as_posix()}
                rows.append((source, temporary, retained, record))
            for _, temporary, retained, _ in rows:
                temporary.replace(retained)
            manifest['retained_csv'] = [record for _, _, _, record in rows]
            for source, _, _, _ in rows:
                source.unlink()


def project_csv(source, target, columns, sample_column, ranges):
    row_count = 0
    with source.open(newline='') as original, target.open('x', newline='') as selected:
        reader = csv.reader(original)
        writer = csv.writer(selected, lineterminator='\n')
        header = next(reader, [])
        if len(header) != len(set(header)) or any(column not in header for column in columns):
            raise ValueError(f'指定した列をCSVから選択できません ({source.name})')
        indices = [header.index(column) for column in columns]
        frame = header.index(sample_column)
        writer.writerow(columns)
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f'列数が一致しない行があります ({source.name} {reader.line_num})')
            sample = int(row[frame])
            if any(start <= sample < end for start, end in ranges):
                writer.writerow([row[index] for index in indices])
                row_count += 1
    if not row_count:
        raise ValueError(f'指定したサンプル範囲に出力がありません ({source.name})')
    return row_count
