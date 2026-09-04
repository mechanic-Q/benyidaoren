# 01-gui-framework

Type: research
Status: resolved (2026-09-05, 双候选本机实测对比，用户亲选 PySide6)
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

**定稿：PySide6**（LGPL），PyInstaller 打包单 exe。2026-09-05 重开后升级为本机实测对比：双候选（PySide6 / Tkinter+tkinterdnd2）均实测到打包产物运行全绿，由用户亲选 PySide6。

### 本机实测对比（2026-09-05，Windows py3.11 venv，清华源）

| 维度 | PySide6 6.11.2 | Tkinter 8.6 + tkinterdnd2 0.6.2 |
|---|---|---|
| 清华源安装 | 顺利 | 顺利 |
| GUI 启动+拖拽注册 | 通过（原生 setAcceptDrops） | 通过（tkdnd 扩展加载成功） |
| 调用 WSL | QProcess rc=0，0.2s | subprocess rc=0 |
| onefile exe 体积 | 48.5 MB | 11.2 MB |
| 打包产物运行 | 全绿（含 WSL 调用） | 全绿（tkdnd 打包存活） |
| 观感 | 现代原生（vista/Fusion） | 陈旧（95 风） |
| 流式日志/进度机制 | signal/slot 回主线程，现成 | 需手写 queue + after 轮询 |

### 关键实测发现

- **tkinterdnd2 打包易碎点已排除**：pyinstaller-hooks-contrib 2026.7 已内置 hook，tkdnd 拖拽扩展打包后加载正常，无需手工处理——Tkinter 是实测可行的对照组，不是纸面排除。
- **QProcess 直接承载 02 票方案**：GUI 进程内 `wsl.exe 全路径 + list 传参`，stdout 回读实测通过，打包产物同样通过。
- 选 PySide6 的决定性因素：观感契合「像软件那样」的核心诉求；流式日志+分阶段进度的线程回主线程刷新机制现成；后续设置页/引导向导组件齐全。

### 排除项

- **Web UI（Flask/Gradio）** — 浏览器形态，不符桌面程序诉求
- **Electron/Tauri** — 引入 Node/Rust 工具链，Python 背景维护成本最高
- **PyQt6** — API 与 PySide6 几乎一致，许可 GPL/商业双轨，无优势
- **Tkinter+tkinterdnd2** — 实测可行，因观感与 UI 机制让位；若后续 PySide6 遇墙仍是 fallback

### 环境事实（后续票依赖）

- Windows 侧双 Python：anaconda3 3.13.0（PATH 默认）+ 独立安装 3.11.6（py 启动器默认）
- GUI 依赖独立 venv，基于 `py -3.11`，清华源安装 PySide6 + PyInstaller
