# CONTEXT

术语表（领域词汇，非实现细节）。

- **壳（shell）**：运行在 Windows 侧的 GUI 程序。只负责界面、任务发起与结果展示，自身不具备识别或翻译能力。
- **宿主（host）**：WSL Ubuntu 内的流水线环境，含 venv、模型（whisper-large-v3 / CAM++ / Hy-MT2-7B）与 `ja2zh_subtitle.py`。重依赖全部在宿主，永不进入壳的分发包。
- **任务（task）**：一次「日语视频 → 中日双字幕 SRT」的转换。由壳发起、宿主执行，产出写到视频同目录。
