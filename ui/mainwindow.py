"""MainWindow —— List-Detail 主界面（QtWidgets 版）。

左：搜索 + 连接列表；右：分组表单 + `.rdp` 预览；底部：状态 + 操作按钮。

界面完全由 `core/schema` 驱动，所以新增字段只需改 schema，不用动这里。
本文件不出现任何 `.rdp` 键名字面量。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core import schema
from ui.controller import AppController
from ui.fields import CollapsibleSection, FieldRow, SecretRow

_DRAFT_ROLE = Qt.ItemDataRole.UserRole
_SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
_IS_DRAFT_ROLE = Qt.ItemDataRole.UserRole + 2


class ProfileDelegate(QStyledItemDelegate):
    """两行列表项：名称（草稿加粗）+ 灰色副标题。"""

    def sizeHint(self, option, index):  # noqa: N802 (Qt 命名)
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 40))
        return size

    def paint(self, painter, option, index):  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        rect = option.rect.adjusted(8, 4, -8, -4)
        painter.save()
        font = painter.font()
        font.setBold(bool(index.data(_IS_DRAFT_ROLE)))
        painter.setFont(font)
        painter.setPen(option.palette.text().color())
        top = rect.adjusted(0, 0, 0, -rect.height() // 2)
        painter.drawText(
            top, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        subtitle = index.data(_SUBTITLE_ROLE)
        if subtitle:
            small = painter.font()
            small.setBold(False)
            small.setPointSizeF(max(7.0, small.pointSizeF() - 1.0))
            painter.setFont(small)
            color = option.palette.text().color()
            color.setAlpha(150)
            painter.setPen(color)
            bottom = rect.adjusted(0, rect.height() // 2, 0, 0)
            painter.drawText(
                bottom, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(subtitle)
            )
        painter.restore()


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.c = controller
        self._rows: dict[str, FieldRow] = {}
        self._rebuilding = False

        self.setMinimumSize(620, 440)
        self.resize(*controller.initial_size())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_form_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 790])

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(splitter, 1)
        outer.addWidget(self._build_bottom_bar())
        self.setCentralWidget(central)

        # 删除快捷键
        act_del = QAction(self)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.triggered.connect(self._on_delete)
        self.addAction(act_del)

        self._connect_controller()
        self._rebuild_list()
        self._sync_form(force=True)
        self._sync_password()
        self._sync_preview()
        self._update_title()
        self._update_buttons()
        self._sync_status()

    # ------------------------------------------------------------ 构建

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称 / 地址…")
        self.search.setClearButtonEnabled(True)
        self.search.textEdited.connect(self._on_search)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setItemDelegate(ProfileDelegate(self.list))
        self.list.setUniformItemSizes(False)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._on_row_changed)
        lay.addWidget(self.list, 1)

        self.count_label = QLabel()
        self.count_label.setEnabled(False)
        lay.addWidget(self.count_label)
        return panel

    def _build_form_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # 名称（界面字段，不是 .rdp 键）
        name_box = CollapsibleSection("名称", opened=True)
        self.name_value = QLabel()
        self.name_value.setWordWrap(True)
        name_box.add(self.name_value)
        lay.addWidget(name_box)

        # 分组表单
        for group in schema.GROUPS:
            section = CollapsibleSection(group.title, opened=group.open_by_default)
            if group.id == "auth":
                # 密码不是 schema 字段（不进 .rdp），单独插在「认证」组最上面
                self.secret_row = SecretRow()
                self.secret_row.setRequested.connect(self._on_password_set)
                self.secret_row.clearRequested.connect(self.c.clearPassword)
                self.secret_row.purgeRequested.connect(self._on_password_purge)
                section.add(self.secret_row)
            for fld in group.fields:
                row = FieldRow(fld)
                row.changed.connect(self._on_field_changed)
                self._rows[fld.key] = row
                section.add(row)
            lay.addWidget(section)

        # .rdp 预览
        preview_box = CollapsibleSection(".rdp 预览", opened=False)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.preview.setFont(mono)
        self.preview.setMinimumHeight(220)
        preview_box.add(self.preview)
        lay.addWidget(preview_box)

        lay.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        self.status_label = QLabel()
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        lay.addWidget(self.status_label, 1)

        self.binary_label = QLabel()
        self.binary_label.setEnabled(False)
        lay.addWidget(self.binary_label, 0)

        self.btn_revert = QPushButton("还原")
        self.btn_revert.clicked.connect(self.c.revert)
        lay.addWidget(self.btn_revert)

        self.btn_delete = QPushButton("删除")
        self.btn_delete.clicked.connect(self._on_delete)
        lay.addWidget(self.btn_delete)

        self.btn_save_as = QPushButton("另存为…")
        self.btn_save_as.clicked.connect(self._on_save_as)
        lay.addWidget(self.btn_save_as)

        self.btn_save = QPushButton("保存")
        self.btn_save.clicked.connect(self._on_save)
        lay.addWidget(self.btn_save)

        self.btn_connect = QPushButton("连接")
        self.btn_connect.clicked.connect(self._on_connect)
        lay.addWidget(self.btn_connect)
        return bar

    def _connect_controller(self) -> None:
        self.c.profilesChanged.connect(self._rebuild_list)
        self.c.reloaded.connect(lambda: self._sync_form(force=True))
        self.c.reloaded.connect(self._sync_preview)
        self.c.reloaded.connect(self._sync_password)
        self.c.valueEdited.connect(lambda _key: self._sync_form())
        self.c.previewChanged.connect(self._sync_preview)
        self.c.titleChanged.connect(self._on_title_changed)
        self.c.statusChanged.connect(self._sync_status)
        self.c.passwordChanged.connect(self._sync_password)

    # ------------------------------------------------------------ 刷新

    def _rebuild_list(self) -> None:
        self._rebuilding = True
        self.list.clear()
        profiles = self.c.visibleProfiles
        current = 0

        self._add_item(self.c.draftLabel, "不保存，直接连接", True, self.c.isDraft)
        for i, p in enumerate(profiles):
            is_current = (not self.c.isDraft and self.c.title == p["name"])
            self._add_item(p["name"], p["subtitle"], False, is_current)
            if is_current:
                current = i + 1

        self.list.setCurrentRow(current)
        self._rebuilding = False
        self.count_label.setText(self.c.profileCount)

    def _add_item(self, name: str, subtitle: str, is_draft: bool, is_current: bool) -> None:
        item = QListWidgetItem(name)
        item.setData(_DRAFT_ROLE, name)
        item.setData(_SUBTITLE_ROLE, subtitle)
        item.setData(_IS_DRAFT_ROLE, is_draft)
        self.list.addItem(item)
        if is_current:
            self.list.setCurrentItem(item)

    def _sync_form(self, force: bool = False) -> None:
        values = self.c.fields
        for key, row in self._rows.items():
            row.set_value(values.get(key, row.fld.default), force=force)

    def _sync_preview(self) -> None:
        self.preview.setPlainText(self.c.previewText)

    def _sync_status(self) -> None:
        self.status_label.setText(self.c.status)

    def _sync_password(self) -> None:
        row = getattr(self, "secret_row", None)
        if row is not None:
            row.set_state(self.c.passwordSupported, self.c.passwordSaved, self.c.passwordHint)

    def _update_title(self) -> None:
        suffix = " •" if self.c.dirty else ""
        self.setWindowTitle(f"sdl-freerdp3 配置 — {self.c.title}{suffix}")
        self.name_value.setText(
            "（未保存 — 点击「保存」命名）" if self.c.isDraft else self.c.title
        )
        self.binary_label.setText(self.c.binaryHint)

    def _update_buttons(self) -> None:
        self.btn_revert.setVisible(self.c.canRevert)
        self.btn_delete.setVisible(not self.c.isDraft)
        self.btn_save_as.setVisible(not self.c.isDraft)
        self.btn_save.setText("保存…" if self.c.isDraft else "保存")
        self.btn_save.setEnabled(self.c.dirty or self.c.isDraft)

    def _on_title_changed(self) -> None:
        self._update_title()
        self._update_buttons()
        self._rebuild_list()

    # ------------------------------------------------------------ 事件

    def _on_search(self, text: str) -> None:
        self.c.search = text

    def _on_row_changed(self, row: int) -> None:
        if self._rebuilding or row < 0:
            return
        item = self.list.item(row)
        if item is not None:
            self.c.selectProfile(item.data(_DRAFT_ROLE))

    def _on_field_changed(self, key: str, value) -> None:
        self.c.setField(key, value)

    def _on_password_set(self, password: str) -> None:
        if self.c.setPassword(password):
            self.secret_row.clear_input()

    def _on_password_purge(self) -> None:
        answer = QMessageBox.question(
            self,
            "清理钥匙串",
            "清除本程序在系统钥匙串里保存的所有 RDP 密码？\n\n"
            "这只影响钥匙串条目，配置文件本身不受影响。",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.c.purgePasswords()

    def _on_save(self) -> None:
        if self.c.isDraft:
            self._on_save_as()
        else:
            self.c.save()

    def _on_save_as(self) -> None:
        default = "" if self.c.isDraft else self.c.title
        name, ok = QInputDialog.getText(self, "保存配置", "配置名称（同时作为文件名）", text=default)
        if ok and name.strip():
            self.c.saveAs(name.strip())

    def _on_delete(self) -> None:
        if self.c.isDraft:
            return
        answer = QMessageBox.question(
            self,
            "删除配置",
            f"把「{self.c.title}」移入回收站？\n\n"
            "文件不会真正删除，可在\n~/.config/sdl-freerdp3-gui/trash/ 找回。",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.c.deleteProfile(self.c.title)

    def _on_connect(self) -> None:
        if self.c.connectNow() == "no address":
            row = self._rows.get("full address")
            if row is not None:
                row.control.setFocus()

    # ------------------------------------------------------------ 生命周期

    def closeEvent(self, event) -> None:  # noqa: N802
        self.c.saveWindowSize(self.width(), self.height())
        super().closeEvent(event)
