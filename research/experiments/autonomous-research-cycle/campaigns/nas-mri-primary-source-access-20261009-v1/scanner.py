"""取得PDFの一次文献同一性と表位置だけを確認。全数値の資格は別段階。"""
import sys,json,re,os,tempfile
from pathlib import Path
from pypdf import PdfReader
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
source=Path(sys.argv[1]);pages=PdfReader(source).pages;texts=[p.extract_text(extraction_mode='layout') for p in pages];alltext='\n'.join(texts)
assert len(pages)==13 and '10.1121/1.2151823' in alltext and 'Takemoto' in alltext and '2006' in alltext
tables={r:[i+1 for i,t in enumerate(texts) if re.search(r'TABLE\s+'+r+r'\s*\.',t)] for r in ['I','II','III']};assert all(tables.values())
print(json.dumps(dict(passed=True,pages=len(pages),DOI='10.1121/1.2151823',table_pages_one_based=tables,full_numeric_table_verified=False,geometry_direction_units_and_lengths_verified=False,generated_waveforms=0)))
