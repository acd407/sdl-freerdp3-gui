#!/usr/bin/env python3
"""sdl-freerdp3-gui —— 一个 .rdp 配置编辑器 + 启动器。

架构
----
```
core/   运行时逻辑，零第三方依赖、**不 import Qt**，可脱离 GUI 单测
ui/     QtWidgets 界面
          controller.py  状态 + 业务操作（只发信号，不碰 widget）
          fields.py      schema → 控件
          mainwindow.py  列表 / 表单 / 预览 / 按钮
app.py  入口：QApplication + MainWindow
```

`.rdp` 的语义（键名 / 类型 / 布尔反转 / 默认值 / absent / 序列化）全部在
`core/schema`；`ui/` 只负责渲染和收集输入。

用 QtWidgets 而不是 QtQuick 的原因：QtWidgets 走 QStyle，能跟随系统主题
（Kvantum / qt6ct）绘制；QtQuick Controls 不经过 QStyle，**Kvantum 对它是完全
无效的**。代价是界面要自己用 Widget 拼。
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core import profiles
from ui.controller import APP_ID, AppController
from ui.mainwindow import MainWindow

# 用模块级引用持有，避免局部变量在 app.exec() 期间被回收
_WINDOW: MainWindow | None = None


def main() -> int:
    profiles.ensure_dirs()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setOrganizationName(APP_ID)

    global _WINDOW
    _WINDOW = MainWindow(AppController())
    _WINDOW.show()

    # 冒烟测试用：设置 SDL_GUI_SMOKE_TEST=<毫秒> 后自动退出，
    # 走一遍正常事件循环，用来抓构造/析构期的崩溃。
    smoke = os.environ.get("SDL_GUI_SMOKE_TEST")
    if smoke:
        QTimer.singleShot(int(smoke), app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
