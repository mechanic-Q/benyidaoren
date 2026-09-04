# 05-bat-repair-verification

Type: task
Status: open
Blocked by:

## Question

确认现有 CLI 流水线的 Windows 调用链完整可靠：bat 已修复（wsl.exe 全路径），端到端 60 秒测试已通过。剩余要验证的是：**真实用户操作路径**——用户双击桌面 bat、拖入视频、全流程跑通。需要用户实际操作一次确认。

### 已完成

- bat 修复：`wsl.exe` 全路径调用（原来 `wsl` 在非交互 shell 下找不到）
- 端到端 60 秒测试通过（WSL 内直接跑 python 脚本）
- tf/torch 同进程冲突已修复（性别判定拆独立进程）

## Answer

（待填——用户双击桌面 bat 拖入视频实测后关闭）
