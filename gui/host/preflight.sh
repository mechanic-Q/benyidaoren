# 06 票全检清单: (标签, wsl 内路径)。脚本常驻 WSL 侧, GUI 仅以静态 argv 调用,
# 避免 wsl.exe 传参对 $变量/双引号/分号 复杂脚本的失真 (2026-09-05 实测)。
for p in \
  /home/lmr/venvs/subtitle-pipeline/bin/python3 \
  /home/lmr/models/asr/whisper-large-v3 \
  /home/lmr/models/asr/campplus/campplus_cn_common.bin \
  /home/lmr/models/translation/hy-mt2-7b/Hy-MT2-7B-Q4_K_M.gguf \
  /home/lmr/projects/llama-dflash2/llama.cpp/build/bin/llama-server
do
  if [ -e "$p" ]; then
    echo "OK $p"
  else
    echo "MISS $p"
  fi
done
curl -sm2 http://127.0.0.1:8888/v1/models | grep -qi "hy-mt" && echo "SRV hy-mt@8888" || {
  curl -sm2 http://127.0.0.1:8888/v1/models >/dev/null 2>&1 && echo "SRV other@8888" || echo "SRV free"
}
