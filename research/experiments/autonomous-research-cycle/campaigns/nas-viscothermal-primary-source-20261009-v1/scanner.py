"""一次PDF同一性と元本文を確認。数値/機構/音声の採択ではない。"""
import sys,json,os,tempfile
from pathlib import Path
from pypdf import PdfReader
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
pdf=PdfReader(sys.argv[1]);assert len(pdf.pages)==9
texts=[p.extract_text(extraction_mode='layout') for p in pdf.pages];full='\n'.join(texts)
assert 'Hayashi' in texts[0] and 'Miki' in texts[0] and '10.1250/ast.29.130' in full and '2008' in full
Path(sys.argv[2]).write_text(full)
print(json.dumps(dict(passed=True,pages=9,DOI='10.1250/ast.29.130',extracted_layout_bytes=len(full.encode()),all_equations_and_units_visually_verified=False,parameters_or_code_adopted=False)))
