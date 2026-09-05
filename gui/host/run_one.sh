# 单任务执行: GUI 传 1 个 wsl 路径参数。脚本常驻 WSL 侧, 参数经 "$1" 原样引用。
exec python3 /home/lmr/tools/ja2zh_subtitle/ja2zh_subtitle.py "$1" --keep-ja
