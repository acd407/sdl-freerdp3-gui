"""AppController —— 界面状态与全部业务操作。

它不 import 任何 widget，只发信号；窗口订阅信号来刷新自己。所以业务逻辑可以
脱离具体控件单测（tools/test_core.py 就是这么用的）。

.rdp 语义（键名 / 类型 / 布尔反转 / 默认值 / absent / 序列化）全部在
``core/schema``，这里只做编排。
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from core import extraargs, launch, profiles, schema
from core.rdpfile import KEY_EXTRA_ARGS, Entry, RdpFile

APP_ID = "sdl-freerdp3-gui"
SECURITY_KEY = "gui_security"
DRAFT_LABEL = "快速连接"
DEFAULT_W, DEFAULT_H = 1060, 740


class AppController(QObject):
    """窗口的唯一数据源。

    信号语义（UI 侧据此刷新，避免无谓地重置正在编辑的输入框）：

    - ``reloaded``    整体重载（载入配置 / 新建 / 保存 / 还原）→ 强制同步全部控件
    - ``valueEdited`` 单个字段被用户改动 → 同步全部控件，但跳过仍有焦点的文本框
    """

    profilesChanged = pyqtSignal()
    reloaded = pyqtSignal()
    valueEdited = pyqtSignal(str)
    previewChanged = pyqtSignal()
    titleChanged = pyqtSignal()
    statusChanged = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._state = profiles.load_state()
        self._rdp = RdpFile()
        self._source: str | None = None  # None = 草稿
        self._dirty = False
        self._message = "新配置（尚未保存）"
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

    # ------------------------------------------------------------ 简单属性

    @property
    def fields(self) -> dict:
        return self._values

    @property
    def previewText(self) -> str:
        return self._render_preview()

    @property
    def title(self) -> str:
        if self._source is not None:
            return self._source
        host = self._values.get("full address", "")
        return str(host) if host else "未命名"

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def isDraft(self) -> bool:
        return self._source is None

    @property
    def canRevert(self) -> bool:
        return self._source is not None and self._dirty

    @property
    def status(self) -> str:
        return self._message

    @property
    def binaryHint(self) -> str:
        return str(self._binary).split("/")[-1] if self._binary else "未找到 FreeRDP 客户端"

    @property
    def draftLabel(self) -> str:
        return DRAFT_LABEL

    @property
    def profileCount(self) -> str:
        return f"{len(self._cache)} 个配置"

    @property
    def visibleProfiles(self) -> list:
        q = self._search.strip().lower()
        items = [
            {"name": p.name, "host": p.host, "subtitle": p.subtitle}
            for p in self._cache
        ]
        if not q:
            return items
        return [
            i
            for i in items
            if q in i["name"].lower() or q in i["host"].lower() or q in i["subtitle"].lower()
        ]

    @property
    def search(self) -> str:
        return self._search

    @search.setter
    def search(self, value: str) -> None:
        if value != self._search:
            self._search = value
            self.profilesChanged.emit()

    def initial_size(self) -> tuple[int, int]:
        return int(self._state.get("w", DEFAULT_W)), int(self._state.get("h", DEFAULT_H))

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
        self.reloaded.emit()
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

    # ------------------------------------------------------------ 操作

    def newDraft(self) -> None:
        self._rdp = RdpFile()
        self._source = None
        self._mark(False)
        self._reload_values(use_defaults=True)
        self._set_message("新配置（尚未保存）")

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
        self.valueEdited.emit(key)
        self.previewChanged.emit()
        self.titleChanged.emit()

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

    def revert(self) -> None:
        if self._source is not None:
            self.selectProfile(self._source)

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

    def saveWindowSize(self, w: int, h: int) -> None:
        self._state["w"] = w
        self._state["h"] = h
        profiles.save_state(self._state)
