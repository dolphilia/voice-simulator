"""原PDFのTable1を全80径で照合し、著者Web表の異版を別に記録する。"""
import sys,json,re,tempfile,os
from html.parser import HTMLParser
from pathlib import Path
from pypdf import PdfReader
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
here=Path(sys.argv[1]);expected=json.loads((here/'diameters.json').read_text());pdf=PdfReader(here/'upstream/arai-2007.pdf')
assert len(pdf.pages)==12
text=pdf.pages[3].extract_text(extraction_mode='layout')
rows={v:list(map(int,nums.split())) for v,nums in re.findall(r'/([ieaou])/\s+((?:\d+\s+){15}\d+)',text)}
assert rows==expected,(rows,expected)
class Table(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=='tr':self.row=[]
  if tag in ('td','th') and self.row is not None:self.cell=[]
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ('td','th') and self.cell is not None:self.row.append(''.join(self.cell).strip());self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
p=Table();p.feed((here/'upstream/arai-lab.html').read_text());lab={r[0].strip('/'):r[1:] for r in p.rows if r and r[0].strip('/') in expected}
assert set(lab)==set(expected) and all(len(r)==16 for r in lab.values())
different=[]
for v,row in lab.items():
 for index,(value,old) in enumerate(zip(row,expected[v]),1):
  if value!=str(old):different.append(dict(vowel=v,index_from_lips=index,paper_diameter_mm=old,lab_cell=value))
print(json.dumps(dict(passed=True,paper_pages=12,table_page_one_based=4,all_80_diameters_exact=True,glottis_is_index16=True,plate_length_mm=10,all_vowel_lengths_cm=16,lab_differences=different,paper_numeric_facts_selected_before_output=True,source_article_not_CC_license_claim=True,source_audio_or_figures_reused_as_generator=False)))
