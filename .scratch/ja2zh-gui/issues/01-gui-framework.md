# 01-gui-framework

Type: research
Status: claimed (2026-09-04, research subagent dispatched)
Blocked by:

## Question

选哪个 GUI 框架能让工具在 Windows 上有可见可交互界面、且能调用 WSL 流水线？

### 背景

当前工具是 `~/tools/ja2zh_subtitle/ja2zh_subtitle.py`（Python CLI），通过桌面 `视频转中文字幕.bat` 调用 WSL 执行。用户要求「像软件那样的可见、可交互的前端界面，运行在 Windows 上」。

### 候选方向（需调研后决策）

1. **PyQt/PySide6** — 成熟桌面 GUI，可做拖拽+进度条+日志窗口，Python 原生，PyInstaller 打包成 exe
2. **Tkinter** — Python 自带零依赖，界面朴素但功能够（拖拽+进度条），打包最轻
3. **Web UI（Flask/FastAPI + 浏览器）** — 本地起服务，浏览器打开界面，跨平台天然，但不像「软件」
4. **Electron/Tauri** — 前端技术栈，体验最好但重（Tauri 需 Rust 工具链）
5. **Gradio** — 最简拖拽上传+进度+输出，但界面定制度低

### 决策标准

- Windows 原生窗口体验（拖拽文件入窗口即开始）
- 有进度条和实时日志显示
- 能 subprocess 调用 WSL bash 命令
- 打包成单 exe 可行（用户要「像软件那样」）
- 维护成本低（用户是 Python 背景，非前端）

## Answer

（待填）
