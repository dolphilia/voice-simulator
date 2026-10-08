"""別版の予約入口を先に照合し、変更しない全件終了監査へ委譲する。"""
import hts_allpass_comparison_20261008_v2 as driver
import hts_allpass_closeout_20261008 as original

def close():
    driver.verify_amendment();original.close()

if __name__=='__main__':close()
