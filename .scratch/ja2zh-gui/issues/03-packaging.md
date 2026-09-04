# 03-packaging

Type: grilling
Status: resolved (2026-09-05, agent 按推荐推进，用户可重开改判)
Blocked by:

## Question

GUI 工具怎么打包成 Windows 可双击运行的形态？单 exe？portable 文件夹？

### 背景

用户要「像软件那样」。选项：
- PyInstaller `--onefile` 单 exe（但 torch/TF 依赖在 WSL 侧不进包，包只是 GUI 壳+WSL 调用器）
- portable 文件夹（exe + 依赖文件夹）
- 不打包，直接 .bat + Python 脚本（但用户说「像软件那样」）

### 关键约束

GUI 本身只是壳，真正的重依赖（whisper/funasr/TF）在 WSL venv 里。所以打包的 exe 只需包含 GUI 框架 + subprocess 调用 wsl.exe 的逻辑，体积应该很小。

## Answer

**定稿：PyInstaller `--onefile` 单 exe**，名字沿用「视频转中文字幕」，默认图标，仅本机自用。三个决策点均按推荐推进（提问面板未获用户选择，任何一项可重开改判）：

### 决策树

1. **打包形态：单 exe（onefile）** ✅推荐推进
   - 依据：01 票实测 PyInstaller onefile 48.5MB、产物运行全绿（含 WSL 调用）；用户核心诉求「像软件那样」——桌面双击单文件最贴合；portable 文件夹形态的启动优势（免解压）对 9 秒级任务无感，而文件堆削弱软件感。
   - 接受的代价：每次启动解压到临时目录，首启慢 1-2 秒。
2. **名字与图标：「本译道人.exe」+ 像素风道士 .ico**（用户 2026-09-05 亲定，覆盖此前的推荐推进项）
   - 名字含义（用户原话）：本地部署大模型翻译有道行的人；与 GitHub 仓库名 benyidaoren 一致。
   - 图标：像素风道士（黑混元巾+金簪、深青道袍、胸口太极、深色圆角底板），32x32 手绘生成多尺寸 ico，已入库 `gui/assets/benyidaoren.ico`；打包参数 `--icon gui/assets/benyidaoren.ico`。
3. **分发范围：仅本机自用** ✅推荐推进
   - 依据：destination 就是给自己的本地工具；exe 是壳（Windows 侧），宿主（WSL venv+模型）不会跟着 exe 走，拷去他机必然缺环境——那是 06-wsl-dependency-check 的检测引导要兜的场景，本票不扩大范围。

### 实施要点（移交实施期）

- 壳内零重依赖：PySide6 + 调用逻辑（02 票方案），`--onefile --noconsole --name 视频转中文字幕`；`--noconsole` 去黑窗后日志全走 GUI 日志区，调试期可先不带该参数。
- 打包机：`py -3.11` 的 venv（01 票环境事实），清华源装 pyinstaller。
- 宿主环境（WSL venv/模型/脚本）不进包、不随 exe 走——壳启动时的存在性检查归 06 票。
