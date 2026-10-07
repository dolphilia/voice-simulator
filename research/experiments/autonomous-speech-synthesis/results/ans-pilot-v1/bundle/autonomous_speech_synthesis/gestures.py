"""音素標的から連続制御を計算する。保存済み発話軌跡を持たない。"""
import copy
import unicodedata
import numpy as np

VOWELS = "aiueo"
CONSONANTS = ("m", "n", "N", "s", "sh", "h", "f", "p", "t", "k", "b", "d", "g", "z", "j", "ts", "ch", "r", "w", "y", "ky", "gy", "ny", "hy", "my", "ry", "Q", "pau")
PHONES = set(VOWELS) | set(CONSONANTS) | {"I", "U"}

DEFAULT_VOICE = {
    "version": "dsp-lf-gesture-v1", "language": "ja", "sample_rate_hz": 24000,
    "source": {"tp": .4, "te": .6, "ta": .05, "aspiration": .008},
    "formants_hz": {"a": [800.,1200.,2500.], "i": [270.,2290.,3010.], "u": [300.,870.,2240.], "e": [530.,1840.,2480.], "o": [570.,840.,2410.]},
    "bandwidths_hz": [90.,120.,180.], "formant_gains": [1.,.55,.28],
    "tract_scale": 1., "bandwidth_scale": 1., "gain": .32,
    "transition_seconds": .035, "noise_gain": .10,
    "units": {"source": "周期で正規化した声門流の微分 dU/du（相対単位）", "waveform": "放射変換後の相対音圧、フルスケール1。Pa校正なし", "f0": "Hz", "duration": "秒", "formants": "Hz"},
    "provenance": "母音標的は旧Web/研究プリセット。発話固有係数なし",
}


def voice_config(changes=None):
    result = copy.deepcopy(DEFAULT_VOICE)
    if changes:
        result.update(copy.deepcopy(changes))
    return result


def validate_voice(voice):
    if set(voice) != set(DEFAULT_VOICE):
        raise ValueError("話者設定のキーが契約外です（任意の波形・軌跡を許可しません）")
    if set(voice["formants_hz"]) != set(VOWELS):
        raise ValueError("母音標的は5種類必要です")
    for formants in voice["formants_hz"].values():
        if len(formants) != 3 or not all(np.isfinite(formants)) or not 150 <= formants[0] < formants[1] < formants[2] < 5500:
            raise ValueError("フォルマント標的が不正です")
    for key, bounds in {"tract_scale": (.75,1.3), "bandwidth_scale": (.5,2.), "gain": (.01,1.), "transition_seconds": (0.,.1), "noise_gain": (0.,.3)}.items():
        if not np.isfinite(voice[key]) or not bounds[0] <= voice[key] <= bounds[1]:
            raise ValueError(f"話者係数が範囲外です: {key}")
    if set(voice["source"]) != {"tp", "te", "ta", "aspiration"}:
        raise ValueError("音源係数が契約外です")
    tp,te,ta,noise = (voice["source"][k] for k in ("tp","te","ta","aspiration"))
    if not all(np.isfinite([tp,te,ta,noise])) or not (0 < tp < te < min(2*tp,1) and 0 < ta < 1-te and 0 <= noise <= .1):
        raise ValueError("LF音源係数が不正です")
    if len(voice["bandwidths_hz"]) != 3 or not all(20 <= b <= 500 for b in voice["bandwidths_hz"]):
        raise ValueError("帯域幅が不正です")
    if len(voice["formant_gains"]) != 3 or not all(0 < b <= 1 for b in voice["formant_gains"]):
        raise ValueError("フォルマント利得が不正です")


def kana_to_phonemes(text):
    """かな表記に限定した辞書非依存前段。未知文字は黙って捨てない。"""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(chr(ord(c)-0x60) if "ァ" <= c <= "ヶ" else c for c in text)
    table = dict(zip("あいうえお", VOWELS))
    for chars, onset in [("かきくけこ","k"),("がぎぐげご","g"),("さしすせそ","s"),("ざじずぜぞ","z"),("たちつてと","t"),("だぢづでど","d"),("なにぬねの","n"),("はひふへほ","h"),("ばびぶべぼ","b"),("ぱぴぷぺぽ","p"),("まみむめも","m"),("らりるれろ","r")]:
        table.update({c: onset+" "+v for c,v in zip(chars,VOWELS)})
    table.update({"し":"sh i","じ":"j i","ち":"ch i","つ":"ts u","ぢ":"j i","づ":"z u","ふ":"f u","や":"y a","ゆ":"y u","よ":"y o","わ":"w a","を":"o","ん":"N","っ":"Q"})
    result = []
    for index,c in enumerate(text):
        if c in "ゃゅょ":
            if len(result)<2 or result[-1] != "i":
                raise ValueError(f"拗音の前段を解釈できません: {index}")
            result.pop()
            base=result.pop()
            result.extend([{"k":"ky","g":"gy","n":"ny","h":"hy","m":"my","r":"ry","sh":"sh","ch":"ch","j":"j"}.get(base, base), {"ゃ":"a","ゅ":"u","ょ":"o"}[c]])
        elif c == "ー":
            if not result or result[-1] not in VOWELS:
                raise ValueError("長音の直前に母音が必要です")
            result.append(result[-1])
        elif c in " 、。，,.!?！？\n":
            if result and result[-1] != "pau":
                result.append("pau")
        elif c in table:
            result.extend(table[c].split())
        else:
            raise ValueError(f"未対応文字: {c}。かな、または明示音素で指定してください")
    return result


def make_gestures(phonemes, prosody, voice, sample_rate):
    validate_voice(voice)
    phones=list(phonemes)
    if not phones or any(p not in PHONES for p in phones):
        raise ValueError("空入力または未対応音素です")
    if set(prosody) - {"f0_hz","speed","durations_seconds","accent_nucleus","intonation","devoice"}:
        raise ValueError("韻律指定のキーが契約外です")
    f0=float(prosody.get("f0_hz",220))
    speed=float(prosody.get("speed",1))
    if not 80 <= f0 <= 400 or not .6 <= speed <= 1.6:
        raise ValueError("F0または速度が適用範囲外です")
    lengths=prosody.get("durations_seconds")
    if lengths is None:
        lengths=[(.12 if p.lower() in VOWELS else .16 if p == "pau" else .10 if p in ("Q","N") else .065)/speed for p in phones]
    if len(lengths)!=len(phones) or not all(np.isfinite(lengths)) or not all(.01<=d<=2 for d in lengths) or sum(lengths)>30:
        raise ValueError("音素継続長の契約違反です（最大30秒）")
    bounds=np.r_[0,np.cumsum(np.rint(np.array(lengths)*sample_rate).astype(int))]
    count=int(bounds[-1])
    tracks={k:np.zeros(count) for k in ("voicing","noise","noise_center_hz","nasal","gain","f0_hz")}
    tracks["formants_hz"]=np.zeros((count,3))
    events=[]
    mora=0
    for i,p in enumerate(phones):
        left,right=int(bounds[i]),int(bounds[i+1]); n=right-left
        u=np.linspace(0,1,n)
        vowel=next((q.lower() for q in phones[i:] if q.lower() in VOWELS), next((q.lower() for q in reversed(phones[:i]) if q.lower() in VOWELS),"a"))
        target=np.array(voice["formants_hz"][vowel])*voice["tract_scale"]
        voiced=1.; noise=np.zeros(n); amp=np.ones(n); nasal=0.; center=4000.
        if p.lower() in VOWELS:
            mora+=1
            if p in ("I","U") or (prosody.get("devoice",True) and p in ("i","u") and i>0 and i+1<len(phones) and phones[i-1] in ("k","s","sh","t","h","p") and phones[i+1] in ("k","s","sh","t","h","p")):
                voiced=.08; noise[:]=.18; center=2000.
        elif p in ("m","n","N","ny","my"):
            nasal=1.; amp[:]=.6
            target[0]=280.; target[1]*=.9
        elif p in ("p","t","k","b","d","g","ky","gy","ch","ts","j"):
            voiced=.22 if p in ("b","d","g","gy","j") else 0.
            amp[:]=.12 if voiced else 0.
            release=.68 if p not in ("ch","ts","j") else .45
            noise=np.where(u>release, np.exp(-18*(u-release)),0.)
            if p in ("ch","ts","j"):
                noise=np.where(u>release,.65,0.)
            center=1000. if p in ("p","b") else 2600. if p in ("k","g","ky","gy") else 4500.
            target[1] += -220 if p in ("p","b") else 220 if p in ("k","g","ky","gy") else 60
        elif p in ("s","sh","h","f","z","hy"):
            voiced=.35 if p=="z" else 0.; noise[:]=1.
            center={"s":6500.,"sh":4000.,"h":1600.,"hy":2300.,"f":1100.,"z":5500.}[p]
            amp[:]=.5
        elif p == "r" or p=="ry":
            amp=.35+.65*(np.abs(u-.5)>.20)
            target[2]*=.85
        elif p in ("w","y"):
            target=np.array(voice["formants_hz"]["u" if p=="w" else "i"])*voice["tract_scale"]
        elif p in ("Q","pau"):
            amp[:]=0.; voiced=0.
        tracks["formants_hz"][left:right]=target
        tracks["voicing"][left:right]=voiced
        tracks["noise"][left:right]=noise
        tracks["noise_center_hz"][left:right]=center
        tracks["nasal"][left:right]=nasal
        tracks["gain"][left:right]=amp
        contour=1.
        if prosody.get("intonation",True) and len(phones)>1:
            contour=(1.05-.15*(left+np.arange(n))/count)
            if mora==1: contour=contour*.93
            if 0 < prosody.get("accent_nucleus",0) < mora: contour=contour*.85
        tracks["f0_hz"][left:right]=f0*contour
        events.append({"phone":p,"start_seconds":left/sample_rate,"end_seconds":right/sample_rate,"mora_index":mora,"nasal_coupling":nasal,"voiced_target":voiced})
    # 声道標的は境界をまたいで補間。閉鎖・破裂の時間構造は保存する。
    width=round(voice["transition_seconds"]*sample_rate)
    for boundary in bounds[1:-1]:
        half=min(width//2,int(boundary),count-int(boundary))
        if half>0:
            lo,hi=int(boundary)-half,int(boundary)+half
            weight=(.5-.5*np.cos(np.linspace(0,np.pi,hi-lo)))[:,None]
            tracks["formants_hz"][lo:hi]=(1-weight)*tracks["formants_hz"][lo]+weight*tracks["formants_hz"][hi-1]
    # 励起利得も短い連続ジェスチャへ。音声断片は使用しない。
    kernel=np.ones(max(1,round(.003*sample_rate))); kernel/=len(kernel)
    for key in ("voicing","nasal","gain","noise"):
        tracks[key]=np.convolve(tracks[key],kernel,mode="same")
    return tracks,events
