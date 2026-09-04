# -*- coding: utf-8 -*-
"""[原型] ja2zh-gui 主窗口 UI 原型 —— 一次性代码，用于回答「主窗口长什么样」。

四个变体，运行后用窗口底部深色浮动条切换（← / → 键亦可）：
  D 融合版（默认） A 的单栏主体 + B 的任务队列栏 + 中日双字幕完成态（用户反馈合成）
  A 单栏流水线     大拖拽区 + 分段进度 chips + 可折叠日志
  B 监控台         左侧任务栏 + 右侧步骤条 + 终端式深色日志
  C 向导极简       居中大字步骤向导，日志收进可展开抽屉

所有运行数据为模拟（浮动条上的「模拟运行 / 模拟出错」触发），不调用真实 WSL。
运行: gui\\ui_prototype_launcher.bat（双击）
结论记录: .scratch/ja2zh-gui/issues/04-ui-prototype.md
"""
import os
import sys

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#4a8cff"
GREEN = "#3ddc97"
RED = "#ff6b6b"
TXT = "#e8eaed"
MONO = "Consolas"

# 真实流水线的 7 个阶段（ja2zh_subtitle.py 的 [0/6]..[6/6]），dur 为模拟时长(秒)
STAGES = [
    ("翻译服务", 0.8, [(0.10, "[0/6] 翻译服务 Hy-MT2-7B 检查 (8888) ..."),
                       (0.80, "[0/6] 翻译服务已在运行 (8888)")]),
    ("抽取音频", 1.0, [(0.10, "[1/6] 抽取音频 16kHz ..."),
                       (0.85, "ffmpeg: 输出 16000Hz 单声道 wav")]),
    ("ASR 说话人", 2.4, [(0.08, "[2/6] ASR + 说话人 (40min 视频约 6 分钟) ..."),
                         (0.50, "whisper-large-v3 加载完成 (本地)"),
                         (0.80, "ASR: 27 段"),
                         (0.95, "声纹聚类: 3 个说话人")]),
    ("性别判定", 1.0, [(0.15, "[3/6] 性别判定 (独立进程) ..."),
                       (0.90, "性别投票: spk0=F, spk1=M, spk2=M")]),
    ("合并段落", 0.8, [(0.20, "[4/6] 合并同人相邻段 ..."),
                       (0.85, "合并后 14 段")]),
    ("时间轴精修", 1.0, [(0.20, "[5/6] 时间轴精修 (起点对齐语音、时长随文本) ..."),
                         (0.90, "精修完成")]),
    ("翻译", 2.0, [(0.10, "[6/6] Hy-MT2 翻译 ..."),
                   (0.40, "批次 1/2 完成"),
                   (0.70, "批次 2/2 完成"),
                   (0.95, "输出 27 条中文字幕")]),
]
VIDEO_EXT = (".mp4", ".mkv", ".ts", ".avi", ".mov", ".webm", ".flv", ".wmv")

ERR_MSG = "WSL 调用失败 (rc=255)"
ERR_LOG = "[ERR] rc=255: WSL 层错误——无法连接 Ubuntu 发行版"
ERR_HINT = ("常见原因：WSL 未安装 / Ubuntu 未注册 / wsl 服务未启动。\n"
            "可在 PowerShell 运行 wsl --status 检查；重装后执行 wsl --update。")


# ---------------------------------------------------------------- 模拟器
class Sim(QObject):
    log_line = Signal(str)
    stage_changed = Signal(int)
    progress_changed = Signal(float)
    state_changed = Signal(str)      # idle / ready / busy / done / error
    file_changed = Signal(str)
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.file = ""
        self.stage_idx = -1
        self.progress = 0.0
        self.logs = []
        self.out_zh = ""
        self.out_ja = ""
        self.err = ""
        self.hint = ""
        self._events = []            # (t_ms, kind, payload)
        self._stage_bounds = []      # (start_ms, end_ms) per stage
        self._total_ms = 1
        self._ei = 0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # -- 对外操作 -------------------------------------------------------
    def set_file(self, path):
        self.file = path
        self._go("ready")
        self.file_changed.emit(path)

    def reset(self):
        self._timer.stop()
        self.state, self.file = "idle", ""
        self.stage_idx, self.progress = -1, 0.0
        self.logs, self.out_zh, self.out_ja = [], "", ""
        self.err, self.hint = "", ""
        self.state_changed.emit("idle")
        self.file_changed.emit("")
        self.stage_changed.emit(-1)
        self.progress_changed.emit(0.0)

    def start(self, fail=False):
        self._build_events(fail)
        self._ei = 0
        self._clock.start()
        self._timer.start()
        self._go("busy")

    # -- 内部 -----------------------------------------------------------
    def _go(self, state):
        self.state = state
        self.state_changed.emit(state)

    def _build_events(self, fail):
        ev, bounds = [], []
        t = 0.0                       # 秒；入队时统一转毫秒
        for i, (name, dur, logs) in enumerate(STAGES):
            start = t
            ev.append((int(start * 1000), "stage", i))
            for frac, text in logs:
                ev.append((int((start + frac * dur) * 1000), "log", text))
            if fail and i == 2:      # ASR 阶段中段失败
                ev.append((int((start + 0.45 * dur) * 1000), "log", ERR_LOG))
                ev.append((int((start + 0.55 * dur) * 1000),
                           "failed", (ERR_MSG, ERR_HINT)))
                t = start + 0.55 * dur
                bounds.append((int(start * 1000), int(t * 1000)))
                break
            t = start + dur
            bounds.append((int(start * 1000), int(t * 1000)))
        if not fail:
            self.out_zh = "D:\\videos\\示例_日语视频.zh.srt"
            self.out_ja = "D:\\videos\\示例_日语视频.ja.srt"
            ev.append((int((t + 0.3) * 1000), "finished", self.out_zh))
        ev.sort(key=lambda x: x[0])
        self._events = ev
        self._stage_bounds = bounds
        self._total_ms = bounds[-1][1] if bounds else 1

    def _tick(self):
        now = self._clock.elapsed()
        while self._ei < len(self._events) and self._events[self._ei][0] <= now:
            _, kind, payload = self._events[self._ei]
            self._ei += 1
            if kind == "log":
                self.logs.append(payload)
                self.log_line.emit(payload)
            elif kind == "stage":
                self.stage_idx = payload
                self.stage_changed.emit(payload)
            elif kind == "finished":
                self._timer.stop()
                self.progress = 1.0
                self.progress_changed.emit(1.0)
                self._go("done")
                self.finished.emit(payload)
                return
            elif kind == "failed":
                self._timer.stop()
                self.err, self.hint = payload
                self._go("error")
                self.failed.emit(*payload)
                return
        if self.state == "busy":
            p = 0.0
            for (s, e) in self._stage_bounds:
                if now >= e:
                    p = e / self._total_ms
                elif now > s:
                    p = now / self._total_ms
                    break
            self.progress = min(p, 0.999)
            self.progress_changed.emit(self.progress)


# ---------------------------------------------------------------- 公共小件
class DropZone(QFrame):
    """虚线拖拽区（三个变体各自实例化，acceptDrops + 真实文件选择）。"""
    file_chosen = Signal(str)

    def __init__(self, big, small=""):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("drop")
        self._hl(False)
        v = QVBoxLayout(self)
        v.addStretch(1)
        self.big = QLabel(big)
        self.big.setAlignment(Qt.AlignCenter)
        self.small = QLabel(small)
        self.small.setAlignment(Qt.AlignCenter)
        self.small.setStyleSheet("color:#9aa0a6; font-size:12px;")
        v.addWidget(self.big)
        v.addWidget(self.small)
        v.addStretch(1)

    def _hl(self, on):
        color = ACCENT if on else "#565b63"
        self.setStyleSheet(f"#drop {{ border: 2px dashed {color}; border-radius: 10px;"
                           " background:#1e2024; }}")
        if on:
            self.big.setStyleSheet(f"color:{ACCENT};")

    def set_texts(self, big, small=""):
        self.big.setText(big)
        self.big.setStyleSheet("")
        self.small.setText(small)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hl(True)

    def dragLeaveEvent(self, e):
        self._hl(False)

    def dropEvent(self, e):
        self._hl(False)
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.file_chosen.emit(u.toLocalFile())
                return

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择日语视频", "", "视频 (*.mp4 *.mkv *.ts *.avi *.mov *.webm)")
        if path:
            self.file_chosen.emit(path)


def chip_style(kind):
    if kind == "done":
        return ("QLabel { background:rgba(61,220,151,.16); color:%s; border-radius:9px;"
                " padding:3px 8px; font-size:11px; }" % GREEN)
    if kind == "cur":
        return ("QLabel { background:%s; color:white; border-radius:9px;"
                " padding:3px 8px; font-size:11px; font-weight:bold; }" % ACCENT)
    return "QLabel { background:#2a2d33; color:#8a9099; border-radius:9px; padding:3px 8px; font-size:11px; }"


def render_chips(labels, cur):
    out = []
    for i, name in enumerate(labels):
        lab = QLabel(name)
        lab.setStyleSheet(chip_style("done" if i < cur else "cur" if i == cur else "p"))
        lab.setAlignment(Qt.AlignCenter)
        lab.setFixedHeight(24)
        lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        out.append(lab)
    return out


def log_view(dark=False):
    v = QPlainTextEdit()
    v.setReadOnly(True)
    f = QFont(MONO, 9)
    v.setFont(f)
    if dark:
        v.setStyleSheet("QPlainTextEdit { background:#141414; color:#d4d4d4; }")
    return v


def append_log(view, line):
    if "[ERR]" in line:
        view.appendHtml(f'<span style="color:{RED};">{line}</span>')
    else:
        view.appendPlainText(line)


# ---------------------------------------------------------------- 变体 A
class VariantA(QWidget):
    """单栏流水线：拖拽卡(五态) + 阶段 chips + 可折叠日志。"""
    name = "A · 单栏流水线"

    def __init__(self, sim):
        super().__init__()
        self.sim = sim
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 12)
        lay.setSpacing(12)

        self.pages = QStackedWidget()
        # 0 empty
        self.drop = DropZone("把日语视频拖到这里", "支持 mp4 / mkv / ts 等 · 中文字幕输出到视频同目录 · 点击也可选择文件")
        self.drop.file_chosen.connect(sim.set_file)
        self.pages.addWidget(self.drop)
        # 1 ready
        w1 = QFrame()
        w1.setObjectName("rd")
        v1 = QVBoxLayout(w1)
        v1.addStretch(1)
        self.a_file = QLabel(" ")
        self.a_file.setAlignment(Qt.AlignCenter)
        self.a_file.setStyleSheet("font-size:15px; font-weight:bold;")
        self.a_small = QLabel(" ")
        self.a_small.setAlignment(Qt.AlignCenter)
        self.a_small.setStyleSheet("color:#9aa0a6;")
        row = QHBoxLayout()
        row.addStretch(1)
        b_start = QPushButton("开始转换")
        b_start.setStyleSheet(f"QPushButton {{ background:{ACCENT}; color:white; padding:8px 28px;"
                              " border-radius:6px; font-size:14px; }")
        b_re = QPushButton("重选文件")
        row.addWidget(b_start)
        row.addSpacing(10)
        row.addWidget(b_re)
        row.addStretch(1)
        v1.addWidget(self.a_file)
        v1.addWidget(self.a_small)
        v1.addSpacing(10)
        v1.addLayout(row)
        v1.addStretch(1)
        b_start.clicked.connect(lambda: sim.start(False))
        b_re.clicked.connect(sim.reset)
        self.pages.addWidget(w1)
        # 2 busy
        w2 = QFrame()
        w2.setObjectName("by")
        v2 = QVBoxLayout(w2)
        self.a_bfile = QLabel(" ")
        self.a_bfile.setStyleSheet("color:#9aa0a6;")
        self.a_chips = QHBoxLayout()
        self.a_bar = QProgressBar()
        self.a_bar.setTextVisible(False)
        self.a_bar.setFixedHeight(10)
        self.a_pct = QLabel("0%")
        self.a_pct.setAlignment(Qt.AlignRight)
        self.a_pct.setStyleSheet("color:#9aa0a6; font-size:11px;")
        v2.addWidget(self.a_bfile)
        v2.addSpacing(6)
        v2.addLayout(self.a_chips)
        v2.addWidget(self.a_bar)
        v2.addWidget(self.a_pct)
        self.pages.addWidget(w2)
        # 3 done
        w3 = QFrame()
        w3.setObjectName("dn")
        v3 = QVBoxLayout(w3)
        v3.addStretch(1)
        self.a_out = QLabel(" ")
        self.a_out.setAlignment(Qt.AlignCenter)
        self.a_out.setWordWrap(True)
        t3 = QLabel("转换完成")
        t3.setAlignment(Qt.AlignCenter)
        t3.setStyleSheet(f"color:{GREEN}; font-size:16px; font-weight:bold;")
        row3 = QHBoxLayout()
        row3.addStretch(1)
        b_open = QPushButton("打开所在文件夹")
        b_again = QPushButton("再转一个")
        row3.addWidget(b_open)
        row3.addWidget(b_again)
        row3.addStretch(1)
        v3.addWidget(t3)
        v3.addWidget(self.a_out)
        v3.addSpacing(10)
        v3.addLayout(row3)
        v3.addStretch(1)
        b_open.clicked.connect(lambda: append_log(
            self.a_log, f"（原型）此处将打开文件夹: {sim.out_zh}"))
        b_again.clicked.connect(sim.reset)
        self.pages.addWidget(w3)
        # 4 error
        w4 = QFrame()
        w4.setObjectName("er")
        v4 = QVBoxLayout(w4)
        v4.addStretch(1)
        t4 = QLabel("转换失败")
        t4.setAlignment(Qt.AlignCenter)
        t4.setStyleSheet(f"color:{RED}; font-size:16px; font-weight:bold;")
        self.a_err = QLabel(" ")
        self.a_err.setAlignment(Qt.AlignCenter)
        self.a_err.setWordWrap(True)
        self.a_hint = QLabel(" ")
        self.a_hint.setAlignment(Qt.AlignCenter)
        self.a_hint.setWordWrap(True)
        self.a_hint.setStyleSheet("color:#9aa0a6; font-size:12px;")
        row4 = QHBoxLayout()
        row4.addStretch(1)
        b_retry = QPushButton("重试")
        b_retry.clicked.connect(lambda: sim.start(False))
        row4.addWidget(b_retry)
        row4.addStretch(1)
        v4.addWidget(t4)
        v4.addWidget(self.a_err)
        v4.addWidget(self.a_hint)
        v4.addSpacing(8)
        v4.addLayout(row4)
        v4.addStretch(1)
        self.pages.addWidget(w4)
        self.page_of = {"idle": 0, "ready": 1, "busy": 2, "done": 3, "error": 4}
        lay.addWidget(self.pages, 3)

        # 日志（可折叠）
        self.log_wrap = QWidget()
        lv = QVBoxLayout(self.log_wrap)
        lv.setContentsMargins(0, 0, 0, 0)
        self.a_log = log_view()
        lv.addWidget(self.a_log)
        lay.addWidget(self.log_wrap, 2)
        self.a_fold = QCheckBox("显示日志")
        self.a_fold.setChecked(True)
        self.a_fold.toggled.connect(self.log_wrap.setVisible)
        lay.addWidget(self.a_fold)

        sim.log_line.connect(lambda s: append_log(self.a_log, s))
        sim.state_changed.connect(self.refresh)
        sim.file_changed.connect(lambda _: self.refresh("ready" if sim.state == "idle" else sim.state))
        sim.stage_changed.connect(self._stage)
        sim.progress_changed.connect(self._prog)
        for s in ("finished", "failed"):
            getattr(sim, s).connect(lambda *_: self.refresh(sim.state))
        self.refresh("idle")

    def _stage(self, idx):
        while self.a_chips.count():
            it = self.a_chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for c in render_chips([s[0] for s in STAGES], idx):
            self.a_chips.addWidget(c)

    def _prog(self, p):
        self.a_bar.setValue(int(p * 100))
        self.a_pct.setText(f"{int(p * 100)}%")

    def refresh(self, state):
        self.pages.setCurrentIndex(self.page_of[state])
        if state == "ready":
            self.a_file.setText(self.sim.file)
            self.a_small.setText("就绪 · 点击开始")
        elif state == "busy":
            self.a_bfile.setText(f"正在处理: {self.sim.file}")
        elif state == "done":
            self.a_out.setText(f"输出: {self.sim.out_zh}")
        elif state == "error":
            self.a_err.setText(self.sim.err)
            self.a_hint.setText(self.sim.hint)


# ---------------------------------------------------------------- 变体 B
class VariantB(QWidget):
    """监控台：左侧任务栏 + 右侧步骤条 + 终端式深色日志。"""
    name = "B · 监控台"

    def __init__(self, sim):
        super().__init__()
        self.sim = sim
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(14)

        # 左：任务栏
        side = QFrame()
        side.setFixedWidth(230)
        side.setStyleSheet("#side { background:#202327; border-radius:10px; }")
        side.setObjectName("side")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 12, 12, 12)
        t = QLabel("任务")
        t.setStyleSheet("font-weight:bold;")
        sv.addWidget(t)
        self.b_card = QLabel("（拖入视频文件\n添加任务）")
        self.b_card.setStyleSheet("background:#2a2d33; border-radius:8px; padding:12px;"
                                  " color:#9aa0a6; font-size:12px;")
        self.b_card.setAlignment(Qt.AlignTop)
        self.b_card.setMinimumHeight(90)
        sv.addWidget(self.b_card)
        sv.addStretch(1)
        self.b_batch = QLabel("+ 批量队列将在这里扩展（原型未启用）")
        self.b_batch.setStyleSheet("color:#9aa0a6; font-size:11px;")
        self.b_batch.setWordWrap(True)
        sv.addWidget(self.b_batch)
        root.addWidget(side)

        # 右：步骤条 + 终端日志 + 状态条
        right = QVBoxLayout()
        top = QHBoxLayout()
        self.b_chips = QHBoxLayout()
        top.addLayout(self.b_chips)
        top.addStretch(1)
        self.b_pct = QLabel(" ")
        self.b_pct.setStyleSheet("font-size:20px; font-weight:bold; color:%s;" % ACCENT)
        top.addWidget(self.b_pct)
        right.addLayout(top)
        right.addSpacing(6)
        self.b_bar = QProgressBar()
        self.b_bar.setTextVisible(False)
        self.b_bar.setFixedHeight(6)
        right.addWidget(self.b_bar)
        right.addSpacing(10)
        self.b_log = log_view(dark=True)
        right.addWidget(self.b_log, 1)
        self.b_status = QLabel("待命")
        self.b_status.setStyleSheet("color:#9aa0a6;")
        right.addWidget(self.b_status)
        root.addLayout(right, 1)

        self.b_start = QPushButton("开始处理")
        self.b_start.setStyleSheet(f"QPushButton {{ background:{ACCENT}; color:white;"
                                   " padding:6px 18px; border-radius:6px; }")
        self.b_start.clicked.connect(lambda: sim.start(False))
        self.b_status_row = QHBoxLayout()
        self.b_status_row.addWidget(self.b_status)
        self.b_status_row.addStretch(1)
        self.b_status_row.addWidget(self.b_start)
        right.addLayout(self.b_status_row)

        sim.log_line.connect(lambda s: append_log(self.b_log, s))
        sim.stage_changed.connect(self._stage)
        sim.progress_changed.connect(self._prog)
        sim.state_changed.connect(self.refresh)
        sim.file_changed.connect(lambda _: self.refresh(sim.state))
        self.refresh("idle")

    def _stage(self, idx):
        while self.b_chips.count():
            it = self.b_chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for c in render_chips([s[0] for s in STAGES], idx):
            self.b_chips.addWidget(c)

    def _prog(self, p):
        self.b_bar.setValue(int(p * 100))
        self.b_pct.setText(f"{int(p * 100)}%")

    def refresh(self, state):
        base = "#34383f"
        color = {"busy": ACCENT, "done": GREEN, "error": RED}.get(state, "#9aa0a6")
        if self.sim.file:
            title = self.sim.file.replace("\\", "/").split("/")[-1]
            badge = {"idle": "等待开始", "ready": "等待开始", "busy": "处理中",
                     "done": "已完成", "error": "失败"}[state]
            self.b_card.setStyleSheet(
                f"background:#2a2d33; border-radius:8px; padding:12px;"
                f" border-left:3px solid {color}; color:#e8eaed;")
            self.b_card.setText(f"{title}\n状态: {badge}")
        tag = {"idle": "待命", "ready": "就绪 · 点击「开始处理」", "busy": "处理中 ...",
               "done": f"完成: {self.sim.out_zh}", "error": self.sim.err}[state]
        self.b_status.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.b_status.setText(tag)
        self.b_start.setVisible(state in ("idle", "ready", "error"))
        self.b_start.setText("重试" if state == "error" else "开始处理")


# ---------------------------------------------------------------- 变体 C
class VariantC(QWidget):
    """向导极简：居中大字步骤向导，日志收进抽屉。"""
    name = "C · 向导极简"

    def __init__(self, sim):
        super().__init__()
        self.sim = sim
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 32, 32, 16)

        self.c_drop = DropZone("拖入日语视频", "一件事：拖进来，等完成")
        self.c_drop.setMinimumHeight(300)
        self.c_drop.file_chosen.connect(sim.set_file)
        lay.addWidget(self.c_drop, 1)

        # 向导页（running / done / error 共用居中大字区）
        self.c_run = QWidget()
        rv = QVBoxLayout(self.c_run)
        rv.addStretch(1)
        self.c_step = QLabel(" ")
        self.c_step.setAlignment(Qt.AlignCenter)
        self.c_step.setStyleSheet("color:#9aa0a6; font-size:14px;")
        self.c_stage = QLabel(" ")
        self.c_stage.setAlignment(Qt.AlignCenter)
        self.c_stage.setStyleSheet("font-size:30px; font-weight:bold;")
        self.c_bar = QProgressBar()
        self.c_bar.setTextVisible(False)
        self.c_bar.setFixedHeight(4)
        rv.addSpacing(14)
        rv.addWidget(self.c_step)
        rv.addWidget(self.c_stage)
        rv.addSpacing(14)
        rv.addWidget(self.c_bar)
        rv.addStretch(1)
        lay.addWidget(self.c_run, 1)

        self.c_end = QWidget()
        ev = QVBoxLayout(self.c_end)
        ev.addStretch(1)
        self.c_end_title = QLabel(" ")
        self.c_end_title.setAlignment(Qt.AlignCenter)
        self.c_end_title.setStyleSheet("font-size:28px; font-weight:bold;")
        self.c_end_body = QLabel(" ")
        self.c_end_body.setAlignment(Qt.AlignCenter)
        self.c_end_body.setWordWrap(True)
        row = QHBoxLayout()
        row.addStretch(1)
        self.c_open = QPushButton("打开所在文件夹")
        self.c_open.clicked.connect(lambda: append_log(
            self.c_drawer, f"（原型）此处将打开文件夹: {sim.out_zh}"))
        self.c_again = QPushButton("再转一个")
        self.c_again.clicked.connect(sim.reset)
        self.c_retry = QPushButton("重试")
        self.c_retry.clicked.connect(lambda: sim.start(False))
        row.addWidget(self.c_open)
        row.addWidget(self.c_again)
        row.addWidget(self.c_retry)
        row.addStretch(1)
        ev.addWidget(self.c_end_title)
        ev.addSpacing(10)
        ev.addWidget(self.c_end_body)
        ev.addSpacing(14)
        ev.addLayout(row)
        ev.addStretch(1)
        lay.addWidget(self.c_end, 1)

        # 抽屉：默认收起
        self.c_drawer = QPlainTextEdit()
        self.c_drawer.setReadOnly(True)
        self.c_drawer.setFont(QFont(MONO, 9))
        self.c_drawer.hide()
        lay.addWidget(self.c_drawer, 1)
        self.c_toggle = QPushButton("详情 ▸")
        self.c_toggle.setFlat(True)
        self.c_toggle.setStyleSheet("color:#9aa0a6;")
        self.c_toggle.clicked.connect(self._fold)
        lay.addWidget(self.c_toggle, 0, Qt.AlignLeft)

        sim.log_line.connect(lambda s: append_log(self.c_drawer, s))
        sim.stage_changed.connect(self._stage)
        sim.progress_changed.connect(self._prog)
        sim.state_changed.connect(self.refresh)
        sim.file_changed.connect(lambda _: self.refresh(sim.state))
        self.refresh("idle")

    def _fold(self):
        self.c_drawer.setVisible(not self.c_drawer.isVisible())
        self.c_toggle.setText("详情 ▾" if self.c_drawer.isVisible() else "详情 ▸")

    def _stage(self, idx):
        if idx < 0:
            return
        self.c_step.setText(f"第 {idx + 1} 步 / 共 {len(STAGES)} 步")
        self.c_stage.setText(STAGES[idx][0])

    def _prog(self, p):
        self.c_bar.setValue(int(p * 100))

    def refresh(self, state):
        running = state in ("idle", "ready", "busy")
        self.c_drop.setVisible(running)
        self.c_run.setVisible(running)
        self.c_end.setVisible(state in ("done", "error"))
        if running and self.sim.file:
            self.c_drop.set_texts(self.sim.file.replace("\\", "/").split("/")[-1],
                                  "点击「详情」可展开日志 · 拖入新文件可替换")
        if state == "busy":
            self.c_stage.setStyleSheet(f"font-size:30px; font-weight:bold; color:{ACCENT};")
        elif state == "done":
            self.c_end_title.setText("完成")
            self.c_end_title.setStyleSheet(f"font-size:28px; font-weight:bold; color:{GREEN};")
            self.c_end_body.setText(f"输出: {self.sim.out_zh}")
            self.c_open.setVisible(True)
            self.c_retry.setVisible(False)
        elif state == "error":
            self.c_end_title.setText("出错了")
            self.c_end_title.setStyleSheet(f"font-size:28px; font-weight:bold; color:{RED};")
            self.c_end_body.setText(f"{self.sim.err}\n{self.sim.hint}")
            self.c_open.setVisible(False)
            self.c_retry.setVisible(True)


# ---------------------------------------------------------------- 变体 D
class VariantD(QWidget):
    """融合版（用户选定方向）：A 的单栏主体 + B 的任务队列栏 + 双字幕输出。"""
    name = "D · 融合版（A 主体 + B 队列栏）"

    def __init__(self, sim):
        super().__init__()
        self.sim = sim
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(14)

        # ---- 左：任务队列栏（来自 B）
        side = QFrame()
        side.setFixedWidth(220)
        side.setObjectName("side")
        side.setStyleSheet("#side { background:#202327; border-radius:10px; }")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 12, 12, 12)
        t = QLabel("任务队列")
        t.setStyleSheet("font-weight:bold;")
        sv.addWidget(t)
        self.d_card = QLabel("（拖入视频文件\n添加任务）")
        self.d_card.setStyleSheet("background:#2a2d33; border-radius:8px; padding:12px;"
                                  " color:#9aa0a6; font-size:12px;")
        self.d_card.setAlignment(Qt.AlignTop)
        self.d_card.setMinimumHeight(90)
        sv.addWidget(self.d_card)
        sv.addStretch(1)
        hint = QLabel("批量：拖入多个文件自动排队（原型仅演示单个任务）")
        hint.setStyleSheet("color:#9aa0a6; font-size:11px;")
        hint.setWordWrap(True)
        sv.addWidget(hint)
        root.addWidget(side)

        # ---- 右：A 的五态主体 + 常驻日志
        right = QVBoxLayout()
        self.pages = QStackedWidget()
        # 0 empty
        self.drop = DropZone("把日语视频拖到这里", "支持 mp4 / mkv / ts 等 · 点击也可选择文件\n完成后输出 中文 + 日语 双字幕 SRT")
        self.drop.file_chosen.connect(sim.set_file)
        self.pages.addWidget(self.drop)
        # 1 ready
        w1 = QFrame()
        w1.setObjectName("rd")
        v1 = QVBoxLayout(w1)
        v1.addStretch(1)
        self.d_file = QLabel(" ")
        self.d_file.setAlignment(Qt.AlignCenter)
        self.d_file.setStyleSheet("font-size:15px; font-weight:bold;")
        self.d_small = QLabel(" ")
        self.d_small.setAlignment(Qt.AlignCenter)
        self.d_small.setStyleSheet("color:#9aa0a6;")
        row = QHBoxLayout()
        row.addStretch(1)
        b_start = QPushButton("开始转换")
        b_start.setStyleSheet(f"QPushButton {{ background:{ACCENT}; color:white; padding:8px 28px;"
                              " border-radius:6px; font-size:14px; }")
        b_re = QPushButton("重选文件")
        b_re.clicked.connect(sim.reset)
        b_start.clicked.connect(lambda: sim.start(False))
        row.addWidget(b_start)
        row.addSpacing(10)
        row.addWidget(b_re)
        row.addStretch(1)
        v1.addWidget(self.d_file)
        v1.addWidget(self.d_small)
        v1.addSpacing(10)
        v1.addLayout(row)
        v1.addStretch(1)
        self.pages.addWidget(w1)
        # 2 busy
        w2 = QFrame()
        w2.setObjectName("by")
        v2 = QVBoxLayout(w2)
        self.d_bfile = QLabel(" ")
        self.d_bfile.setStyleSheet("color:#9aa0a6;")
        self.d_chips = QHBoxLayout()
        self.d_bar = QProgressBar()
        self.d_bar.setTextVisible(False)
        self.d_bar.setFixedHeight(10)
        self.d_pct = QLabel("0%")
        self.d_pct.setAlignment(Qt.AlignRight)
        self.d_pct.setStyleSheet("color:#9aa0a6; font-size:11px;")
        v2.addWidget(self.d_bfile)
        v2.addSpacing(6)
        v2.addLayout(self.d_chips)
        v2.addWidget(self.d_bar)
        v2.addWidget(self.d_pct)
        self.pages.addWidget(w2)
        # 3 done —— 双字幕输出
        w3 = QFrame()
        w3.setObjectName("dn")
        v3 = QVBoxLayout(w3)
        v3.addStretch(1)
        t3 = QLabel("转换完成")
        t3.setAlignment(Qt.AlignCenter)
        t3.setStyleSheet(f"color:{GREEN}; font-size:16px; font-weight:bold;")
        self.d_out_zh = QLabel(" ")
        self.d_out_zh.setAlignment(Qt.AlignCenter)
        self.d_out_ja = QLabel(" ")
        self.d_out_ja.setAlignment(Qt.AlignCenter)
        row3 = QHBoxLayout()
        row3.addStretch(1)
        b_open = QPushButton("打开所在文件夹")
        b_open.clicked.connect(lambda: append_log(
            self.d_log, f"（原型）此处将打开文件夹: {sim.out_zh}"))
        b_again = QPushButton("再转一个")
        b_again.clicked.connect(sim.reset)
        row3.addWidget(b_open)
        row3.addWidget(b_again)
        row3.addStretch(1)
        v3.addWidget(t3)
        v3.addSpacing(6)
        v3.addWidget(self.d_out_zh)
        v3.addWidget(self.d_out_ja)
        v3.addSpacing(10)
        v3.addLayout(row3)
        v3.addStretch(1)
        self.pages.addWidget(w3)
        # 4 error
        w4 = QFrame()
        w4.setObjectName("er")
        v4 = QVBoxLayout(w4)
        v4.addStretch(1)
        t4 = QLabel("转换失败")
        t4.setAlignment(Qt.AlignCenter)
        t4.setStyleSheet(f"color:{RED}; font-size:16px; font-weight:bold;")
        self.d_err = QLabel(" ")
        self.d_err.setAlignment(Qt.AlignCenter)
        self.d_err.setWordWrap(True)
        self.d_hint = QLabel(" ")
        self.d_hint.setAlignment(Qt.AlignCenter)
        self.d_hint.setWordWrap(True)
        self.d_hint.setStyleSheet("color:#9aa0a6; font-size:12px;")
        row4 = QHBoxLayout()
        row4.addStretch(1)
        b_retry = QPushButton("重试")
        b_retry.clicked.connect(lambda: sim.start(False))
        row4.addWidget(b_retry)
        row4.addStretch(1)
        v4.addWidget(t4)
        v4.addWidget(self.d_err)
        v4.addWidget(self.d_hint)
        v4.addSpacing(8)
        v4.addLayout(row4)
        v4.addStretch(1)
        self.pages.addWidget(w4)
        self.page_of = {"idle": 0, "ready": 1, "busy": 2, "done": 3, "error": 4}
        right.addWidget(self.pages, 3)

        # 日志区：加标题与浅边框，避免一片白没有边界感
        logbox = QFrame()
        logbox.setObjectName("logbox")
        logbox.setStyleSheet("#logbox { background:#1b1d21; border:1px solid #34383f;"
                             " border-radius:8px; }")
        lv = QVBoxLayout(logbox)
        lv.setContentsMargins(10, 6, 10, 10)
        lv.setSpacing(4)
        lt = QLabel("日志")
        lt.setStyleSheet("color:#9aa0a6; font-size:11px; border:none;")
        lv.addWidget(lt)
        self.d_log = log_view()
        self.d_log.setStyleSheet("QPlainTextEdit { background:#1b1d21; color:#e8eaed;"
                                 " border:none; }")
        lv.addWidget(self.d_log)
        right.addWidget(logbox, 2)
        root.addLayout(right, 1)

        sim.log_line.connect(lambda s: append_log(self.d_log, s))
        sim.state_changed.connect(self.refresh)
        sim.file_changed.connect(lambda _: self.refresh(sim.state))
        sim.stage_changed.connect(self._stage)
        sim.progress_changed.connect(self._prog)
        for s in ("finished", "failed"):
            getattr(sim, s).connect(lambda *_: self.refresh(sim.state))
        self.refresh("idle")

    def _stage(self, idx):
        while self.d_chips.count():
            it = self.d_chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for c in render_chips([s[0] for s in STAGES], idx):
            self.d_chips.addWidget(c)

    def _prog(self, p):
        self.d_bar.setValue(int(p * 100))
        self.d_pct.setText(f"{int(p * 100)}%")

    def refresh(self, state):
        self.pages.setCurrentIndex(self.page_of[state])
        badge = {"idle": "等待添加", "ready": "等待开始", "busy": "处理中",
                 "done": "已完成", "error": "失败"}[state]
        color = {"busy": ACCENT, "done": GREEN, "error": RED}.get(state, "#9aa0a6")
        if self.sim.file:
            title = self.sim.file.replace("\\", "/").split("/")[-1]
            self.d_card.setStyleSheet(
                f"background:#2a2d33; border-radius:8px; padding:12px;"
                f" border-left:3px solid {color}; color:#e8eaed;")
            self.d_card.setText(f"{title}\n状态: {badge}")
        if state == "ready":
            self.d_file.setText(self.sim.file)
            self.d_small.setText("就绪 · 点击开始")
        elif state == "busy":
            self.d_bfile.setText(f"正在处理: {self.sim.file}")
        elif state == "done":
            self.d_out_zh.setText(f"中文字幕: {self.sim.out_zh}")
            self.d_out_ja.setText(f"日语字幕: {self.sim.out_ja}")
        elif state == "error":
            self.d_err.setText(self.sim.err)
            self.d_hint.setText(self.sim.hint)


# ---------------------------------------------------------------- 切换条 & 主窗
class PrototypeBar(QFrame):
    variant_switched = Signal(int)

    def __init__(self, names, start_i=0):
        super().__init__()
        self.names = names
        self.i = start_i
        self.setObjectName("bar")
        self.setStyleSheet("#bar { background:#232323; border-radius:18px; }")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        b_prev = QPushButton("<")
        b_next = QPushButton(">")
        for b in (b_prev, b_next):
            b.setFixedWidth(34)
            b.setStyleSheet("QPushButton { color:white; background:#3a3a3a;"
                            " border-radius:12px; font-weight:bold; }")
        self.label = QLabel(" ")
        self.label.setStyleSheet("color:white; font-size:12px; min-width:130px;")
        self.label.setAlignment(Qt.AlignCenter)
        b_prev.clicked.connect(lambda: self.step(-1))
        b_next.clicked.connect(lambda: self.step(1))
        h.addWidget(b_prev)
        h.addWidget(self.label)
        h.addWidget(b_next)
        h.addSpacing(16)
        b_run = QPushButton("模拟运行")
        b_err = QPushButton("模拟出错")
        b_reset = QPushButton("重置")
        for b in (b_run, b_err, b_reset):
            b.setStyleSheet("QPushButton { color:#ccc; background:#3a3a3a;"
                            " border-radius:6px; padding:4px 10px; font-size:11px; }")
        h.addWidget(b_run)
        h.addWidget(b_err)
        h.addWidget(b_reset)
        tip = QLabel("原型工具条（不属于设计）· ←/→ 切换变体")
        tip.setStyleSheet("color:#777; font-size:10px;")
        h.addSpacing(10)
        h.addWidget(tip)
        h.addStretch(1)
        self._demo = None
        b_run.clicked.connect(lambda: self._demo and self._demo("run"))
        b_err.clicked.connect(lambda: self._demo and self._demo("fail"))
        b_reset.clicked.connect(lambda: self._demo and self._demo("reset"))
        self._render()

    def set_demo(self, fn):
        self._demo = fn

    def step(self, d):
        self.i = (self.i + d) % len(self.names)
        self._render()
        self.variant_switched.emit(self.i)

    def _render(self):
        self.label.setText(f"{self.names[self.i]}    {self.i + 1}/{len(self.names)}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "benyidaoren.ico")
        self.setWindowTitle("本译道人 — UI 原型（深色 · D 融合版）")
        self.setWindowIcon(QIcon(ico))
        self.setMinimumSize(920, 640)
        self.sim = Sim()

        holder = QWidget()
        root = QVBoxLayout(holder)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.variants = [VariantD(self.sim), VariantA(self.sim),
                         VariantB(self.sim), VariantC(self.sim)]
        for v in self.variants:
            self.stack.addWidget(v)
        root.addWidget(self.stack, 1)

        bar_wrap = QHBoxLayout()
        bar_wrap.setContentsMargins(0, 6, 0, 10)
        bar_wrap.addStretch(1)
        self.bar = PrototypeBar([v.name for v in self.variants], start_i=0)
        self.bar.set_demo(self._demo)
        self.bar.variant_switched.connect(self.stack.setCurrentIndex)
        bar_wrap.addWidget(self.bar)
        bar_wrap.addStretch(1)
        root.addLayout(bar_wrap)
        self.setCentralWidget(holder)

    def keyPressEvent(self, e):
        # 日志框内的左右键由其自己消费，不会到达这里
        if e.key() == Qt.Key_Left:
            self.bar.step(-1)
        elif e.key() == Qt.Key_Right:
            self.bar.step(1)
        else:
            super().keyPressEvent(e)

    def _demo(self, what):
        if what == "reset":
            self.sim.reset()
            return
        if self.sim.state == "busy":
            return
        if not self.sim.file:
            self.sim.set_file("D:\\videos\\示例_日语视频.mp4")
        self.sim.start(fail=(what == "fail"))


def apply_theme(app):
    """深色主题（用户偏好黑色系）：全部颜色显式指定，不跟随系统深浅模式。"""
    app.setStyleSheet(
        "QWidget { color:#e8eaed; font-size:13px; }"
        "QMainWindow { background:#17181c; }"
        "QFrame#rd, QFrame#by { background:#232629; border:1px solid #34383f;"
        " border-radius:10px; }"
        "QFrame#dn { background:#232629; border:1px solid #3ddc97; border-radius:10px; }"
        "QFrame#er { background:#232629; border:1px solid #ff6b6b; border-radius:10px; }"
        "QProgressBar { background:#34383f; border:none; border-radius:3px; }"
        "QProgressBar::chunk { background:#4a8cff; border-radius:3px; }"
        "QPlainTextEdit { background:#1b1d21; color:#e8eaed; border:1px solid #34383f; }"
        "QPushButton { background:#2a2d33; color:#e8eaed; border:1px solid #34383f;"
        " border-radius:6px; padding:5px 14px; }"
        "QPushButton:hover { background:#33373d; }"
    )


def main(smoke=False):
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)
    w = MainWindow()
    w.show()
    if smoke:
        QTimer.singleShot(1500, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main(smoke="--smoke" in sys.argv)
