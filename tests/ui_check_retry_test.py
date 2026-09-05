# -*- coding: utf-8 -*-
"""全检自动重试逻辑单测: 首次失败静默重试一次, 二次失败进错误页。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui"))

import benyidaoren as b
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

app = QApplication(sys.argv)
w = b.MainWindow()
w.light_ok = True
PO = w.page_of
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


w.add_file("C:/vid/a.mp4")
w.full_check = lambda: counts.append(1)  # stub, 不发真进程
counts = []
w.on_start()
check("on_start 重置重试计数", w.check_retries == 0)
counts.clear()  # on_start 自身触发过一次全检, 清零后专测重试

# 第一次失败 → 自动重试, 不进错误页
w._check_retry_or_fail("测试失败甲")
QTest.qWait(2500)
check("首次失败触发自动重试", w.check_retries == 1 and len(counts) == 1)
check("重试期间不进错误页", w.pages.currentIndex() == PO["busy"])
check("重试留痕日志", any("自动重试" in ln for ln in w.log.toPlainText().splitlines()))

# 第二次失败 → 错误页
w._check_retry_or_fail("测试失败乙")
check("二次失败进错误页", w.pages.currentIndex() == PO["error"])
check("二次失败不再计数", w.check_retries == 1)

print("\n%d 项失败" % len(fails) if fails else "\n全部通过")
sys.exit(1 if fails else 0)
