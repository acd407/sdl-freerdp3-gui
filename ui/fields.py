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
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QToolButton,
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
            w.editingFinished.connect(self._emit_text)
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
        w.editingFinished.connect(self._emit_text)
        return w

    # ------------------------------------------------------------ 事件

    def _emit_text(self) -> None:
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


class CollapsibleSection(QFrame):
    """可折叠分组：标题按钮 + 内容区。对应原 QML 里点标题展开/收起。"""

    def __init__(self, title: str, opened: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(opened)
        self._toggle.setAutoRaise(True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow
        )
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle.toggled.connect(self._on_toggled)
        outer.addWidget(self._toggle)

        self.body = QWidget()
        self.body.setVisible(opened)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        outer.addWidget(self.body)

    def _on_toggled(self, opened: bool) -> None:
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(opened)

    def add(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)
