#!/usr/bin/env python3
"""QtWidgets 冒烟测试：离屏构建真实主窗口，断言 0 条 Qt 警告。

为什么不用「数控件个数」当唯一标准：字段渲染失败的形态会先是警告（控件造错
类型、绑定到 None、信号连到不存在的方法……），而 **0 警告**能覆盖这些。在
0 警告之外，这里再显式断言字段数、控件类型、以及一次真实的编辑往返。

用法:
    python3 tools/check_ui.py
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

# 禁止产生 core dump —— 万一又踩到 Qt 崩溃，不要往磁盘写几百 MB
ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True).prctl(4, 0, 0, 0, 0)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 必须在 import core.profiles 之前隔离 XDG，否则会读写真实配置
_TMP = tempfile.mkdtemp(prefix="sdl-gui-ui-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "cfg")
os.environ["XDG_RUNTIME_DIR"] = os.path.join(_TMP, "run")
os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QSpinBox,
)

from core import profiles, schema  # noqa: E402
from ui.controller import AppController  # noqa: E402
from ui.fields import CollapsibleSection, FieldRow  # noqa: E402
from ui.mainwindow import MainWindow  # noqa: E402

_WARNINGS: list[str] = []
_BENIGN = (
    "QStandardPaths: XDG_RUNTIME_DIR",  # 临时目录提示，与我们无关
)


def _on_message(mode, context, message) -> None:
    if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        if not any(b in message for b in _BENIGN):
            _WARNINGS.append(f"{context.file}:{context.line} {message}")


_EXPECTED = {
    schema.WIDGET_TEXT: QLineEdit,
    schema.WIDGET_PATH: QLineEdit,
    schema.WIDGET_INT: QSpinBox,
    schema.WIDGET_BOOL: QCheckBox,
    schema.WIDGET_ENUM: QComboBox,
}


def main() -> int:
    profiles.ensure_dirs()
    app = QApplication(sys.argv[:1])
    qInstallMessageHandler(_on_message)

    controller = AppController()
    win = MainWindow(controller)
    win.resize(1060, 740)
    win.show()
    app.processEvents()

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{name}{' — ' + detail if detail else ''}")
            print(f"  ✗ {name}{' — ' + detail if detail else ''}")

    # 字段数与控件类型
    check("字段行数量", len(win._rows) == len(schema.FIELDS),
          f"{len(win._rows)} != {len(schema.FIELDS)}")
    for fld in schema.FIELDS:
        row = win._rows.get(fld.key)
        check(f"字段存在 {fld.key}", row is not None)
        if row is None:
            continue
        want = _EXPECTED.get(fld.widget)
        check(f"控件类型 {fld.key}", want is None or isinstance(row.control, want),
              f"{type(row.control).__name__} 期望 {want.__name__ if want else '?'}")

    # 密码行（钥匙串）已接入
    check("密码行存在", hasattr(win, "secret_row"))
    if hasattr(win, "secret_row"):
        check("密码是掩码输入框", isinstance(win.secret_row.edit, QLineEdit))
        check("密码框已掩码",
              win.secret_row.edit.echoMode() == QLineEdit.EchoMode.Password)

    # 值同步：controller → 控件
    win._sync_form(force=True)
    address = win._rows["full address"]
    check("初始地址为空", address.control.text() == "")

    # 真实编辑往返：改地址就应立即生效（不能依赖 editingFinished / 失焦）
    address.control.setText("10.1.2.3")
    app.processEvents()
    check("输入即收到编辑（无需失焦）", controller.fields["full address"] == "10.1.2.3")
    check("输入即置脏（保存可用）", controller.dirty)
    check("预览包含地址", "full address:s:10.1.2.3" in controller.previewText,
          controller.previewText)

    # 联动：改安全方式 → extra_args 控件跟着变
    security = win._rows["gui_security"]
    idx = security.control.findData(1)  # 仅 TLS
    security.control.setCurrentIndex(idx)
    app.processEvents()
    check("下拉写入 /sec:tls",
          "/sec:tls" in str(controller.fields["gui_extra_args"]),
          str(controller.fields["gui_extra_args"]))
    check("extra_args 控件被刷新",
          "/sec:tls" in win._rows["gui_extra_args"].control.text(),
          win._rows["gui_extra_args"].control.text())

    # 列表有草稿一项
    check("列表含草稿", win.list.count() >= 1)
    check("草稿被选中", win.list.currentRow() == 0, str(win.list.currentRow()))

    # 布局健全性：展开的分组里，字段行必须真的被布局了（宽高 > 0），
    # 且标签列固定 LABEL_WIDTH。折叠分组里的行隐藏，不检查。
    win._sync_form(force=True)
    app.processEvents()
    visible = {k: r for k, r in win._rows.items() if r.isVisible()}
    check("有可见字段行", len(visible) > 0)
    zero = [k for k, r in visible.items() if r.width() <= 0 or r.height() <= 0]
    check("可见字段行都有尺寸", not zero, str(zero[:5]))
    if "full address" in visible:
        label = visible["full address"].layout().itemAt(0).widget()
        check("标签列宽固定", label.width() == 190, str(label.width()))

    # 折叠分组：有主题原生箭头，且展开/收起真的切换
    sections = win.findChildren(CollapsibleSection)
    check("折叠分组数量", len(sections) >= len(schema.GROUPS) + 2, str(len(sections)))
    if sections:
        sec = sections[1]  # [0] 是「名称」，[1] 起是 schema 分组
        check("分组可勾选折叠", sec.isCheckable())
        sec.setChecked(False)
        app.processEvents()
        check("收起后内容隐藏", not sec.body.isVisible())
        sec.setChecked(True)
        app.processEvents()
        check("再次展开后内容可见", sec.body.isVisible())

    win.close()
    app.processEvents()

    print(f"字段 {len(win._rows)} / schema {len(schema.FIELDS)}；"
          f"Qt 警告 {len(_WARNINGS)}")
    for w in _WARNINGS[:15]:
        print("  -", w)
    shutil.rmtree(_TMP, ignore_errors=True)

    if failures or _WARNINGS:
        print("\n结果: 失败 ✗")
        return 1
    print("\n结果: 通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
