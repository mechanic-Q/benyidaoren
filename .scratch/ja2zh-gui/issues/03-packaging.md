# 03-packaging

Type: grilling
Status: open
Blocked by: 01

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

（待填）
