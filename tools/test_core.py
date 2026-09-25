#!/usr/bin/env python3
"""核心层测试：rdpfile / extraargs / profiles / schema / launch / Bridge。

不需要显示器（Qt 用 offscreen），使用临时的 XDG 目录，不碰你的真实配置。

用法:
    python3 tools/test_core.py
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

# 禁止产生 core dump —— 万一又踩到 QML/Qt 崩溃，不要往磁盘写几百 MB
ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True).prctl(4, 0, 0, 0, 0)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 必须在 import core.profiles 之前隔离 XDG
_TMP = tempfile.mkdtemp(prefix="sdl-gui-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "cfg")
os.environ["XDG_RUNTIME_DIR"] = os.path.join(_TMP, "run")
os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

from core import extraargs, launch, profiles, schema  # noqa: E402
from core.rdpfile import RdpFile  # noqa: E402


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, name: str, cond: bool, detail: str = "") -> bool:
        if cond:
            self.passed += 1
        else:
            self.failures.append(f"{name}{(' — ' + detail) if detail else ''}")
            print(f"  ✗ {name}{(' — ' + detail) if detail else ''}")
        return bool(cond)

    def eq(self, name: str, got: object, want: object) -> bool:
        return self.check(name, got == want, f"实际 {got!r}，期望 {want!r}")

    def group(self, title: str) -> None:
        print(f"\n== {title} ==")

    def finish(self) -> int:
        print(f"\n{self.passed} 项通过，{len(self.failures)} 项失败")
        for f in self.failures:
            print("  -", f)
        return 1 if self.failures else 0


R = Report()


# --------------------------------------------------------------- rdpfile

def test_rdpfile() -> None:
    R.group("rdpfile")

    f = RdpFile()
    f.set("full address", "192.168.1.10")
    f.set("server port", 3390)
    f.set("redirectclipboard", False)
    f.set("drivestoredirect", "Shared(/home/user)")
    f.set("gui_extra_args", "/cert:ignore /sec:tls")
    f.set("unknown_key", "保留我")
    text = f.dumps()

    g = RdpFile.loads(text)
    R.eq("往返一致", g.dumps(), text)
    R.eq("字符串", g.get_str("full address"), "192.168.1.10")
    R.eq("整数", g.get_int("server port"), 3390)
    R.eq("布尔 False", g.get_bool("redirectclipboard", True), False)
    R.eq("含括号的值", g.get_str("drivestoredirect"), "Shared(/home/user)")
    R.eq("含冒号的值", g.get_str("gui_extra_args"), "/cert:ignore /sec:tls")
    R.eq("未知键被保留", g.get_str("unknown_key"), "保留我")

    # BOM / CRLF / 注释行 / 重复键
    messy = "\ufefffull address:s:a.b\r\n# 注释\r\nserver port:i:1\r\nserver port:i:2\n"
    m = RdpFile.loads(messy)
    R.eq("BOM+CRLF 解析", m.get_str("full address"), "a.b")
    R.eq("重复键取最后一个", m.get_int("server port"), 2)
    R.check("无法识别的行被保留", "# 注释" in m.dumps())

    R.eq("缺失键返回默认值", RdpFile().get_int("server port", 3389), 3389)
    R.check("未设置的键不在 keys 里", "server port" not in RdpFile())


# --------------------------------------------------------------- extraargs

def test_extraargs() -> None:
    R.group("extraargs")
    P = extraargs.SECURITY_PREFIX
    R.eq("新增", extraargs.set_token("", P, "/sec:tls"), "/sec:tls")
    R.eq("追加不破坏已有参数", extraargs.set_token("/cert:ignore", P, "/sec:tls"),
         "/cert:ignore /sec:tls")
    R.eq("替换", extraargs.set_token("/cert:ignore /sec:tls", P, "/sec:nla"),
         "/cert:ignore /sec:nla")
    R.eq("删除（前面的参数保留）", extraargs.set_token("/sec:tls /cert:ignore", P, ""),
         "/cert:ignore")
    R.eq("删除（后面的参数保留）", extraargs.set_token("/cert:ignore /sec:tls", P, ""),
         "/cert:ignore")
    R.eq("删除（夹在中间）",
         extraargs.set_token("/cert:ignore /sec:nla,ext +dynamic-resolution", P, ""),
         "/cert:ignore +dynamic-resolution")
    R.eq("不误伤其它前缀", extraargs.set_token("/cert:ignore", P, ""), "/cert:ignore")

    for src, want in [("", 0), ("/sec:tls", 1), ("/cert:ignore /sec:nla", 2),
                      ("/sec:nla,ext", 3), ("/sec:rdp", 4), ("/cert:ignore", 0)]:
        R.eq(f"反推索引 {src!r}", extraargs.security_index(src), want)


# --------------------------------------------------------------- profiles

def test_profiles() -> None:
    R.group("profiles")
    profiles.ensure_dirs()
    f = RdpFile()
    f.set("full address", "10.0.0.1")
    f.set("server port", 3390)
    profiles.save("办公室", f)

    got = profiles.list_profiles()
    R.eq("列出 1 个", len(got), 1)
    R.eq("名称", got[0].name, "办公室")
    R.eq("载入的内容", profiles.load("办公室").get_int("server port"), 3390)

    R.eq("非法字符被替换", profiles.sanitize("a/b:c"), "a_b_c")
    R.eq("空名回退", profiles.sanitize("   "), "未命名")

    profiles.save("办公室", f)
    R.eq("覆盖保存不产生副本", len(profiles.list_profiles()), 1)

    moved = profiles.delete("办公室")
    R.check("软删除到 trash/", moved is not None and moved.parent.name == "trash")
    R.eq("删除后列表为空", len(profiles.list_profiles()), 0)


# --------------------------------------------------------------- schema

def test_schema() -> None:
    R.group("schema")
    from core.keymap import DEAD_KEYS
    R.check("schema 不含死键",
            not [f.key for f in schema.FIELDS
                 if f.key in DEAD_KEYS and not f.key.startswith("gui_")])
    R.check("虚拟字段不参与序列化", "gui_security" in schema.VIRTUAL_KEYS)
    R.check("每个字段都有分组", all(schema.BY_KEY[f.key].group for f in schema.FIELDS))
    R.check("音频默认写入（absent != default）",
            schema.BY_KEY["audiomode"].absent_value != schema.BY_KEY["audiomode"].default)


# --------------------------------------------------------------- Bridge

def test_bridge() -> None:
    R.group("Bridge")
    from PyQt6.QtGui import QGuiApplication
    from app import Bridge

    _ = QGuiApplication.instance() or QGuiApplication([])
    profiles.ensure_dirs()
    b = Bridge()

    # 新建草稿必须把「默认值 != 缺失行为」的字段显式写出来
    b.setField("full address", "10.1.2.3")
    data = b._collect()
    explicit = {
        f.key for f in schema.FIELDS
        if f.key not in schema.VIRTUAL_KEYS
        and not (f.widget == schema.WIDGET_TEXT and not str(f.default).strip())
        and f.default != f.absent_value
    }
    missing = sorted(k for k in explicit if not data.has(k))
    R.check("草稿写出全部必需的显式键", not missing, f"缺 {missing}")
    R.eq("音频被显式写出", data.get_int("audiomode", -1), 0)

    # 音频三态：本机/服务器播放要写出来，「不播放」等于缺失行为因而省略
    for idx, label, want in [(0, "在本机播放", 0), (1, "在服务器播放", 1), (2, "不播放", None)]:
        b.setField("audiomode", idx)
        d = b._collect()
        got = d.get_int("audiomode", -1) if d.has("audiomode") else None
        R.check(f"音频「{label}」", got == want, f"文件里 {got!r}，期望 {want!r}")

    # 安全方式 <-> gui_extra_args 双向联动
    b.setField("gui_extra_args", "/cert:ignore /sec:nla +dynamic-resolution")
    R.eq("手写 extra_args 回推下拉", b.fields["gui_security"], 2)
    b.setField("gui_security", 1)
    R.eq("下拉改写 extra_args（保留其它参数）", b.fields["gui_extra_args"],
         "/cert:ignore /sec:tls +dynamic-resolution")

    # 保存 → 重新载入 往返
    b.setField("full address", "10.1.2.3")
    b.saveAs("往返")
    before = dict(b.fields)
    b.selectProfile("往返")
    diff = sorted(k for k in before if before[k] != b.fields.get(k))
    R.check("保存→重载 值不变", not diff, f"不一致: {diff}")

    # 载入不含 audiomode 的外部文件：应显示真实的「不播放」
    p = profiles.path_for("外部")
    p.write_text("full address:s:10.9.9.9\ndesktopwidth:i:1024\n")
    b.selectProfile("外部")
    R.eq("缺失键显示真实行为（音频）", b.fields["audiomode"], 2)
    b.save()
    R.check("未改动的缺失键不会凭空写入", "audiomode" not in p.read_text())


# --------------------------------------------------------------- launch

def test_launch() -> None:
    R.group("launch")
    R.check("找到 FreeRDP 客户端", bool(launch.find_binary()))
    cmd = launch.build_command(Path("/tmp/x.rdp"), "/cert:ignore /sec:tls")
    R.eq("参数个数", len(cmd), 4)
    R.eq("第一个参数是文件", cmd[1], "/tmp/x.rdp")
    cmd2 = launch.build_command(Path("/tmp/x.rdp"), '/drive:"My Docs,/home/u/My Docs"')
    R.check("引号内的空格不被拆分", len(cmd2) == 3, f"实际 {cmd2}")


def main() -> int:
    try:
        test_rdpfile()
        test_extraargs()
        test_profiles()
        test_schema()
        test_bridge()
        test_launch()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    return R.finish()


if __name__ == "__main__":
    sys.exit(main())
