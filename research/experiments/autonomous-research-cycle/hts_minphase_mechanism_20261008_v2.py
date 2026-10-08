"""jobの秒数予約APIだけを直す。最初の呼出は予約前TypeError、科学出力なし。"""
from contextlib import contextmanager
import hts_minphase_mechanism_20261008 as original

class Budget(original.Budget):
    @contextmanager
    def job(self,campaign,kind,label,count=1,reserve_bytes=0,expected_seconds=0):
        token=self.reserve(campaign,kind,label,count,reserve_bytes,expected_seconds=expected_seconds)
        try:
            yield token
        except BaseException as exc:
            self.finish(token,repr(exc))
            raise
        else:
            self.finish(token)

if __name__=='__main__':
    original.Budget=Budget
    original.run()
