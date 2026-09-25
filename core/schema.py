"""schema — UI 用的字段表：分组、中文标签、控件类型、默认值。

只包含在本机 FreeRDP 上**实测有效**的键。死键由 ``keymap.DEAD_KEYS`` 自动排除
（见 tools/genschema.py）。

每个字段的语义
--------------
``invert``  为 True 时，UI 上勾选 = True，而文件里写 0（.rdp 的 ``disable ...``
            这类反向键）。UI 永远展示正向语义，反转只发生在这里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .extraargs import SECURITY_OPTIONS
from .keymap import DEAD_KEYS, KEY_SETTINGS, KEY_TYPE

# ---------------------------------------------------------------- 结构

WIDGET_TEXT = "text"
WIDGET_INT = "int"
WIDGET_BOOL = "bool"
WIDGET_ENUM = "enum"
WIDGET_PATH = "path"

# 哨兵：表示「键缺失时的行为」与 default 相同
UNSET = object()


@dataclass(frozen=True)
class Field:
    key: str
    group: str
    label: str
    widget: str
    default: Any = ""
    invert: bool = False
    options: tuple[tuple[int, str], ...] = ()
    minimum: int = 0
    maximum: int = 1_000_000
    suffix: str = ""
    help: str = ""
    # 键在 .rdp 里**缺失**时，FreeRDP 实际表现出的 UI 值。
    #
    # 这很关键：_collect() 只写「与 absent 不同」的字段，所以 absent 必须等于
    # FreeRDP 的缺失行为，否则用户选了「默认值」时该键会被跳过、行为被改变。
    # （实测踩过：audiomode 缺失 = 音频全关，而 UI 默认是 0=本机播放，导致选
    #   「本机播放」时反而没有声音。）
    #
    # UNSET 表示 absent 与 default 相同（绝大多数字段属于这种）。
    absent: Any = UNSET

    @property
    def absent_value(self) -> Any:
        return self.default if self.absent is UNSET else self.absent

    @property
    def always_write(self) -> bool:
        return self.absent is None

    @property
    def type(self) -> str:
        t = KEY_TYPE.get(self.key)
        if t == "i":
            return "i"
        if t == "s":
            return "s"
        # 兜底：按控件类型推断
        return "i" if self.widget in (WIDGET_INT, WIDGET_BOOL, WIDGET_ENUM) else "s"


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    open_by_default: bool = False
    fields: tuple[Field, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- 枚举

ENUM_SCREEN_MODE = ((1, "窗口"), (2, "全屏"))
ENUM_BPP = ((8, "8 位"), (15, "15 位"), (16, "16 位"), (24, "24 位"), (32, "32 位 (推荐)"))
ENUM_AUTH_LEVEL = (
    (0, "连接，不校验服务器身份"),
    (1, "校验失败则不连接"),
    (2, "校验失败时警告 (默认)"),
)
ENUM_AUDIO_MODE = ((0, "在本机播放"), (1, "在服务器播放"), (2, "不播放"))
ENUM_CONNECTION_TYPE = (
    (1, "调制解调器 (56k)"),
    (2, "低速宽带"),
    (3, "卫星"),
    (4, "高速宽带"),
    (5, "WAN"),
    (6, "LAN"),
    (7, "自动检测 (推荐)"),
)
ENUM_KEYBOARD_HOOK = ((0, "仅本地"), (1, "仅远程"), (2, "全屏时转发到远程"))
ENUM_SCALE_FACTOR = tuple((v, f"{v}%") for v in (100, 125, 150, 175, 200))
ENUM_DESKTOP_SIZE_ID = (
    (0, "由下面的宽高决定"),
    (1, "640 x 480"),
    (2, "800 x 600"),
    (3, "1024 x 768"),
    (4, "1280 x 1024"),
    (5, "1600 x 1200"),
)


# ---------------------------------------------------------------- 字段表
#
# 说明：``gui_extra_args`` 不是 .rdp 标准键，而是本项目的自定义键。
# 实测 FreeRDP 会静默忽略未知键并原样保留，所以可以安全地放在同一个文件里。

FIELDS: tuple[Field, ...] = (
    # ---------------- 连接 ----------------
    Field("full address", "connection", "服务器地址", WIDGET_TEXT,
          help="主机名、IPv4、IPv6 或 URL"),
    Field("server port", "connection", "端口", WIDGET_INT, 3389,
          minimum=1, maximum=65535),
    Field("gatewayhostname", "connection", "RD 网关", WIDGET_TEXT,
          help="留空表示不使用网关"),
    Field("gui_extra_args", "connection", "额外命令行参数", WIDGET_TEXT,
          help="写不进 .rdp 的参数，例如 /cert:ignore /sec:tls"),

    # ---------------- 认证 ----------------
    # 虚拟字段：不对应任何 .rdp 键，而是映射到 gui_extra_args 里的 /sec: 参数。
    # FreeRDP 的 103 个 .rdp 键里没有任何安全层选项（实测：/sec:tls 会把
    # NlaSecurity 和 RdpSecurity 都关掉，而 .rdp 连 RdpSecurity 都碰不到），
    # 所以只能走命令行。
    Field("gui_security", "auth", "安全方式", WIDGET_ENUM, 0,
          options=tuple((idx, label) for idx, label, _ in SECURITY_OPTIONS),
          help="写入「额外命令行参数」里的 /sec:。服务器要求纯 TLS 时选「仅 TLS」"),
    Field("username", "auth", "用户名", WIDGET_TEXT),
    Field("domain", "auth", "域 / 工作组", WIDGET_TEXT),
    Field("authentication level", "auth", "服务器身份校验", WIDGET_ENUM, 2,
          options=ENUM_AUTH_LEVEL),
    Field("enablecredsspsupport", "auth", "使用 NLA (CredSSP)", WIDGET_BOOL, True),
    Field("negotiate security layer", "auth", "协商安全层", WIDGET_BOOL, True),
    Field("prompt for credentials", "auth", "总是提示输入凭据", WIDGET_BOOL, False),
    Field("administrative session", "auth", "管理员会话", WIDGET_BOOL, False),
    # 键缺失时 AutoReconnectionEnabled=FALSE，所以 True 必须写出来
    Field("autoreconnection enabled", "auth", "断线自动重连", WIDGET_BOOL, True,
          absent=False),
    Field("autoreconnect max retries", "auth", "最大重连次数", WIDGET_INT, 20,
          minimum=0, maximum=1000),

    # ---------------- 显示 ----------------
    Field("screen mode id", "display", "显示模式", WIDGET_ENUM, 1,
          options=ENUM_SCREEN_MODE),
    # 键缺失时 FreeRDP 用 1024x768，所以默认的 1280x800 必须写出来
    Field("desktopwidth", "display", "宽度", WIDGET_INT, 1280,
          minimum=200, maximum=16384, suffix=" px", absent=1024),
    Field("desktopheight", "display", "高度", WIDGET_INT, 800,
          minimum=200, maximum=16384, suffix=" px", absent=768),
    Field("session bpp", "display", "色深", WIDGET_ENUM, 32, options=ENUM_BPP),
    Field("desktopscalefactor", "display", "缩放", WIDGET_ENUM, 100,
          options=ENUM_SCALE_FACTOR),
    Field("dynamic resolution", "display", "窗口缩放时跟随调整分辨率", WIDGET_BOOL, False,
          absent=False),
    Field("smart sizing", "display", "缩放远程画面以适应窗口", WIDGET_BOOL, False),
    Field("use multimon", "display", "使用多个显示器", WIDGET_BOOL, False),
    Field("selectedmonitors", "display", "显示器编号", WIDGET_TEXT,
          help="逗号分隔，如 0,1；配合「使用多个显示器」"),
    Field("span monitors", "display", "跨越所有显示器 (span)", WIDGET_BOOL, False),

    # ---------------- 性能与体验 ----------------
    Field("connection type", "perf", "连接类型", WIDGET_ENUM, 7,
          options=ENUM_CONNECTION_TYPE,
          help="影响 FreeRDP 自动启用的一整套图形/性能选项"),
    Field("compression", "perf", "压缩", WIDGET_BOOL, True),
    # 键缺失时 BitmapCachePersistEnabled=FALSE
    Field("bitmapcachepersistenable", "perf", "持久位图缓存", WIDGET_BOOL, True,
          absent=False),
    Field("allow font smoothing", "perf", "字体平滑 (ClearType)", WIDGET_BOOL, True),
    Field("allow desktop composition", "perf", "桌面合成 (Aero)", WIDGET_BOOL, True),
    Field("disable wallpaper", "perf", "显示桌面壁纸", WIDGET_BOOL, True, invert=True),
    Field("disable full window drag", "perf", "拖动窗口时显示内容", WIDGET_BOOL, True,
          invert=True),
    Field("disable menu anims", "perf", "菜单动画", WIDGET_BOOL, True, invert=True),
    Field("disable themes", "perf", "使用桌面主题", WIDGET_BOOL, True, invert=True),
    Field("keyboardhook", "perf", "Windows 键处理", WIDGET_ENUM, 2,
          options=ENUM_KEYBOARD_HOOK),

    # ---------------- 设备重定向 ----------------
    Field("redirectclipboard", "device", "剪贴板", WIDGET_BOOL, True),
    Field("redirectdrives", "device", "所有磁盘驱动器", WIDGET_BOOL, False),
    Field("drivestoredirect", "device", "共享目录", WIDGET_TEXT,
          help="语法 Shared(/home/user) 或 * 或 C:\\;D:\\，分号分隔"),
    Field("redirectprinters", "device", "打印机", WIDGET_BOOL, False),
    Field("redirectcomports", "device", "串口 / 并口", WIDGET_BOOL, False),
    Field("redirectsmartcards", "device", "智能卡", WIDGET_BOOL, False),
    Field("redirectlocation", "device", "位置信息", WIDGET_BOOL, False),
    Field("redirectwebauthn", "device", "WebAuthn", WIDGET_BOOL, False),
    Field("devicestoredirect", "device", "其他设备", WIDGET_TEXT,
          help="语法见 FreeRDP 文档；留空表示不重定向"),

    # ---------------- 音频 ----------------
    # 键缺失时 AudioPlayback=FALSE 且 RemoteConsoleAudio=FALSE = 音频全关，
    # 对应 UI 上的「不播放」(2)。所以默认的「在本机播放」(0) 必须写进文件。
    Field("audiomode", "audio", "音频播放", WIDGET_ENUM, 0, options=ENUM_AUDIO_MODE,
          absent=2),
    Field("audiocapturemode", "audio", "麦克风输入", WIDGET_BOOL, False),
    Field("videoplaybackmode", "audio", "优化的视频播放", WIDGET_BOOL, False),

    # ---------------- 启动程序 (RemoteApp) ----------------
    Field("remoteapplicationmode", "app", "RemoteApp 模式", WIDGET_BOOL, False),
    Field("remoteapplicationprogram", "app", "程序路径或别名", WIDGET_TEXT),
    Field("remoteapplicationname", "app", "程序显示名", WIDGET_TEXT),
    Field("alternate shell", "app", "启动时运行的程序", WIDGET_TEXT,
          help="登录后自动执行的命令"),
    Field("shell working directory", "app", "工作目录", WIDGET_PATH),
)

GROUP_TITLES: tuple[tuple[str, str, bool], ...] = (
    ("connection", "连接", True),
    ("display", "显示", True),
    ("auth", "认证", True),
    ("device", "设备重定向", False),
    ("perf", "性能与体验", False),
    ("audio", "音频", False),
    ("app", "启动程序", False),
)

# ---------------------------------------------------------------- 派生


def _build() -> tuple[Group, ...]:
    groups: list[Group] = []
    for gid, title, opened in GROUP_TITLES:
        fields = [f for f in FIELDS if f.group == gid]
        if not fields:
            continue
        groups.append(Group(gid, title, opened, tuple(fields)))
    return tuple(groups)


GROUPS: tuple[Group, ...] = _build()
BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}

# 供 UI 层使用的扁平结构（QtWidgets 与 QML 时期同一份，不依赖任何 GUI 框架）
SCHEMA_FOR_UI: list[dict[str, Any]] = [
    {
        "id": g.id,
        "title": g.title,
        "open": g.open_by_default,
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "widget": f.widget,
                "default": f.default,
                "invert": f.invert,
                "suffix": f.suffix,
                "help": f.help,
                "type": f.type,
                "minimum": f.minimum,
                "maximum": f.maximum,
                "intOptions": [list(o) for o in f.options],
            }
            for f in g.fields
        ],
    }
    for g in GROUPS
]


def ui_to_file(fld: Field, ui_value: Any) -> Any:
    """把 UI 值转成要写进文件的原始值（处理 ``invert``）。"""
    if fld.widget == WIDGET_BOOL:
        v = bool(ui_value)
        return (not v) if fld.invert else v
    if fld.widget == WIDGET_ENUM:
        return int(ui_value)
    if fld.widget == WIDGET_INT:
        return int(ui_value)
    return str(ui_value)


def file_to_ui(fld: Field, file_value: Any) -> Any:
    """把文件里的原始值转成 UI 值。"""
    if fld.widget == WIDGET_BOOL:
        v = bool(file_value)
        return (not v) if fld.invert else v
    if fld.widget == WIDGET_ENUM:
        try:
            return int(file_value)
        except (TypeError, ValueError):
            return fld.default
    if fld.widget == WIDGET_INT:
        try:
            return int(file_value)
        except (TypeError, ValueError):
            return fld.default
    return str(file_value) if file_value is not None else ""


# 虚拟字段：由 GUI 特殊处理，不直接写进 .rdp
VIRTUAL_KEYS: frozenset[str] = frozenset({"gui_security"})

# 自检：schema 里不应出现死键
_dead_in_schema = [f.key for f in FIELDS if f.key in DEAD_KEYS and not f.key.startswith("gui_")]
assert not _dead_in_schema, f"schema 包含 FreeRDP 无效果的键: {_dead_in_schema}"

# 自检：非自定义键必须真的驱动了什么 setting
_unknown = [f.key for f in FIELDS
            if not f.key.startswith("gui_") and not KEY_SETTINGS.get(f.key)]
assert not _unknown, f"schema 包含探针未确认的键: {_unknown}"
