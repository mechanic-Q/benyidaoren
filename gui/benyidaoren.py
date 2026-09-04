# -*- coding: utf-8 -*-
"""本译道人 — 日语视频 → 中日双字幕 (Windows GUI 壳)

正式版。规划定稿见 .scratch/ja2zh-gui/ (map.md 与 01-06 票):
  01 PySide6  02 wsl.exe 全路径+list 传参+utf-8 流式  03 onefile 打包
  04 D 融合版深色布局  06 轻检启动+全检转换+8888 被占随机换端口
壳只负责界面与调用; 宿主 (WSL venv+模型+ja2zh_subtitle.py) 提供能力。
运行: gui/benyidaoren.bat (双击) 或 venv python gui/benyidaoren.py
"""
import os
import re
import shlex
import sys

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

WSL_EXE = r"C:\Windows\System32\wsl.exe"
DISTRO = "Ubuntu"
SCRIPT = "/home/lmr/tools/ja2zh_subtitle/ja2zh_subtitle.py"
CREATE_NO_WINDOW = 0x08000000

STAGES = ["翻译服务", "抽取音频", "ASR 说话人", "性别判定", "合并段落", "时间轴精修", "翻译"]
VIDEO_EXT = (".mp4", ".mkv", ".ts", ".avi", ".mov", ".webm", ".flv", ".wmv")

# 06 票全检清单: (标签, wsl 内路径)
HOST_CHECKS = [
    ("venv python", "/home/lmr/venvs/subtitle-pipeline/bin/python3"),
    ("whisper 模型", "/home/lmr/models/asr/whisper-large-v3"),
    ("声纹模型", "/home/lmr/models/asr/campplus/campplus_cn_common.bin"),
    ("翻译模型", "/home/lmr/models/translation/hy-mt2-7b/Hy-MT2-7B-Q4_K_M.gguf"),
    ("llama-server", "/home/lmr/projects/llama-dflash2/llama.cpp/build/bin/llama-server"),
]
PREFLIGHT_SH = (
    'for p in ' + " ".join('"%s"' % p for _, p in HOST_CHECKS) + '; do '
    '[ -e "$p" ] && echo "OK $p" || echo "MISS $p"; done; '
    'curl -sm2 http://127.0.0.1:8888/v1/models | grep -qi "hy-mt" && echo "SRV hy-mt@8888" || '
    '(curl -sm2 http://127.0.0.1:8888/v1/models >/dev/null 2>&1 && echo "SRV other@8888" '
    '|| echo "SRV free")'
)

ACCENT = "#4a8cff"
GREEN = "#3ddc97"
RED = "#ff6b6b"
YELLOW = "#ffd166"
TXT = "#e8eaed"
MONO = "Consolas"


def apply_theme(app):
    """深色主题 (04 票定稿): 全部颜色显式指定, 不跟随系统深浅模式。"""
    app.setStyleSheet(
        "QWidget { color:#e8eaed; font-size:13px; }"
        "QMainWindow { background:#17181c; }"
        "QFrame#by { background:#232629; border:1px solid #34383f; border-radius:10px; }"
        "QFrame#dn { background:#232629; border:1px solid #3ddc97; border-radius:10px; }"
        "QFrame#er { background:#232629; border:1px solid #ff6b6b; border-radius:10px; }"
        "QProgressBar { background:#34383f; border:none; border-radius:3px; }"
        "QProgressBar::chunk { background:#4a8cff; border-radius:3px; }"
        "QPlainTextEdit { background:#1b1d21; color:#e8eaed; border:1px solid #34383f; }"
        "QPushButton { background:#2a2d33; color:#e8eaed; border:1px solid #34383f;"
        " border-radius:6px; padding:5px 14px; }"
        "QPushButton:hover { background:#33373d; }"
        "QListWidget { background:#1b1d21; border:1px solid #34383f; border-radius:6px; }"
    )


def quiet(proc):
    """--noconsole 打包后 QProcess 起控制台程序会闪黑窗, 压掉。"""
    try:
        proc.setCreateProcessArgumentsModifier(
            lambda args: setattr(args, "flags", args.flags | CREATE_NO_WINDOW))
    except Exception:
        pass


def chip_style(kind):
    if kind == "done":
        return ("QLabel { background:rgba(61,220,151,.16); color:%s; border-radius:9px;"
                " padding:3px 8px; font-size:11px; }" % GREEN)
    if kind == "cur":
        return ("QLabel { background:%s; color:white; border-radius:9px;"
                " padding:3px 8px; font-size:11px; font-weight:bold; }" % ACCENT)
    return "QLabel { background:#2a2d33; color:#8a9099; border-radius:9px; padding:3px 8px; font-size:11px; }"


def render_chips(cur):
    out = []
    for i, name in enumerate(STAGES):
        lab = QLabel(name)
        lab.setStyleSheet(chip_style("done" if i < cur else "cur" if i == cur else "p"))
        lab.setAlignment(Qt.AlignCenter)
        lab.setFixedHeight(24)
        lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        out.append(lab)
    return out


def log_view():
    v = QPlainTextEdit()
    v.setReadOnly(True)
    v.setFont(QFont(MONO, 9))
    return v


def append_log(view, line, color=None):
    if color:
        view.appendHtml(f'<span style="color:{color};">{line}</span>')
    else:
        view.appendPlainText(line)


def base_name(path):
    return os.path.basename(path.replace("\\", "/"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "benyidaoren.ico")
        self.setWindowTitle("本译道人 — 日语视频转中日双字幕")
        self.setWindowIcon(QIcon(ico))
        self.setMinimumSize(920, 640)

        # ---- 状态 ----
        self.queue = []          # [{win, wsl, state: pending/working/done/failed}]
        self.current = None
        self.run_buf = ""
        self.stage = -1
        self.err_lines = []
        self.preflight = []      # 全检结果行
        self.srv_info = ""

        # ---- 进程 ----
        self.q_light = QProcess(self)
        self.q_check = QProcess(self)
        self.q_conv = QProcess(self)
        self.q_run = QProcess(self)
        for q in (self.q_light, self.q_check, self.q_conv, self.q_run):
            quiet(q)

        # ---- UI ----
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 10)
        root.setSpacing(8)

        self.warnbar = QFrame()
        self.warnbar.setObjectName("warn")
        self.warnbar.setStyleSheet(
            "#warn { background:#3a3222; border:1px solid #8a6d1a; border-radius:6px; }")
        wl = QHBoxLayout(self.warnbar)
        wl.setContentsMargins(12, 6, 12, 6)
        self.warn_text = QLabel("")
        self.warn_text.setWordWrap(True)
        wl.addWidget(self.warn_text, 1)
        b_diag = QPushButton("复制诊断")
        b_diag.clicked.connect(self.copy_diag)
        wl.addWidget(b_diag)
        self.warnbar.hide()
        root.addWidget(self.warnbar)

        body = QHBoxLayout()
        body.setContentsMargins(16, 8, 16, 0)
        body.setSpacing(14)

        # 左: 任务队列
        side = QFrame()
        side.setFixedWidth(230)
        side.setObjectName("side")
        side.setStyleSheet("#side { background:#202327; border-radius:10px; }")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 12, 12, 12)
        t = QLabel("任务队列")
        t.setStyleSheet("font-weight:bold;")
        sv.addWidget(t)
        self.qlist = QListWidget()
        sv.addWidget(self.qlist, 1)
        row_q = QHBoxLayout()
        b_add = QPushButton("添加")
        b_add.clicked.connect(self.add_files_dialog)
        b_rm = QPushButton("移除所选")
        b_rm.clicked.connect(self.remove_selected)
        row_q.addWidget(b_add)
        row_q.addWidget(b_rm)
        sv.addLayout(row_q)
        hint = QLabel("批量: 拖入多个文件自动排队依次转换")
        hint.setStyleSheet("color:#9aa0a6; font-size:11px;")
        hint.setWordWrap(True)
        sv.addWidget(hint)
        body.addWidget(side)

        # 右: 五态页 + 常驻日志
        right = QVBoxLayout()
        self.pages = QStackedWidget()
        # 0 空态
        self.drop = DropZone()
        self.drop.file_dropped.connect(self.add_file)
        self.drop.clicked.connect(self.add_files_dialog)
        self.pages.addWidget(self.drop)
        # 1 运行
        w2 = QFrame()
        w2.setObjectName("by")
        v2 = QVBoxLayout(w2)
        self.b_file = QLabel(" ")
        self.b_file.setStyleSheet("color:#e8eaed; font-size:14px; font-weight:bold;")
        self.b_pos = QLabel(" ")
        self.b_pos.setStyleSheet("color:#9aa0a6;")
        self.chips = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.pct = QLabel("0%")
        self.pct.setAlignment(Qt.AlignRight)
        self.pct.setStyleSheet("color:#9aa0a6; font-size:11px;")
        v2.addWidget(self.b_file)
        v2.addWidget(self.b_pos)
        v2.addSpacing(8)
        v2.addLayout(self.chips)
        v2.addWidget(self.bar)
        v2.addWidget(self.pct)
        v2.addStretch(1)
        row_stop = QHBoxLayout()
        row_stop.addStretch(1)
        self.b_stop = QPushButton("停止")
        self.b_stop.clicked.connect(self.stop_all)
        row_stop.addWidget(self.b_stop)
        v2.addLayout(row_stop)
        self.pages.addWidget(w2)
        # 2 完成
        w3 = QFrame()
        w3.setObjectName("dn")
        v3 = QVBoxLayout(w3)
        v3.addStretch(1)
        t3 = QLabel("全部完成")
        t3.setAlignment(Qt.AlignCenter)
        t3.setStyleSheet(f"color:{GREEN}; font-size:16px; font-weight:bold;")
        self.d_out = QLabel(" ")
        self.d_out.setAlignment(Qt.AlignCenter)
        self.d_out.setWordWrap(True)
        row3 = QHBoxLayout()
        row3.addStretch(1)
        b_open = QPushButton("打开所在文件夹")
        b_open.clicked.connect(self.open_folder)
        b_again = QPushButton("再来一批")
        b_again.clicked.connect(self.reset_all)
        row3.addWidget(b_open)
        row3.addWidget(b_again)
        row3.addStretch(1)
        v3.addWidget(t3)
        v3.addSpacing(8)
        v3.addWidget(self.d_out)
        v3.addSpacing(10)
        v3.addLayout(row3)
        v3.addStretch(1)
        self.pages.addWidget(w3)
        # 3 错误
        w4 = QFrame()
        w4.setObjectName("er")
        v4 = QVBoxLayout(w4)
        v4.addStretch(1)
        t4 = QLabel("转换失败")
        t4.setAlignment(Qt.AlignCenter)
        t4.setStyleSheet(f"color:{RED}; font-size:16px; font-weight:bold;")
        self.e_msg = QLabel(" ")
        self.e_msg.setAlignment(Qt.AlignCenter)
        self.e_msg.setWordWrap(True)
        self.e_hint = QLabel(" ")
        self.e_hint.setAlignment(Qt.AlignCenter)
        self.e_hint.setWordWrap(True)
        self.e_hint.setStyleSheet("color:#9aa0a6; font-size:12px;")
        row4 = QHBoxLayout()
        row4.addStretch(1)
        b_diag2 = QPushButton("复制诊断")
        b_diag2.clicked.connect(self.copy_diag)
        b_retry = QPushButton("重试")
        b_retry.clicked.connect(self.on_start)
        row4.addWidget(b_diag2)
        row4.addWidget(b_retry)
        row4.addStretch(1)
        v4.addWidget(t4)
        v4.addWidget(self.e_msg)
        v4.addWidget(self.e_hint)
        v4.addSpacing(8)
        v4.addLayout(row4)
        v4.addStretch(1)
        self.pages.addWidget(w4)
        self.page_of = {"empty": 0, "busy": 1, "done": 2, "error": 3}
        right.addWidget(self.pages, 3)

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
        self.log = log_view()
        self.log.setStyleSheet("QPlainTextEdit { background:#1b1d21; color:#e8eaed;"
                               " border:none; }")
        lv.addWidget(self.log)
        right.addWidget(logbox, 2)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)

        self.show_page("empty")
        self.light_check()

    # ---------------- 进程通用 ----------------
    def show_page(self, name):
        self.pages.setCurrentIndex(self.page_of[name])

    # ---------------- 轻检 (06: 启动时) ----------------
    def light_check(self):
        if not os.path.exists(WSL_EXE):
            self.warn("未找到 wsl.exe (C:\\Windows\\System32\\wsl.exe)。请先安装 WSL。")
            return
        self.warn_text.setText("正在检查 WSL 环境 ...")
        self.warnbar.show()
        self.q_light.finished.connect(self.on_light_done, Qt.UniqueConnection)
        self.q_light.start(WSL_EXE, ["-d", DISTRO, "--", "true"])

    def on_light_done(self, code, _status):
        try:
            self.q_light.finished.disconnect(self.on_light_done)
        except RuntimeError:
            pass
        if code == 0:
            self.warnbar.hide()
        else:
            self.warn(f"WSL / {DISTRO} 不可用 (rc={code})。"
                      f"请在 PowerShell 运行 wsl --status 检查; 重装后执行 wsl --update。")

    def warn(self, text):
        self.warn_text.setText(text)
        self.warnbar.show()

    # ---------------- 队列管理 ----------------
    def add_files_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择日语视频", "", "视频 (*.mp4 *.mkv *.ts *.avi *.mov *.webm *.flv *.wmv)")
        for p in paths:
            self.add_file(p)

    def add_file(self, path):
        if any(t["win"] == path for t in self.queue):
            return
        if not path.lower().endswith(VIDEO_EXT):
            return
        self.queue.append({"win": path, "wsl": "", "state": "pending"})
        self.qlist.addItem(f"{base_name(path)} · 排队")
        self.refresh_queue_ui()

    def remove_selected(self):
        for row in sorted({self.qlist.row(it) for it in self.qlist.selectedItems()}, reverse=True):
            if row < len(self.queue) and self.queue[row]["state"] == "pending":
                self.queue.pop(row)
                self.qlist.takeItem(row)
        self.refresh_queue_ui()

    def refresh_queue_ui(self):
        marks = {"pending": "排队", "working": "处理中", "done": "已完成", "failed": "失败"}
        colors = {"pending": "#9aa0a6", "working": ACCENT, "done": GREEN, "failed": RED}
        for i, t in enumerate(self.queue):
            if i < self.qlist.count():
                self.qlist.item(i).setText(f"{base_name(t['win'])} · {marks[t['state']]}")
                self.qlist.item(i).setForeground(QColor(colors[t["state"]]))
        busy = any(t["state"] == "working" for t in self.queue)
        self.b_add.setEnabled(not busy)
        self.b_rm.setEnabled(not busy)

    # ---------------- 开始 / 停止 ----------------
    def on_start(self):
        pend = [t for t in self.queue if t["state"] in ("pending", "failed")]
        if not pend:
            self.show_error("没有待转换的任务", "请先把日语视频拖进来。", "")
            return
        for t in self.queue:
            if t["state"] == "failed":
                t["state"] = "pending"
        self.err_lines = []
        self.log.clear()
        self.refresh_queue_ui()
        self.show_page("busy")
        self.b_file.setText("正在检查依赖 ...")
        self.b_pos.setText(f"共 {len([t for t in self.queue if t['state'] != 'done'])} 个任务")
        self.full_check()

    def stop_all(self):
        if self.q_run.state() != QProcess.NotRunning:
            self.q_run.kill()
        for t in self.queue:
            if t["state"] in ("working", "pending"):
                t["state"] = "pending"
        self.current = None
        append_log(self.log, "[已停止]", YELLOW)
        self.show_page("empty")

    def open_folder(self):
        done = [t for t in self.queue if t["state"] == "done"]
        if done:
            append_log(self.log, f"（正式版）将打开: {os.path.dirname(done[0]['win'])}")
            os.startfile(os.path.dirname(done[0]["win"]))

    def reset_all(self):
        self.queue = []
        self.qlist.clear()
        self.log.clear()
        self.show_page("empty")

    # ---------------- 全检 (06: 开始转换时) ----------------
    def full_check(self):
        self.q_check.finished.connect(self.on_check_done, Qt.UniqueConnection)
        self.q_check.start(WSL_EXE, ["-d", DISTRO, "--", "bash", "-c", PREFLIGHT_SH])

    def on_check_done(self, code, _status):
        try:
            self.q_check.finished.disconnect(self.on_check_done)
        except RuntimeError:
            pass
        out = bytes(self.q_check.readAllStandardOutput()).decode("utf-8", "replace")
        self.preflight = [ln.strip() for ln in out.splitlines() if ln.strip()]
        miss = [ln for ln in self.preflight if ln.startswith("MISS")]
        self.srv_info = next((ln[4:] for ln in self.preflight if ln.startswith("SRV ")), "未知")
        if miss:
            names = [next((lb for lb, p in HOST_CHECKS if p in ln), ln) for ln in miss]
            self.show_error(
                "缺少依赖文件",
                "缺失: " + "、".join(names),
                "模型/环境位于 WSL 内 (~/venvs, ~/models, ~/projects)。"
                "如为换机后首次使用, 请先在 WSL 内恢复环境。")
            return
        append_log(self.log, f"[预检] 依赖齐全; 翻译服务: {self.srv_info}")
        self.next_task()

    # ---------------- 任务驱动 ----------------
    def next_task(self):
        pend = [t for t in self.queue if t["state"] == "pending"]
        if not pend:
            self.finish_all()
            return
        task = pend[0]
        task["state"] = "working"
        self.current = task
        self.refresh_queue_ui()
        self.show_page("busy")
        self.stage = -1
        self._render_stage(-1)
        self.b_file.setText(base_name(task["win"]))
        idx = self.queue.index(task) + 1
        self.b_pos.setText(f"任务 {idx}/{len(self.queue)} · 翻译服务: {self.srv_info}")
        # wslpath 转换
        self.q_conv.finished.connect(self.on_conv_done, Qt.UniqueConnection)
        self.q_conv.start(WSL_EXE, ["-d", DISTRO, "--", "wslpath", "-u", task["win"]])

    def on_conv_done(self, code, _status):
        try:
            self.q_conv.finished.disconnect(self.on_conv_done)
        except RuntimeError:
            pass
        task = self.current
        if code != 0:
            self.show_error("路径转换失败", f"wslpath rc={code}", "文件路径可能包含特殊字符。")
            return
        wp = bytes(self.q_conv.readAllStandardOutput()).decode("utf-8", "replace").strip()
        task["wsl"] = wp
        append_log(self.log, f"[$] wslpath: {wp}")
        cmd = f"python3 {shlex.quote(SCRIPT)} {shlex.quote(wp)} --keep-ja"
        self.run_buf = ""
        self.q_run.finished.connect(self.on_run_done, Qt.UniqueConnection)
        self.q_run.readyReadStandardOutput.connect(self.on_run_out, Qt.UniqueConnection)
        self.q_run.start(WSL_EXE, ["-d", DISTRO, "--", "bash", "-lc", cmd])

    def on_run_out(self):
        buf = bytes(self.q_run.readAllStandardOutput()).decode("utf-8", "replace")
        self.run_buf += buf
        lines = self.run_buf.split("\n")
        self.run_buf = lines.pop()
        for ln in lines:
            self.on_line(ln.rstrip("\r"))

    def on_line(self, ln):
        if not ln.strip():
            return
        if ln.startswith("[ERR]"):
            self.err_lines.append(ln)
            append_log(self.log, ln, RED)
            return
        append_log(self.log, ln)
        m = re.match(r"\[(\d)/6\]", ln)
        if m:
            self._render_stage(int(m.group(1)))

    def _render_stage(self, stage):
        self.stage = stage
        while self.chips.count():
            it = self.chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for c in render_chips(stage):
            self.chips.addWidget(c)
        done = len([t for t in self.queue if t["state"] == "done"])
        frac = (stage + 1) / len(STAGES) if stage >= 0 else 0
        total = (done + frac) / max(len(self.queue), 1)
        self.bar.setValue(int(total * 100))
        self.pct.setText(f"{int(total * 100)}%")

    def on_run_done(self, code, _status):
        try:
            self.q_run.finished.disconnect(self.on_run_done)
            self.q_run.readyReadStandardOutput.disconnect(self.on_run_out)
        except RuntimeError:
            pass
        if self.run_buf.strip():
            self.on_line(self.run_buf)
            self.run_buf = ""
        task = self.current
        if code == 0 and not self.err_lines:
            task["state"] = "done"
            self.refresh_queue_ui()
            append_log(self.log, f"[任务完成] {base_name(task['win'])}", GREEN)
            self.next_task()
        else:
            task["state"] = "failed"
            self.refresh_queue_ui()
            tail = "<br>".join(self.err_lines[-3:] or ["(无错误行)"])
            hint = "通用错误。点「复制诊断」获取详情。"
            if code == 255:
                hint = "rc=255 为 WSL 层错误: WSL 未安装/发行版未注册/服务未启动。"
            elif any("翻译服务" in l for l in self.err_lines):
                hint = "翻译服务启动失败: 检查 llama-server 与 Hy-MT2 模型路径。"
            elif any("ffmpeg" in l for l in self.err_lines):
                hint = "ffmpeg 失败: 视频文件可能损坏或格式不受支持。"
            self.show_error(f"任务失败: {base_name(task['win'])} (rc={code})", tail, hint)

    def recent_log_text(self):
        return self.log.toPlainText()

    def finish_all(self):
        done = [t for t in self.queue if t["state"] == "done"]
        lines = []
        for t in done:
            b = os.path.splitext(os.path.basename(t["win"]))[0]
            outdir = os.path.dirname(t["win"])
            lines.append(f"{b}.zh.srt  +  {b}.ja.srt")
        self.d_out.setText("\n".join(lines) or " ")
        self.d_out_dir = os.path.dirname(done[0]["win"]) if done else ""
        append_log(self.log, "[全部完成]", GREEN)
        self.show_page("done")

    def show_error(self, msg, detail, hint):
        self.e_msg.setText(msg if not detail else f"{msg}\n{detail}")
        self.e_hint.setText(hint)
        self.show_page("error")

    def copy_diag(self):
        rows = ["== 本译道人诊断 ==",
                f"任务数: {len(self.queue)}  完成: {len([t for t in self.queue if t['state']=='done'])}"]
        rows += [f"{t['state']:>8}  {t['win']}" for t in self.queue]
        rows.append(f"翻译服务: {self.srv_info}")
        rows.append("== 预检 ==")
        rows += self.preflight or ["(未执行)"]
        rows.append("== 日志尾部 ==")
        rows += self.log.toPlainText().splitlines()[-25:]
        QApplication.clipboard().setText("\n".join(rows))
        append_log(self.log, "[诊断已复制到剪贴板]", YELLOW)


class DropZone(QFrame):
    file_dropped = Signal(str)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("drop")
        self._hl(False)
        v = QVBoxLayout(self)
        v.addStretch(1)
        self.big = QLabel("把日语视频拖到这里")
        self.big.setAlignment(Qt.AlignCenter)
        self.big.setStyleSheet("font-size:16px; font-weight:bold;")
        self.small = QLabel("支持批量 · mp4 / mkv / ts 等 · 完成后输出 中文 + 日语 双字幕 SRT\n点击也可选择文件")
        self.small.setAlignment(Qt.AlignCenter)
        self.small.setStyleSheet("color:#9aa0a6; font-size:12px;")
        v.addWidget(self.big)
        v.addWidget(self.small)
        v.addStretch(1)

    def _hl(self, on):
        color = ACCENT if on else "#565b63"
        self.setStyleSheet(f"#drop {{ border: 2px dashed {color}; border-radius: 10px;"
                           " background:#1e2024; }}")

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
                self.file_dropped.emit(u.toLocalFile())

    def mousePressEvent(self, e):
        self.clicked.emit()


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
