"""P0: 実ファイル・既存履歴を調べ、話者と文の分割を凍結する。"""
import re
from collections import Counter
from .io import ROOT,REPO,read,write_once,file_hash,digest,now
from .gestures import VOWELS,kana_to_phonemes


def task_suite():
    tasks=[]
    for vowel in VOWELS:
        for f0 in (160,220,300):
            tasks.append({"id":f"vowel-{vowel}-{f0}","stage":"P2","kind":"vowel","phonemes":[vowel],"f0_hz":f0,
                          "prosody":{"f0_hz":f0,"durations_seconds":[.4],"intonation":False},"expected_duration_seconds":.4})
    for a in VOWELS:
        for b in VOWELS:
            if a!=b: tasks.append({"id":f"vv-{a}{b}","stage":"P3","kind":"transition","phonemes":[a,b],"prosody":{"durations_seconds":[.18,.18],"intonation":False}})
    for c in ("m","n","s","sh","h","f","p","t","k","b","d","g","z","j","ts","ch","r","w","y","N"):
        for v in ("a","i"):
            for direction in ("CV","VC"):
                phones=[c,v] if direction=="CV" else [v,c]
                tasks.append({"id":f"{direction}-{c}-{v}","stage":"P3","kind":"consonant","family":c,"phonemes":phones,"prosody":{"intonation":False}})
    sentences=["あおいそら", "あめがふる", "ねこがあるく", "かぜがふく", "はながさく", "みずをのむ", "おとがきこえる", "しろいくも", "きってをはる", "がっこうへいく", "ほんをよむ", "きょうわはれ", "ゆっくりはなす", "ちずをみる", "あさのひかり", "こんばんは"]
    for i,text in enumerate(sentences):
        tasks.append({"id":f"sentence-{i:02}","stage":"P4","kind":"sentence","text":text,"phonemes":kana_to_phonemes(text),"prosody":{"accent_nucleus":2}})
    return {"version":"tasks-v1","language":"ja","phones":"OpenJTalk系の記号。sh/ts/ch/j、N=撥音、Q=促音。I/U=無声化母音",
            "tasks":tasks,"unknown_input_policy":"かな/明示音素のみ。漢字・未知記号の失敗も分母に計上する"}


def inventory(output):
    output.mkdir(parents=True,exist_ok=True)
    if (output/"splits.json").exists():
        return read(output/"splits.json")
    artifacts=[]; used_speakers=set(); used_sentences=set(); mentions=[]
    for directory in (REPO/"research/experiments",REPO/"research/scripts",REPO/"research/notebooks",REPO/"docs"):
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or ROOT in path.parents or ".venv" in path.parts or ".cache" in path.parts:
                continue
            if path.suffix not in (".json",".jsonl",".csv",".md",".py",".ipynb") or path.stat().st_size>32_000_000:
                continue
            text=path.read_text(errors="replace")
            speakers=set(re.findall(r"jvs\d{3}",text,re.I)); sentences=set(re.findall(r"VOICEACTRESS100_\d{3}",text))
            used_speakers.update(s.lower() for s in speakers); used_sentences.update(sentences)
            if speakers or sentences:
                mentions.append({"path":str(path.relative_to(REPO)),"speakers":sorted(speakers),"sentences":sorted(sentences),"sha256":file_hash(path)})
            if path.name in ("manifest.json","analysis.json","decision.json","responses.csv","aggregate.json") or path.suffix==".py":
                artifacts.append({"path":str(path.relative_to(REPO)),"sha256":file_hash(path),"bytes":path.stat().st_size,"role":"legacy-regression","method":"既存結果の再認定なし"})
    corpus=REPO/"research/data/raw/reference/JVS/jvs_ver1"
    metadata={}
    meta_path=corpus/"gender_f0range.txt"
    if meta_path.is_file():
        for line in meta_path.read_text().splitlines()[1:]:
            fields=line.split()
            if len(fields)==4:metadata[fields[0]]={"corpus_gender_label":fields[1],"corpus_f0_range_hz":[float(x) for x in fields[2:]]}
    speakers=[p.name for p in sorted(corpus.glob("jvs[0-9][0-9][0-9]")) if p.name not in used_speakers and (p/"parallel100/wav24kHz16bit").is_dir()]
    sentence_ids=[f"VOICEACTRESS100_{n:03}" for n in range(1,101) if f"VOICEACTRESS100_{n:03}" not in used_sentences]
    split={"version":"split-v1","created_utc":now(),"source":"JVS parallel100","license_url":"https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus",
           "history_evidence":mentions,"legacy_speakers":sorted(used_speakers),"legacy_sentences":sorted(used_sentences),"groups":{},
           "independence_status":"repository-audited-only","limitations":["リポジトリ外の閲覧・使用履歴は証明できない。独立性は保存履歴に対してのみ監査済み。","JVS境界は自動alignmentで、正解ラベルとして扱わない。","UTAUは旧使用履歴のある外部回帰群。新規確認には使わない。"]}
    assigned=set()
    for index,(name,size) in enumerate((("development",6),("selection",3),("confirmation",3))):
        texts=sentence_ids[index*4:(index+1)*4]
        chosen=[s for s in speakers if s not in assigned and all((corpus/s/"parallel100/wav24kHz16bit"/(t+".wav")).is_file() and (corpus/s/"parallel100/lab/mon"/(t+".lab")).is_file() for t in texts)][:size]
        assigned.update(chosen)
        records=[]
        for speaker in chosen:
            for sentence in texts:
                wav=corpus/speaker/"parallel100/wav24kHz16bit"/(sentence+".wav")
                lab=corpus/speaker/"parallel100/lab/mon"/(sentence+".lab")
                if not wav.is_file() or not lab.is_file(): continue
                labels=[line.split() for line in lab.read_text().splitlines() if len(line.split())==3]
                records.append({"id":speaker+"-"+sentence,"speaker":speaker,"sentence":sentence,
                                "wav":str(wav.relative_to(REPO)),"lab":str(lab.relative_to(REPO)),"sha256":file_hash(wav),"label_sha256":file_hash(lab),
                                "phone_counts":dict(Counter(row[2] for row in labels)),"alignment":"automatic-unverified"})
                records[-1]["recording_condition"]="JVS parallel100 normal phonation, wav24kHz16bit"
                records[-1]["speaker_metadata"]=metadata.get(speaker,{})
        split["groups"][name]={"speakers":chosen,"sentence_ids":texts,"records":records,"speaker_count":len(chosen)}
    split["speaker_generalization_available"]=all(len(split["groups"][key]["speakers"])>=count for key,count in [("development",6),("selection",3),("confirmation",3)])
    # 最終確認の音声ハッシュはP0で固定。その後はconfirmだけが音声を読む。
    with (output/"inventory.jsonl").open("x") as f:
        from .io import canonical
        for row in artifacts: f.write(canonical(row)+"\n")
    write_once(output/"splits.json",split)
    write_once(output/"task-suite.json",task_suite())
    write_once(output/"budget.json",read(ROOT/"config/campaign-v1.json")["budget"])
    write_once(output/"generation-policy.json",read(ROOT/"config/export-policy-v1.json"))
    return split
