#!/usr/bin/env python3
"""
日语视频 → 中文字幕 全流程工具（ja2zh-subtitle）
用法:
  python ja2zh_subtitle.py <视频文件> [--out 输出目录] [--ja] [--keep-ja]
流程: 抽音频 → whisper-large-v3 ASR(词级时间戳) → CAM++声纹聚类+短段传播(说话人)
      → inaSpeechSegmenter 性别判定 → 同人相邻合并 → Hy-MT2-7B 翻译 → SRT(去引号)
输出: <视频名>.zh.srt (纯中文字幕)  [--keep-ja 时同时输出 <视频名>.ja.srt]
依赖: ~/venvs/subtitle-pipeline (faster-whisper, funasr, inaspeechsegmenter, sklearn, av, soundfile)
模型: ~/models/asr/whisper-large-v3, ~/models/asr/campplus, ~/models/translation/hy-mt2-7b
翻译服务: 需先启动 llama-server (hy-mt2-7b @ 127.0.0.1:8888), 本工具会自动拉起/复用
"""
import argparse, json, os, random, re, shutil, socket, subprocess, sys, time

HOME = os.path.expanduser("~")
PY = f"{HOME}/venvs/subtitle-pipeline/bin/python3"
SERVER_BIN = f"{HOME}/projects/llama-dflash2/llama.cpp/build/bin/llama-server"
MODEL_ASR = f"{HOME}/models/asr/whisper-large-v3"
MODEL_SPK = f"{HOME}/models/asr/campplus/campplus_cn_common.bin"
MODEL_MT = f"{HOME}/models/translation/hy-mt2-7b/Hy-MT2-7B-Q4_K_M.gguf"
PORT = 8888
TMP = "/tmp/ja2zh"

def sh(cmd, **kw):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(f"[ERR] {r.stdout[-800:]}{r.stderr[-800:]}", file=sys.stderr)
        sys.exit(1)
    return r.stdout

# ---------- 0. 服务管理 ----------
def server_ready(port, check_model=False):
    try:
        r = subprocess.run(["curl", "-s", "-m", "2", f"http://127.0.0.1:{port}/v1/models"],
                           capture_output=True, text=True)
        if '"data"' not in r.stdout:
            return False
        # 端口可能常驻其他 llama-server 实例, 复用前必须确认是本工具的 Hy-MT2
        return (not check_model) or ("hy-mt" in r.stdout.lower())
    except Exception:
        return False

def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0

def ensure_server():
    global PORT
    if server_ready(8888, check_model=True):
        PORT = 8888
        print("[0/6] 翻译服务已在运行 (8888)")
        return None
    if server_ready(8888):
        print("      8888 被其他服务占用, 换端口 ...")
    print("[0/6] 启动翻译服务 Hy-MT2-7B ...")
    # 8888 附近常被占 (用户环境), 直接随机选不常用段 20000-32767 (避开 ephemeral)
    for _ in range(5):
        port = random.randint(20000, 32767)
        if not port_free(port):
            continue
        proc = subprocess.Popen([SERVER_BIN, "--model", MODEL_MT, "--n-gpu-layers", "999",
            "--ctx-size", "8192", "--flash-attn", "on", "--host", "127.0.0.1", "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            time.sleep(2)
            if server_ready(port, check_model=True):
                PORT = port
                print(f"      服务就绪 (端口 {port})")
                return proc
        proc.terminate()
    print("[ERR] 翻译服务启动失败 (多次换端口均超时)", file=sys.stderr); sys.exit(1)

# ---------- 1. 抽音频 ----------
def extract_audio(video, wav):
    print("[1/6] 抽取音频 16kHz ...")
    r = subprocess.run(["ffmpeg", "-y", "-i", video, "-ar", "16000", "-ac", "1", wav],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERR] ffmpeg 失败: {r.stderr[-500:]}", file=sys.stderr); sys.exit(1)

# ---------- 2-4. ASR + 说话人 + 性别 (在 venv python 子进程跑) ----------
PIPELINE = r'''
import warnings, json, sys, os
warnings.filterwarnings("ignore")
import numpy as np

wav = sys.argv[1]
out = sys.argv[2]

# --- ASR ---
from faster_whisper import WhisperModel
asr = WhisperModel("%s", device="cuda", compute_type="float16")
segments, info = asr.transcribe(wav, language="ja", word_timestamps=True,
    vad_filter=True, condition_on_previous_text=False, beam_size=5)
seg_list = [{"start": round(s.start,2), "end": round(s.end,2), "text": s.text.strip()} for s in segments]
print(f"ASR: {len(seg_list)} 段", flush=True)

# --- 音频载入(归一化铁律) ---
import av
c = av.open(wav); st = c.streams.audio[0]; sr = st.rate
audio = np.concatenate([f.to_ndarray().flatten() for f in c.decode(st)]).astype(np.float32)
if np.abs(audio).max() > 1.5: audio = audio / 32768.0

def clip(s, e, pad=0.75):
    a = max(0, int((s-pad)*sr)); b = min(len(audio), int((e+pad)*sr))
    return audio[a:b]
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0

# --- 声纹: 长段 CAM++ ---
from funasr import AutoModel
spk = AutoModel(model="CAMPPlus", model_path="%s", disable_update=True, log_level="ERROR")
LONG = 4.0
long_idx, embs = [], []
for i, s in enumerate(seg_list):
    if s["end"]-s["start"] >= LONG and rms(clip(s["start"], s["end"])) > 0.01:
        r = spk.generate(input=clip(s["start"], s["end"]), fs=sr, output_dir=None)
        e = r[0]["spk_embedding"]
        if hasattr(e, "cpu"): e = e.cpu()
        embs.append(np.array(e).flatten()); long_idx.append(i)
print(f"长段声纹: {len(long_idx)}", flush=True)

from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
X = normalize(np.stack(embs))
km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(X)
lab = km.labels_
if max(np.bincount(lab, minlength=2)) / max(np.bincount(lab, minlength=2).min(),1) > 5:
    sim = X @ X.T
    i0, j0 = np.unravel_index(np.argmin(sim), sim.shape)
    sa, sb = X[i0], X[j0]
    lab = np.array([0 if x@sa >= x@sb else 1 for x in X])

# --- 锚点传播到全段 ---
import bisect
anchor = {i: int(lab[k]) for k, i in enumerate(long_idx)}
labels = [-1]*len(seg_list)
for i, l in anchor.items(): labels[i] = l
anch = sorted(anchor)
def near(i):
    p = bisect.bisect_left(anch, i); cand = []
    if p>0: cand.append(anch[p-1])
    if p<len(anch): cand.append(anch[p])
    return min(cand, key=lambda j: abs(seg_list[j]["start"]-seg_list[i]["start"]))
for i in range(len(seg_list)):
    if labels[i]==-1: labels[i] = labels[near(i)]

# --- 性别: 独立进程 (TF 不能与 torch 同进程, 拆出去) ---
# 由外层主进程在 run_pipeline 后单独调用 gender_stage.py
out_rows = [{"start": s["start"], "end": s["end"],
             "speaker": "?", "text": s["text"]} for i, s in enumerate(seg_list)]
json.dump({"seg_list": seg_list, "labels": labels, "long_idx": long_idx,
           "out_rows": out_rows},
          open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("PIPELINE OK", flush=True)
''' % (MODEL_ASR, MODEL_SPK)

# 性别判定独立进程脚本 (纯 TF, CPU, 关 XLA)
GENDER_STAGE = r'''
import warnings, json, sys, os
warnings.filterwarnings("ignore")
os.environ["CUDA_VISIBLE_DEVICES"]=""; os.environ["TF_XLA_FLAGS"]="--tf_xla_auto_jit=0"
os.environ["TF_ENABLE_ONEDNN_OPTS"]="0"
import tensorflow as tf; tf.config.optimizer.set_jit(False)
import numpy as np, soundfile as sf
from inaSpeechSegmenter import Segmenter
gseg = Segmenter()

data = json.load(open(sys.argv[1], encoding="utf-8"))
seg_list, labels = data["seg_list"], data["labels"]
long_idx = data["long_idx"]

import av
c = av.open(sys.argv[2]); st = c.streams.audio[0]; sr = st.rate
audio = np.concatenate([f.to_ndarray().flatten() for f in c.decode(st)]).astype(np.float32)
if np.abs(audio).max() > 1.5: audio = audio / 32768.0

def clip(s, e, pad=0.1):
    a = max(0, int((s-pad)*sr)); b = min(len(audio), int((e+pad)*sr))
    return audio[a:b]

votes = {0:{"male":0,"female":0}, 1:{"male":0,"female":0}}
for i in long_idx[:20]:
    s = seg_list[i]
    w = clip(s["start"], s["end"])
    if len(w) < int(0.5*sr): continue
    sf.write("/tmp/_g.wav", w, sr)
    g = gseg("/tmp/_g.wav")
    d = {"male":0.0,"female":0.0}
    for gg in g:
        if gg[0] in d: d[gg[0]] += float(gg[2])-float(gg[1])
    if d["male"]+d["female"] > 0.3:
        votes[labels[i]]["male" if d["male"]>d["female"] else "female"] += 1
c2g = {c: ("male" if votes[c]["male"]>=votes[c]["female"] else "female") for c in (0,1)}
print(f"性别投票: {votes} -> {c2g}", flush=True)

out_rows = data["out_rows"]
for i, s in enumerate(seg_list):
    out_rows[i]["speaker"] = "female" if c2g[labels[i]]=="female" else "male"
json.dump(out_rows, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
print("GENDER OK", flush=True)
'''

def run_pipeline(wav, out_json):
    print("[2/6] ASR + 说话人 (40min视频约6分钟) ...")
    pipe = os.path.join(TMP, "pipeline.py")
    open(pipe, "w", encoding="utf-8").write(PIPELINE)
    stage1 = out_json + ".stage1"
    r = subprocess.run([PY, pipe, wav, stage1], capture_output=True, text=True)
    for ln in r.stdout.strip().splitlines():
        if ln.strip(): print("      " + ln)
    if r.returncode != 0 or "PIPELINE OK" not in r.stdout:
        print(f"[ERR] 流水线失败:\n{r.stdout[-600:]}{r.stderr[-600:]}", file=sys.stderr); sys.exit(1)

    print("[3/6] 性别判定 (独立进程) ...")
    gs = os.path.join(TMP, "gender.py")
    open(gs, "w", encoding="utf-8").write(GENDER_STAGE)
    r2 = subprocess.run([PY, gs, stage1, wav, out_json], capture_output=True, text=True)
    for ln in r2.stdout.strip().splitlines():
        if ln.strip(): print("      " + ln)
    if r2.returncode != 0 or "GENDER OK" not in r2.stdout:
        print(f"[ERR] 性别判定失败:\n{r2.stdout[-600:]}{r2.stderr[-600:]}", file=sys.stderr); sys.exit(1)

# ---------- 5. 翻译 ----------
CTX = "背景：日剧对白字幕，两位角色：女性上司与男性下属（职场日常对话）。"
KANA = re.compile(r"[ぁ-ゖァ-ヺー]")

def translate_one(ja, speaker):
    role = "女上司" if speaker == "female" else "男下属"
    payload = {"messages": [{"role": "user",
        "content": f"{CTX}以下是{role}说的话。将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n`{ja}`"}],
        "max_tokens": 200, "temperature": 0.1}
    r = subprocess.run(["curl", "-s", "-m", "60", f"http://127.0.0.1:{PORT}/v1/chat/completions",
        "-H", "Content-Type: application/json", "-d", json.dumps(payload, ensure_ascii=False)],
        capture_output=True, text=True)
    try:
        return json.loads(r.stdout)["choices"][0]["message"]["content"].strip().strip("`").split("\n")[0].strip()
    except Exception:
        return ""

def fmt(t):
    t = float(t); h = int(t//3600); m = int((t%3600)//60); s = t%60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s-int(s))*1000)):03d}"

def write_srt(path, items):
    lines = []
    for i, (a, b, text) in enumerate(items, 1):
        text = re.sub(r"[“”「」『』\"]", "", text)   # 去引号
        lines += [str(i), f"{fmt(a)} --> {fmt(b)}", text, ""]
    open(path, "w", encoding="utf-8").write("\n".join(lines))

def translate_stage(diar_json, out_zh, out_ja, keep_ja):
    print("[4/6] 合并同人相邻段 ...")
    diar = json.load(open(diar_json, encoding="utf-8"))
    merged = []
    for s in diar:
        if merged and merged[-1]["speaker"] == s["speaker"] \
           and s["start"] - merged[-1]["end"] < 2.0 \
           and s["end"] - merged[-1]["start"] < 7.0:
            merged[-1]["text"] += s["text"]; merged[-1]["end"] = s["end"]
        else:
            merged.append(dict(s))
    print(f"      {len(diar)} → {len(merged)} 段")

    print("[5/6] 时间轴精修（起点对齐语音、时长随文本） ...")
    # 起点不动（ASR start 即语音起点），结束=起点+max(2.5, 字数*速率) 上限8s
    jp_items, zh_items = [], []
    zh_all = [None] * len(merged)

    print("[6/6] Hy-MT2 翻译 ...")
    from concurrent.futures import ThreadPoolExecutor
    def work(k):
        m = merged[k]
        ja = m["text"].replace("\n", " ").strip()
        if not ja or len(ja) <= 1:
            return k, ja
        zh = translate_one(ja, m["speaker"])
        if not zh or KANA.search(zh):
            zh2 = translate_one(ja, m["speaker"])
            if zh2 and not KANA.search(zh2): zh = zh2
            elif not zh: zh = ja
        return k, zh
    with ThreadPoolExecutor(max_workers=4) as ex:
        for k, zh in ex.map(work, range(len(merged))):
            zh_all[k] = zh
            if (k+1) % 50 == 0: print(f"      ...{k+1}/{len(merged)}")

    for k, m in enumerate(merged):
        ja_len = len(re.sub(r"\s", "", m["text"]))
        zh_len = len(re.sub(r"\s", "", zh_all[k]))
        need = max(2.5, ja_len*0.16, zh_len*0.22)
        a = m["start"]
        b = min(max(a + need, m["end"] - 1.0), a + 8.0)  # 语音尾前1s内收，保底need，上限8s
        jp_items.append((a, b, m["text"]))
        zh_items.append((a, b, zh_all[k]))

    write_srt(out_zh, zh_items)
    print(f"完成: {out_zh} ({len(zh_items)} 条)")
    if keep_ja:
        write_srt(out_ja, jp_items)
        print(f"同时输出: {out_ja}")

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="日语视频 → 中文字幕")
    ap.add_argument("video", help="视频文件路径 (Windows路径亦可)")
    ap.add_argument("--out", default=None, help="输出目录 (默认=视频所在目录)")
    ap.add_argument("--keep-ja", action="store_true", help="同时输出日语SRT")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        print(f"[ERR] 文件不存在: {video}", file=sys.stderr); sys.exit(1)
    outdir = args.out or os.path.dirname(video)
    base = os.path.splitext(os.path.basename(video))[0]
    out_zh = os.path.join(outdir, f"{base}.zh.srt")
    out_ja = os.path.join(outdir, f"{base}.ja.srt")
    os.makedirs(TMP, exist_ok=True)
    wav = os.path.join(TMP, "audio16k.wav")

    srv = ensure_server()
    try:
        extract_audio(video, wav)
        diar_json = os.path.join(TMP, "diar.json")
        run_pipeline(wav, diar_json)
        translate_stage(diar_json, out_zh, out_ja, args.keep_ja)
    finally:
        if srv:
            print("停止翻译服务 ...")
            srv.terminate()
    print("\n[OK] 全流程完成")

if __name__ == "__main__":
    main()
