"""schema → QtWidgets 控件。

新增一个字段**不需要改这个文件**：`FieldRow` 按 `fld.widget` 造控件，分组由
`MainWindow` 按 `schema.GROUPS` 生成。这里不出现任何 `.rdp` 键名字面量。

布尔反转、类型转换、默认值/absent 全在 `core/schema`；本文件里的值一律是
**UI 语义**（例如「显示桌面壁纸」勾选 = 启用，而不是文件里的 `disable wallpaper:i:0`）。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import schema

LABEL_WIDTH = 190
INT_WIDTH = 170
ENUM_WIDTH = 280

_TEXT_WIDGETS = (schema.WIDGET_TEXT, schema.WIDGET_PATH)


class FieldRow(QWidget):
    """一行字段：标签 + 控件。控件值变化时发 ``changed(key, ui_value)``。"""

    changed = pyqtSignal(str, object)

    def __init__(self, fld: schema.Field, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fld = fld
        self.key = fld.key
        self._syncing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        label = QLabel(fld.label)
        label.setFixedWidth(LABEL_WIDTH)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        if fld.help:
            label.setToolTip(fld.help)
        lay.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)

        self.control = self._make_control(fld)
        if fld.widget in _TEXT_WIDGETS:
            lay.addWidget(self.control, 1)
        else:
            lay.addWidget(self.control, 0)
            lay.addStretch(1)

    # ------------------------------------------------------------ 构造

    def _make_control(self, fld: schema.Field) -> QWidget:
        if fld.widget in _TEXT_WIDGETS:
            w = QLineEdit()
            w.setClearButtonEnabled(True)
            # textChanged 而不是 editingFinished：后者只在焦点离开 / 回车时才发，
            # 会导致用户刚敲字时「保存」按钮不亮。textChanged 每次编辑都发；
            # 程序化 setText（set_value）被 _syncing 挡住。
            w.textChanged.connect(self._emit_text)
            return w

        if fld.widget == schema.WIDGET_INT:
            w = QSpinBox()
            w.setRange(fld.minimum, fld.maximum)
            if fld.suffix:
                w.setSuffix(fld.suffix)
            w.setMaximumWidth(INT_WIDTH)
            w.setMinimumWidth(90)
            w.valueChanged.connect(self._emit_int)
            return w

        if fld.widget == schema.WIDGET_BOOL:
            w = QCheckBox()
            w.toggled.connect(self._emit_bool)
            return w

        if fld.widget == schema.WIDGET_ENUM:
            w = QComboBox()
            for value, text in fld.options:
                w.addItem(text, value)
            w.setMaximumWidth(ENUM_WIDTH)
            w.setMinimumWidth(120)
            w.currentIndexChanged.connect(self._emit_enum)
            return w

        # 兜底：当文本框处理，至少不会崩
        w = QLineEdit()
        w.textChanged.connect(self._emit_text)
        return w

    # ------------------------------------------------------------ 事件

    def _emit_text(self, _text: str = "") -> None:
        if not self._syncing:
            self.changed.emit(self.key, self.control.text())

    def _emit_int(self, value: int) -> None:
        if not self._syncing:
            self.changed.emit(self.key, int(value))

    def _emit_bool(self, checked: bool) -> None:
        if not self._syncing:
            self.changed.emit(self.key, bool(checked))

    def _emit_enum(self, index: int) -> None:
        if not self._syncing and index >= 0:
            self.changed.emit(self.key, self.control.itemData(index))

    # ------------------------------------------------------------ 同步

    def set_value(self, value, force: bool = False) -> None:
        """把 controller 的值写进控件。

        ``force=False`` 时**跳过仍有焦点的文本框**：否则会把用户正在输入、尚未
        提交的内容重置掉（对应 QML 时期「setField 默认不发 fieldsChanged」的约束）。
        """
        if not force and isinstance(self.control, QLineEdit) and self.control.hasFocus():
            return

        self._syncing = True
        try:
            f = self.fld
            if f.widget in _TEXT_WIDGETS:
                self.control.setText("" if value is None else str(value))
            elif f.widget == schema.WIDGET_INT:
                try:
                    n = int(value)
                except (TypeError, ValueError):
                    n = int(f.default) if f.default is not None else 0
                self.control.setValue(max(f.minimum, min(f.maximum, n)))
            elif f.widget == schema.WIDGET_BOOL:
                self.control.setChecked(bool(value))
            elif f.widget == schema.WIDGET_ENUM:
                idx = self.control.findData(value)
                if idx >= 0:
                    self.control.setCurrentIndex(idx)
        finally:
            self._syncing = False


class CollapsibleSection(QGroupBox):
    """可折叠分组：`QGroupBox(checkable=True)`——勾选框就是展开 / 收起。

    为什么用 checkable 的 QGroupBox：标题栏、勾选框、边框全部由当前 QStyle
    （Kvantum / Fusion / …）绘制，深浅主题都不需要自己调色；自己画箭头反而容易
    和主题不一致。

    注意：Qt 会在**取消勾选时禁用全部子控件**。所以收起时必须把 `body` 一并
    隐藏——否则子控件会变灰（虽然不可见），而且重新展开时 Qt 会把它们全部
    `setEnabled(True)`，会覆盖掉我们自己设过的禁用状态（目前没有这种控件，
    但将来加“根据其它字段禁用的控件”时要知道这一点）。
    """

    def __init__(self, title: str, opened: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(opened)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        self.body = QWidget()
        self.body.setVisible(opened)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        outer.addWidget(self.body)

        self.toggled.connect(self.body.setVisible)

    def add(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)


class SecretRow(QWidget):
    """密码行：输入密码 + 保存 / 清除。

    这不是 schema 字段：密码不进 .rdp，只进系统钥匙串（见 core/secrets.py）。
    本控件只负责收集与展示，读写钥匙串和 ``gui_`` 标记都在 AppController。
    """

    setRequested = pyqtSignal(str)
    clearRequested = pyqtSignal()
    purgeRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        label = QLabel("密码")
        label.setFixedWidth(LABEL_WIDTH)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setToolTip(
            "保存到系统钥匙串（Secret Service），连接时自动填入。\n"
            "密码不会写进 .rdp，也不会出现在命令行（走 FREERDP_ASKPASS）。"
        )
        lay.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)

        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setClearButtonEnabled(True)
        self.edit.setPlaceholderText("输入密码后点「保存」…")
        self.edit.returnPressed.connect(self._emit_set)
        lay.addWidget(self.edit, 1)

        self.btn_save = QPushButton("保存")
        self.btn_save.clicked.connect(self._emit_set)
        lay.addWidget(self.btn_save, 0)

        self.btn_clear = QPushButton("清除")
        self.btn_clear.clicked.connect(self.clearRequested.emit)
        lay.addWidget(self.btn_clear, 0)

        self.btn_purge = QPushButton("全部…")
        self.btn_purge.setToolTip("清除本程序在系统钥匙串里保存的所有密码")
        self.btn_purge.clicked.connect(self.purgeRequested.emit)
        lay.addWidget(self.btn_purge, 0)

        self.status = QLabel()
        self.status.setEnabled(False)
        self.status.setMinimumWidth(90)
        lay.addWidget(self.status, 0)

    def _emit_set(self) -> None:
        pw = self.edit.text()
        if pw:
            self.setRequested.emit(pw)

    def clear_input(self) -> None:
        self.edit.clear()

    def set_state(self, supported: bool, saved: bool, hint: str = "") -> None:
        self.edit.setEnabled(supported)
        self.btn_save.setEnabled(supported)
        self.btn_clear.setEnabled(supported and saved)
        self.btn_purge.setEnabled(supported)
        self.status.setText(hint)
