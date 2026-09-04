## Destination

一个 Windows 桌面 GUI 工具：用户把日语视频文件拖进去（或通过文件选择器选中），工具自动执行全流程（ASR→说话人→性别→合并→翻译），结束后在视频同目录输出中文字幕 SRT。界面可见、有进度显示、出错有提示。底层复用已验证的 WSL 流水线。

## Notes

- 领域：Python/WSL2 流水线 + Windows 桌面 GUI
- 底层流水线已建成并端到端验证通过：`~/tools/ja2zh_subtitle/ja2zh_subtitle.py`（6 阶段，60 秒样本测试 OK）
- Windows 入口 `视频转中文字幕.bat` 已验证可调用 WSL
- 硬件：RTX 5080 16GB，WSL2 Ubuntu，7950X 128GB RAM
- 模型全部本地：whisper-large-v3、CAM++、Hy-MT2-7B（llama-server @8888）
- 用户偏好：纯文本无 emoji，国内源下载，独立 venv 隔离
- 每会话先读本 map 再选 ticket

## Decisions so far

- [05-bat-repair-verification](issues/05-bat-repair-verification.md) — CLI 链路已修复并端到端验证（60 秒样本全流程通过）；剩用户真实拖拽操作一次确认
- [02-wsl-invocation](issues/02-wsl-invocation.md) — 已实测定稿：wsl.exe 全路径+list 传参+WSL_UTF8=1+utf-8 流式+stderr 线程防死锁+wslpath 转路径+rc=255=WSL 层错误映射

## Not yet specified

- GUI 框架选型后的具体界面布局：进度条放哪、日志窗口多大、是否需要设置页（改模型路径等）——等框架定了再细化
- 是否需要支持批量多视频队列——用户只说了「放文件进去就执行」，先单文件，批量是 fog
- 打包分发方式（单 exe？安装包？portable？）——等框架定后才知道打包难度
- WSL 依赖检测和引导：用户换电脑或重装 WSL 时 GUI 如何提示缺少依赖

## Out of scope

- 实时翻译/同声传译（用户明确要的是事后出字幕，不是实时）
- 非日语视频支持（当前流水线硬编码 ja，扩展是多语言话题，不属本次）
