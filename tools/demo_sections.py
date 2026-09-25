#!/usr/bin/env python3
"""分组 / 折叠控件的视觉对照 demo —— **不参与运行时**，纯给人看的。

把同一份示例内容塞进每一种候选实现，方便直接比较；顶部还能实时切换 QStyle
（Kvantum / Fusion / …），看它们在不同主题下的表现。

用法:
    python3 tools/demo_sections.py

冒烟（无头、600ms 后自动退出）：
    DEMO_SMOKE_TEST=600 QT_QPA_PLATFORM=offscreen python3 tools/demo_sections.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QCommandLinkButton,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyleFactory,
    QToolBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.fields import CollapsibleSection  # noqa: E402  (应用当前用的实现)


# --------------------------------------------------------------- 通用零件

class ArrowToolButton(QToolButton):
    """主题原生箭头 + 加粗标题的折叠头。

    应用里的正式实现是 `ui/fields.CollapsibleSection`；这里抽出来给几个变体复用。
    """

    def __init__(self, text: str, opened: bool = True, bold: bool = True, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setChecked(opened)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(14, 14))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if bold:
            font = self.font()
            font.setBold(True)
            self.setFont(font)
        self.toggled.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        pm = (
            QStyle.StandardPixmap.SP_ArrowDown
            if self.isChecked()
            else QStyle.StandardPixmap.SP_ArrowRight
        )
        self.setIcon(self.style().standardIcon(pm))

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._refresh()


def sample_body(label_width: int = 90) -> QWidget:
    """每个折叠控件里塞同一份内容，方便对比。"""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)

    edit = QLineEdit("192.168.1.10")
    port = QSpinBox()
    port.setRange(1, 65535)
    port.setValue(3389)
    port.setMaximumWidth(140)
    audio = QComboBox()
    audio.addItems(["在本机播放", "在服务器播放", "不播放"])

    for text, widget in (("服务器地址", edit), ("端口", port), ("音频播放", audio)):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        lab = QLabel(text)
        lab.setFixedWidth(label_width)
        rl.addWidget(lab, 0)
        if isinstance(widget, (QLineEdit, QComboBox)):
            rl.addWidget(widget, 1)
        else:
            rl.addWidget(widget, 0)
            rl.addStretch(1)
        lay.addWidget(row)
    return body


def _panel() -> tuple[QFrame, QVBoxLayout]:
    box = QFrame()
    box.setFrameShape(QFrame.Shape.StyledPanel)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 6, 8, 8)
    lay.setSpacing(6)
    return box, lay


# --------------------------------------------------------------- 变体

def variant_old_arrow() -> QWidget:
    """① 迁移前用的：QToolButton.setArrowType()，Qt 内绘小三角。"""
    box, lay = _panel()
    btn = QToolButton()
    btn.setText("连接")
    btn.setCheckable(True)
    btn.setChecked(True)
    btn.setAutoRaise(True)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    btn.setArrowType(Qt.ArrowType.DownArrow)
    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    btn.toggled.connect(
        lambda on: btn.setArrowType(
            Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow
        )
    )
    lay.addWidget(btn)

    body = sample_body()
    lay.addWidget(body)
    btn.toggled.connect(body.setVisible)
    return box


def variant_themed_toolbutton() -> QWidget:
    """② 应用现在用的：主题原生箭头 + 加粗标题。"""
    sec = CollapsibleSection("连接", opened=True)
    sec.add(sample_body())
    return sec


def variant_flat_pushbutton() -> QWidget:
    """③ 整行 QPushButton(flat)：面积大、好点，文字要靠样式表左对齐。"""
    box, lay = _panel()
    btn = QPushButton("连接")
    btn.setCheckable(True)
    btn.setChecked(True)
    btn.setFlat(True)
    btn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
    btn.setIconSize(QSize(14, 14))
    btn.setStyleSheet("QPushButton { text-align: left; padding: 4px 6px; }")
    font = btn.font()
    font.setBold(True)
    btn.setFont(font)
    btn.toggled.connect(
        lambda on: btn.setIcon(
            QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_ArrowDown
                if on
                else QStyle.StandardPixmap.SP_ArrowRight
            )
        )
    )
    lay.addWidget(btn)

    body = sample_body()
    lay.addWidget(body)
    btn.toggled.connect(body.setVisible)
    return box


def variant_groupbox_checkable() -> QWidget:
    """④ QGroupBox(checkable)：原生标题 + 勾选框，最"系统"。

    注意：Qt 会在取消勾选时**禁用子控件**，所以这里收起时把 body 一并隐藏。
    """
    box = QGroupBox("连接")
    box.setCheckable(True)
    box.setChecked(True)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(6)

    body = sample_body()
    lay.addWidget(body)
    box.toggled.connect(body.setVisible)
    return box


def variant_groupbox_arrow() -> QWidget:
    """⑤ QGroupBox 原生分组外框 + 标题下方的主题箭头。"""
    box = QGroupBox("连接")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(6)

    head = ArrowToolButton("展开 / 收起")
    lay.addWidget(head)

    body = sample_body()
    lay.addWidget(body)
    head.toggled.connect(body.setVisible)
    return box


def variant_disclosure() -> QWidget:
    """⑥ 现代 disclosure 风：无外框，加粗标题 + 细分隔线 + 缩进内容。"""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    head = ArrowToolButton("连接")
    head.setMinimumHeight(28)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)

    holder = QWidget()
    hl = QVBoxLayout(holder)
    hl.setContentsMargins(10, 8, 0, 8)
    hl.addWidget(sample_body())

    lay.addWidget(head)
    lay.addWidget(line)
    lay.addWidget(holder)
    head.toggled.connect(holder.setVisible)
    return box


def variant_tree() -> QWidget:
    """⑦ QTreeWidget：原生展开三角、键盘 ←/→、动画，主题完全一致。

    代价：字段是任意 widget，要用 setItemWidget，行高得自己给 sizeHint。
    """
    tree = QTreeWidget()
    tree.setHeaderHidden(True)
    tree.setRootIsDecorated(True)
    tree.setIndentation(18)
    tree.setMinimumHeight(200)

    root = QTreeWidgetItem(tree, ["连接"])
    body = sample_body()
    child = QTreeWidgetItem(root)
    tree.setItemWidget(child, 0, body)
    child.setSizeHint(0, body.sizeHint())
    root.setExpanded(True)
    return tree


def variant_toolbox() -> QWidget:
    """⑧ QToolBox：原生手风琴。缺点：一次只能展开一页。"""
    box = QToolBox()
    box.setMinimumHeight(200)
    box.addItem(sample_body(), "连接")
    box.addItem(sample_body(), "显示")
    return box


def variant_command_link() -> QWidget:
    """⑨ QCommandLinkButton：大按钮 + 副标题，不是折叠语义，仅作参考。"""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    btn = QCommandLinkButton("连接", "点这里展开 / 收起")
    btn.setCheckable(True)
    btn.setChecked(True)
    body = sample_body()
    lay.addWidget(btn)
    lay.addWidget(body)
    btn.toggled.connect(body.setVisible)
    return box


VARIANTS = [
    ("① QToolButton + setArrowType",
     "迁移前的实现：Qt 内绘小三角，颜色不跟主题", variant_old_arrow),
    ("② QToolButton + 主题原生箭头（应用现在用的）",
     "standardIcon(SP_ArrowDown/Right) + 加粗标题", variant_themed_toolbutton),
    ("③ QPushButton(flat, checkable)",
     "整行都是按钮，好点；文字左对齐要写样式表", variant_flat_pushbutton),
    ("④ QGroupBox(checkable)",
     "原生标题栏 + 勾选框，最“系统”；语义偏“启用 / 禁用本组”", variant_groupbox_checkable),
    ("⑤ QGroupBox + 箭头",
     "原生分组外框，标题旁放主题箭头", variant_groupbox_arrow),
    ("⑥ Disclosure（无外框 + 分隔线）",
     "现代折叠面板风格，内容缩进", variant_disclosure),
    ("⑦ QTreeWidget",
     "原生展开三角 + 键盘 ←/→；字段要 setItemWidget", variant_tree),
    ("⑧ QToolBox",
     "原生手风琴；一次只能展开一页", variant_toolbox),
    ("⑨ QCommandLinkButton",
     "大按钮 + 副标题（不是折叠控件，仅对照）", variant_command_link),
]


# --------------------------------------------------------------- 窗口

class Demo(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("分组 / 折叠控件对照 — 切右上角的样式看效果")
        self.resize(920, 860)

        outer = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("QStyle:"))
        self.style_box = QComboBox()
        names = sorted(set(QStyleFactory.keys()) | {"kvantum", "qt6ct-style"})
        self.style_box.addItems(names)
        current = QApplication.style().objectName().lower()
        for i in range(self.style_box.count()):
            if self.style_box.itemText(i).lower() == current:
                self.style_box.setCurrentIndex(i)
                break
        self.style_box.currentTextChanged.connect(self._switch_style)
        bar.addWidget(self.style_box)
        bar.addStretch(1)
        bar.addWidget(QLabel("可用折叠图标：SP_ArrowDown / SP_ArrowRight / "
                             "SP_TitleBarShade|UnshadeButton"))
        outer.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(14)

        for title, note, factory in VARIANTS:
            card = QWidget()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)

            head = QLabel(title)
            hf = head.font()
            hf.setBold(True)
            head.setFont(hf)

            desc = QLabel(note)
            df = desc.font()
            df.setPointSizeF(max(7.0, df.pointSizeF() - 1.0))
            desc.setFont(df)
            desc.setEnabled(False)

            cl.addWidget(head)
            cl.addWidget(desc)
            cl.addWidget(factory())
            lay.addWidget(card)

        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _switch_style(self, name: str) -> None:
        style = QStyleFactory.create(name)
        if style is not None:
            # 样式切换会发 StyleChange，ArrowToolButton / CollapsibleSection 会自己刷新箭头
            QApplication.setStyle(style)


def main() -> int:
    app = QApplication(sys.argv)
    win = Demo()
    win.show()

    smoke = os.environ.get("DEMO_SMOKE_TEST")
    if smoke:
        QTimer.singleShot(int(smoke), app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
