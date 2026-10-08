"""カ行の生成前ログ名失敗に対する技術再試行。科学条件を変更しない。"""
import sys
from pathlib import Path
from budget import ROOT,read,digest
import vtl_shared_cv_development_20261009 as original
from observed_process_20261009 import run_observed
def checked_observer(*args,**kwargs):
 if kwargs.get('label')!='CV-development':raise ValueError('固定ログ名だけの修正を要求')
 kwargs['label']='cv-development'
 return run_observed(*args,**kwargs)
def main():
 here,name=original.location('k');receipt=read(here/'technical-retry-registration.json')
 assert digest(Path(__file__))==receipt['retry_entry_sha256'];assert digest(ROOT/'vtl_shared_cv_development_20261009.py')==receipt['original_controller_sha256']
 original.verify(here);original.run_observed=checked_observer;original.run('k')
 import vtl_shared_cv_development_20261009_v2 as next_controller
 next_controller.register('t')
if __name__=='__main__':main()
