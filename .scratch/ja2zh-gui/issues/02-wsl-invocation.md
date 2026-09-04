# 02-wsl-invocation

Type: research
Status: resolved (2026-09-04, 实测定稿)
Blocked by:

## Question

GUI 从 Windows 侧如何调用 WSL 流水线？直接 subprocess 调 wsl.exe，还是有更好的桥接方式？

### 背景

当前 bat 脚本用 `wsl.exe -d Ubuntu -- bash -lc "python3 ..."` 调用。GUI 版本需要：
- 捕获 stdout/stderr 实时流式输出到界面（进度+日志）
- 传递 Windows 文件路径（需 wslpath 转换）
- 检测 WSL 是否可用、Ubuntu 是否存在
- 错误时给用户可读提示（不是 raw stderr）

## Answer

已实测验证（真机 WSL2 + wsl.exe 互操作）：

- **调用姿势**：`C:\Windows\System32\wsl.exe` 全路径 + 参数 list 传（不拼 bash -c 字符串）+ `text=True, bufsize=1, encoding="utf-8", errors="replace"` + stdout/stderr 分开读（stderr 起线程防 pipe 塞满死锁）+ `env["WSL_UTF8"]="1"`（修 wsl.exe 自身报错的 UTF-16 乱码）+ `creationflags=CREATE_NO_WINDOW`
- **路径转换**：用 `wslpath`（实测支持空格/中文；手动 /mnt/c 映射在非 C 盘/特殊挂载下会错）
- **预检**：一条 bash 合并探测 `command -v python3 && (exec 3<>/dev/tcp/127.0.0.1/8888)`，~1-2s
- **错误映射**：FileNotFoundError→未装 WSL；rc==255→wsl.exe 层错误（发行版不存在，与 Linux 退出码冲突，流水线自写退出码须避开 255）；probe stderr 含 Connection refused→llama-server:8888 没起；其他 rc!=0→透传 stderr 末 5 行（流水线自带分阶段自检日志）
