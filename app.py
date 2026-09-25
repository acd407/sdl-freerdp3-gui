#!/usr/bin/env python3
"""sdl-freerdp3-gui —— 一个 .rdp 配置编辑器 + 启动器。

架构
----
Python 负责**全部** .rdp 语义（键名、类型、布尔反转、序列化），QML 只负责渲染和
收集输入。因此 UI 层可以随时替换，核心逻辑也能脱离 GUI 单测。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Fusion 是桌面风格；必须在使用 QApplication 之前设好。
# （PyQt6 没有 QtQuickControls2 模块，不能调 QQuickStyle.setStyle()）
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

from PyQt6.QtCore import (  # noqa: E402
    QObject,
    QTimer,
    QUrl,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtQml import QQmlApplicationEngine  # noqa: E402

from core import extraargs, launch, profiles, schema  # noqa: E402
from core.rdpfile import KEY_EXTRA_ARGS, Entry, RdpFile  # noqa: E402

APP_ID = "sdl-freerdp3-gui"
SECURITY_KEY = "gui_security"
DRAFT_LABEL = "快速连接"
DEFAULT_W, DEFAULT_H = 1060, 740


class Bridge(QObject):
    """暴露给 QML 的唯一对象。"""

    profilesChanged = pyqtSignal()
    fieldsChanged = pyqtSignal()
    previewChanged = pyqtSignal()
    titleChanged = pyqtSignal()
    statusChanged = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._schema = schema.SCHEMA_FOR_QML
        self._state = profiles.load_state()
        self._rdp = RdpFile()
        self._source: str | None = None  # None = 草稿
        self._dirty = False
        self._message = ""
        self._search = ""
        self._values: dict[str, Any] = {}
        self._cache: list = []
        try:
            self._binary = launch.find_binary()
        except launch.LaunchError:
            self._binary = ""
        self.refresh_profiles()
        # 启动时的初始状态就是一份新草稿，所以用「期望默认值」而不是「缺失行为」
        self._reload_values(use_defaults=True)

    # ------------------------------------------------------------ 属性

    @pyqtProperty("QVariantList", constant=True)
    def schema(self) -> list:
        return self._schema

    @pyqtProperty(str, constant=True)
    def schemaJson(self) -> str:
        """以 JSON 字符串暴露 schema，QML 侧 JSON.parse 成纯 JS 数组。

        不要直接传嵌套的 Python dict/list：QML 对 QVariantList<QVariantMap> 暴露的
        是「map 的键作为 role」，嵌套 Repeater 里 modelData 并不可靠（实测 52 个
        字段全部拿到 undefined）。转成真正的 JS 数组后行为完全确定。
        """
        return json.dumps(self._schema, ensure_ascii=False)


    @pyqtProperty("QVariantList", notify=profilesChanged)
    def profiles(self) -> list:
        return [
            {"name": p.name, "host": p.host, "subtitle": p.subtitle}
            for p in self._cache
        ]

    @pyqtProperty("QVariantList", notify=profilesChanged)
    def visibleProfiles(self) -> list:
        q = self._search.strip().lower()
        items = self.profiles
        if not q:
            return items
        return [
            i
            for i in items
            if q in i["name"].lower()
            or q in i["host"].lower()
            or q in i["subtitle"].lower()
        ]

    @pyqtProperty(str, notify=profilesChanged)
    def profileCount(self) -> str:
        return f"{len(self._cache)} 个配置"

    @pyqtProperty(str, constant=True)
    def draftLabel(self) -> str:
        return DRAFT_LABEL

    @pyqtProperty("QVariantMap", notify=fieldsChanged)
    def fields(self) -> dict:
        return self._values

    @pyqtProperty(str, notify=previewChanged)
    def previewText(self) -> str:
        return self._render_preview()

    @pyqtProperty(str, notify=titleChanged)
    def title(self) -> str:
        if self._source is not None:
            return self._source
        host = self._values.get("full address", "")
        return str(host) if host else "未命名"

    @pyqtProperty(bool, notify=titleChanged)
    def dirty(self) -> bool:
        return self._dirty

    @pyqtProperty(bool, notify=titleChanged)
    def isDraft(self) -> bool:
        return self._source is None

    @pyqtProperty(bool, notify=titleChanged)
    def canRevert(self) -> bool:
        return self._source is not None and self._dirty

    @pyqtProperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._message

    @pyqtProperty(str, constant=True)
    def binaryHint(self) -> str:
        return Path(self._binary).name if self._binary else "未找到 FreeRDP 客户端"

    @pyqtProperty(int, constant=True)
    def initialWidth(self) -> int:
        return int(self._state.get("w", DEFAULT_W))

    @pyqtProperty(int, constant=True)
    def initialHeight(self) -> int:
        return int(self._state.get("h", DEFAULT_H))

    @pyqtProperty(str, notify=profilesChanged)
    def search(self) -> str:
        return self._search

    @search.setter
    def search(self, value: str) -> None:
        if value != self._search:
            self._search = value
            self.profilesChanged.emit()

    # ------------------------------------------------------------ 内部

    def refresh_profiles(self) -> None:
        self._cache = profiles.list_profiles()
        self.profilesChanged.emit()

    def _reload_values(self, use_defaults: bool = False) -> None:
        """从 self._rdp 重算 UI 值。

        use_defaults=False（载入已有文件）：缺失的键取 ``absent_value``——
        即 FreeRDP 键缺失时的真实行为，而不是「我们希望的值」。否则界面会
        显示一个并未生效的值（例如 .rdp 里没有 audiomode 时其实音频是全关的）。

        use_defaults=True（新建草稿）：取 ``default``，即新建配置期望的值；
        这些值随后会被真正写进文件（因为 default != absent）。
        """
        values: dict[str, Any] = {
            f.key: (f.default if use_defaults else f.absent_value) for f in schema.FIELDS
        }
        for f in schema.FIELDS:
            if not self._rdp.has(f.key):
                continue
            raw: Any = (
                self._rdp.get_int(f.key, 0)
                if f.type == "i"
                else self._rdp.get_str(f.key, "")
            )
            values[f.key] = schema.file_to_ui(f, raw)

        # 虚拟字段：由 gui_extra_args 派生
        values[SECURITY_KEY] = extraargs.security_index(str(values.get(KEY_EXTRA_ARGS, "") or ""))

        self._values = values
        self.fieldsChanged.emit()
        self.previewChanged.emit()
        self.titleChanged.emit()

    def _collect(self) -> RdpFile:
        """合成最小化的 .rdp：非 schema 键原样保留，schema 字段只写非默认值。"""
        out = RdpFile()
        schema_keys = {f.key for f in schema.FIELDS}
        for e in self._rdp.entries:
            if e.type is not None and e.key not in schema_keys:
                out.entries.append(Entry(e.key, e.type, e.value))

        for f in schema.FIELDS:
            if f.key in schema.VIRTUAL_KEYS:
                continue
            ui = self._values.get(f.key, f.default)
            if f.widget == schema.WIDGET_TEXT and not str(ui).strip():
                continue
            # 只在与「键缺失时的行为」相同时才省略，否则必须写出来
            if ui == f.absent_value:
                continue
            out.set(f.key, schema.ui_to_file(f, ui))
        return out

    def _render_preview(self) -> str:
        return self._collect().dumps()

    def _set_message(self, text: str) -> None:
        self._message = text
        self.statusChanged.emit()

    def _mark(self, dirty: bool = True) -> None:
        self._dirty = dirty
        self.titleChanged.emit()

    # ------------------------------------------------------------ 槽

    @pyqtSlot()
    def newDraft(self) -> None:
        self._rdp = RdpFile()
        self._source = None
        self._mark(False)
        self._reload_values(use_defaults=True)
        self._set_message("新配置（尚未保存）")

    @pyqtSlot(str)
    def selectProfile(self, name: str) -> None:
        if name == DRAFT_LABEL:
            self.newDraft()
            return
        try:
            self._rdp = profiles.load(name)
        except OSError as exc:
            self._set_message(f"读取失败: {exc}")
            return
        self._source = name
        self._mark(False)
        self._reload_values()
        self._set_message(f"已载入 {name}")

    @pyqtSlot(str, "QVariant")
    def setField(self, key: str, value: Any) -> None:
        f = schema.BY_KEY.get(key)
        if f is None:
            return
        if self._values.get(key) == value and key != KEY_EXTRA_ARGS:
            return

        self._values[key] = value

        # 「安全方式」是虚拟字段：把选择写进 gui_extra_args 里的 /sec: token，
        # 其余手写参数原样保留。
        if key == SECURITY_KEY:
            extra = str(self._values.get(KEY_EXTRA_ARGS, "") or "")
            self._values[KEY_EXTRA_ARGS] = extraargs.set_token(
                extra, extraargs.SECURITY_PREFIX, extraargs.security_token(int(value))
            )
        elif key == KEY_EXTRA_ARGS:
            # 反过来：手写改了 extra_args，下拉也要跟着走
            self._values[SECURITY_KEY] = extraargs.security_index(str(value or ""))

        self._mark(True)
        if key in (SECURITY_KEY, KEY_EXTRA_ARGS):
            # 这两个字段互相联动，需要让另一侧的控件刷新。
            # 此时没有输入框处于未提交状态（onEditingFinished 先于本调用触发）。
            self.fieldsChanged.emit()
        # 平时只刷新预览；**不**发 fieldsChanged，否则正在编辑的输入框会被重置
        self.previewChanged.emit()
        self.titleChanged.emit()

    @pyqtSlot(str, result=bool)
    def saveAs(self, name: str) -> bool:
        if not name.strip():
            return False
        target = profiles.sanitize(name)
        if self._source and target == self._source:
            return self.save()
        if profiles.path_for(target).exists():
            target = profiles.available_name(target)
        data = self._collect()
        try:
            profiles.save(target, data)
        except OSError as exc:
            self._set_message(f"保存失败: {exc}")
            return False
        # 关键：把落盘的内容回写成内存状态，否则紧接着的 _reload_values()
        # 会从**旧的** self._rdp 重算，把刚填的表单清空。
        self._rdp = data
        self._source = target
        self._mark(False)
        self._reload_values()
        self.refresh_profiles()
        self._set_message(f"已保存为 {target}.rdp")
        return True

    @pyqtSlot(result=bool)
    def save(self) -> bool:
        if self._source is None:
            return False
        data = self._collect()
        try:
            profiles.save(self._source, data)
        except OSError as exc:
            self._set_message(f"保存失败: {exc}")
            return False
        self._rdp = data
        self._mark(False)
        self.refresh_profiles()
        self._set_message(f"已保存 {self._source}")
        return True

    @pyqtSlot()
    def revert(self) -> None:
        if self._source is not None:
            self.selectProfile(self._source)

    @pyqtSlot(str, result=bool)
    def deleteProfile(self, name: str) -> bool:
        if name == DRAFT_LABEL or not name:
            return False
        moved = profiles.delete(name)
        if moved is None:
            return False
        if self._source == name:
            self.newDraft()
        self.refresh_profiles()
        self._set_message(f"已移入回收站: {moved.name}")
        return True

    @pyqtSlot(result=str)
    def connectNow(self) -> str:
        """写出 .rdp（草稿写运行目录），然后启动客户端。"""
        if not self._values.get("full address", "").strip():
            self._set_message("请先填写服务器地址")
            return "no address"

        extra = str(self._values.get(KEY_EXTRA_ARGS, "") or "")
        try:
            if self._source is None:
                path = profiles.write_draft(self._collect())
            else:
                data = self._collect()
                profiles.save(self._source, data)
                self._rdp = data
                path = profiles.path_for(self._source)
                self._mark(False)
                self.refresh_profiles()
            pid = launch.launch(path, extra)
        except (launch.LaunchError, OSError) as exc:
            self._set_message(f"启动失败: {exc}")
            return str(exc)

        self._set_message(f"已启动 {self.binaryHint} (pid {pid})")
        return ""

    @pyqtSlot(int, int)
    def saveWindowSize(self, w: int, h: int) -> None:
        self._state["w"] = w
        self._state["h"] = h
        profiles.save_state(self._state)


def main() -> int:
    profiles.ensure_dirs()

    app = QGuiApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setOrganizationName(APP_ID)

    # 用模块级引用持有，避免局部变量在函数返回时被早于预期地回收
    global _BRIDGE, _ENGINE
    _BRIDGE = Bridge()
    _ENGINE = QQmlApplicationEngine()
    _ENGINE.rootContext().setContextProperty("bridge", _BRIDGE)

    qml = Path(__file__).parent / "ui" / "Main.qml"
    _ENGINE.load(QUrl.fromLocalFile(str(qml)))
    if not _ENGINE.rootObjects():
        print("QML 加载失败", file=sys.stderr)
        return 1

    # 冒烟测试用：设置 SDL_GUI_SMOKE_TEST=<毫秒> 后自动退出，
    # 从而真正走一遍正常退出路径（包括 shutdown() 的析构顺序）。
    smoke = os.environ.get("SDL_GUI_SMOKE_TEST")
    if smoke:
        QTimer.singleShot(int(smoke), app.quit)

    rc = app.exec()
    shutdown()
    return rc


_BRIDGE: "Bridge | None" = None
_ENGINE: "QQmlApplicationEngine | None" = None


def shutdown() -> None:
    """按正确顺序销毁。

    QML 的对象和绑定都由 engine 持有；必须在销毁 bridge（Python QObject）**之前**
    先销毁 engine。顺序反了的话，QML 绑定会在 bridge 消失后再求值一次，Qt 产生
    warning，而 PyQt6 会把 QML warning 升级为 qFatal —— 进程直接 abort。
    """
    global _BRIDGE, _ENGINE
    _ENGINE = None   # 先 QML 侧
    _BRIDGE = None   # 再 Python 侧


if __name__ == "__main__":
    sys.exit(main())
