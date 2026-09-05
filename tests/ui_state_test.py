# -*- coding: utf-8 -*-
"""benyidaoren.py 页面状态机离屏串测 (Windows venv + QT_QPA_PLATFORM=offscreen)。

不触碰任何真实进程: full_check/q_conv/q_run 一律 stub, 只验证 UI 流转与按钮状态。
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui"))

import benyidaoren as b

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
w = b.MainWindow()
PO = w.page_of
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# 1. 启动: 空态
check("启动为空态", w.pages.currentIndex() == PO["empty"])
check("整窗接受拖拽", w.acceptDrops())

# 2. 拖入第一个文件 → 就绪态 + 高亮开始按钮
w.add_file("C:/vid/a.mp4")
check("入队后切就绪态", w.pages.currentIndex() == PO["ready"])
check("开始按钮存在且可用", w.b_start.isEnabled() and w.b_start.text().endswith("开始转换"))
check("就绪计数文本", w.r_count.text() == "已就绪 1 个文件")
check("开始按钮在当前页可见", w.b_start.isVisible() or w.pages.currentWidget().findChildren(type(w.b_start)))

# 3. 去重与非视频过滤
w.add_file("C:/vid/a.mp4")
w.add_file("C:/vid/note.txt")
check("重复与非视频不入队", len(w.queue) == 1)

# 4. 追加文件
w.add_file("C:/vid/b.mkv")
check("追加到 2 个", len(w.queue) == 2 and w.r_count.text() == "已就绪 2 个文件")

# 5. 点开始 → busy (stub 全检, 不发真进程)
w.full_check = lambda: None
w.b_start.click()
check("点击开始进入 busy", w.pages.currentIndex() == PO["busy"])
check("busy 期间添加/移除禁用", not w.b_add.isEnabled() and not w.b_rm.isEnabled())
check("busy 期间开始按钮禁用", not w.b_start.isEnabled())

# 6. 运行中拖入追加 → 保持 busy, 新文件排队
w.add_file("C:/vid/c.mp4")
check("运行中追加保持 busy", w.pages.currentIndex() == PO["busy"])
check("运行中追加排队", len([t for t in w.queue if t["state"] == "pending"]) == 3)

# 7. 停止 → 回就绪态 (含未完成任务), 按钮恢复可用
w.queue[0]["state"] = "working"
w.stop_all()
check("停止后回就绪态", w.pages.currentIndex() == PO["ready"])
check("停止后开始按钮可用", w.b_start.isEnabled())
check("停止后任务回到排队", all(t["state"] == "pending" for t in w.queue))

# 8. 任务失败 → 错误页; 追加文件不打扰错误页; 重试按钮连通 on_start
w.queue[0]["state"] = "failed"
w.current = w.queue[0]
w.show_error("x", "y", "z")
w.add_file("C:/vid/d.mp4")
check("错误页不被追加打扰", w.pages.currentIndex() == PO["error"])
w.on_start()
check("重试路径进入 busy", w.pages.currentIndex() == PO["busy"])

# 9. 全部完成 → 完成页
for t in w.queue:
    t["state"] = "done"
w.current = None
w.finish_all()
check("完成后为完成页", w.pages.currentIndex() == PO["done"])

# 10. 完成态追加新文件 → 回就绪态
w.add_file("C:/vid/e.mp4")
check("完成态追加回就绪态", w.pages.currentIndex() == PO["ready"])
check("就绪计数只算未完成", w.r_count.text() == "已就绪 1 个文件")

# 11. 就绪页删掉新增任务 → 只剩已完成 → 回完成态; 再清空 → 空态
w.qlist.item(w.qlist.count() - 1).setSelected(True)
w.remove_selected()
check("删掉新增后回完成态", w.pages.currentIndex() == PO["done"])
for i in range(w.qlist.count()):
    w.qlist.item(i).setSelected(True)
w.remove_selected()
check("清空后回空态", w.pages.currentIndex() == PO["empty"] and not w.queue)
check("空态开始按钮禁用", not w.b_start.isEnabled())

print("\n%d 项失败" % len(fails) if fails else "\n全部通过")
sys.exit(1 if fails else 0)
