## Destination

一个 Windows 桌面 GUI 工具：用户把日语视频文件拖进去（或通过文件选择器选中），工具自动执行全流程（ASR→说话人→性别→合并→翻译），结束后在视频同目录输出**中文 + 日语双字幕 SRT**。界面可见、有进度显示、出错有提示。底层复用已验证的 WSL 流水线。

## Notes

- 领域：Python/WSL2 流水线 + Windows 桌面 GUI
- 底层流水线已建成并端到端验证通过：`~/tools/ja2zh_subtitle/ja2zh_subtitle.py`（6 阶段，60 秒样本测试 OK）
- Windows 入口 `视频转中文字幕.bat` 已验证可调用 WSL
- 硬件：RTX 5080 16GB，WSL2 Ubuntu，7950X 128GB RAM
- 模型全部本地：whisper-large-v3、CAM++、Hy-MT2-7B（llama-server @8888）
- 用户偏好：纯文本无 emoji，国内源下载，独立 venv 隔离
- 每会话先读本 map 再选 ticket
- 实施状态 (2026-09-05): 正式版已交付——gui/benyidaoren.py (壳) + ja2zh_subtitle.py (宿主端口自适应) 改造完成, 端到端实测通过 (8888 被占自动换 31483, 翻译质量在线), 本译道人.exe (48.5MB) 已部署桌面待用户验收

## Decisions so far

- [05-bat-repair-verification](issues/05-bat-repair-verification.md) — CLI 链路已修复并端到端验证（60 秒样本全流程通过）；剩用户真实拖拽操作一次确认
- [02-wsl-invocation](issues/02-wsl-invocation.md) — 已实测定稿：wsl.exe 全路径+list 传参+WSL_UTF8=1+utf-8 流式+stderr 线程防死锁+wslpath 转路径+rc=255=WSL 层错误映射
- [01-gui-framework](issues/01-gui-framework.md) — 定稿 PySide6（LGPL）：双候选本机实测到打包产物全绿后由用户亲选；QProcess 调 WSL 通过，onefile 48.5MB；Tkinter 对照同样全绿（11.2MB，tkdnd 打包存活）因观感让位，留作 fallback
- [04-ui-prototype](issues/04-ui-prototype.md) — 定稿 D 融合版：A 的单栏主体（拖拽+7 阶段进度+常驻日志）+ B 的任务队列栏（批量排队）；完成态输出中日双字幕（流水线 keep_ja 已支持，GUI 默认开启）；**深色主题**（全部颜色显式指定）；设置页/历史记录不做；原型在 gui/ui_prototype.py
- [03-packaging](issues/03-packaging.md) — 定稿 PyInstaller onefile 单 exe「**本译道人.exe**」（用户定名，48.5MB 实测）+ 像素道士 .ico（gui/assets/benyidaoren.ico）；仅本机自用；壳（Windows GUI）与宿主（WSL 流水线+模型）分离，宿主不进包
- [06-wsl-dependency-check](issues/06-wsl-dependency-check.md) — 定稿轻检启动（wsl+Ubuntu，<1s，缺→顶部黄条）+ 全检转换（venv/三模型，缺→内嵌错误卡+复制诊断+重试）；**8888 被占→随机不常用端口**（20000-32767 随机，避开 8888 顺延段；复用前校验 Hy-MT2 模型 id），端口项降为 GUI 信息性显示

## Not yet specified

（当前为空：原迷雾已全部 graduated 成票或并入现有票）

## Out of scope

- 实时翻译/同声传译（用户明确要的是事后出字幕，不是实时）
- 非日语视频支持（当前流水线硬编码 ja，扩展是多语言话题，不属本次）
- GUI 设置页、历史记录（04 票用户裁定只要批量队列，其余不做）
