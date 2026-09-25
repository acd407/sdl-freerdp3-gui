#!/usr/bin/env python3
"""核心层测试：rdpfile / extraargs / profiles / schema / launch / AppController。

不需要显示器（Qt 用 offscreen），使用临时的 XDG 目录，不碰你的真实配置。

用法:
    python3 tools/test_core.py
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 禁止产生 core dump —— 万一又踩到 Qt 崩溃，不要往磁盘写几百 MB
ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True).prctl(4, 0, 0, 0, 0)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 必须在 import core.profiles 之前隔离 XDG
_TMP = tempfile.mkdtemp(prefix="sdl-gui-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "cfg")
os.environ["XDG_RUNTIME_DIR"] = os.path.join(_TMP, "run")
os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from core import extraargs, launch, profiles, schema  # noqa: E402
from core import secrets  # noqa: E402
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


class FakeSecretBackend:
    """内存钥匙串，供测试用；不接触真实 Secret Service。"""

    name = "fake"

    def __init__(self, available: bool = True) -> None:
        self.store: dict[tuple, str] = {}
        self.available = available

    @staticmethod
    def _key(attrs) -> tuple:
        return tuple(sorted(attrs.items()))

    def get(self, attrs):
        return self.store.get(self._key(attrs))

    def set(self, attrs, secret, label):
        self.store[self._key(attrs)] = secret
        return True

    def delete(self, attrs):
        return self.store.pop(self._key(attrs), None) is not None

    def purge(self):
        self.store.clear()
        return True


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


# --------------------------------------------------------------- secrets

def test_secrets() -> None:
    R.group("secrets")
    ident = secrets.identity_from_values(
        {"full address": "h", "server port": "3390", "username": "u", "domain": ""}
    )
    R.eq("端口转 int", ident.port, 3390)
    attrs = secrets.build_attrs(ident)
    R.eq("空域归一成 -", attrs["domain"], "-")
    R.eq("application 属性", attrs["application"], secrets.APP_ATTR)
    R.eq("属性稳定",
         secrets.build_attrs(secrets.identity_from_values(
             {"full address": "h", "server port": 3390, "username": "u"})),
         attrs)
    R.check("不同身份属性不同",
            secrets.build_attrs(secrets.Identity("h", 3390, "v")) != attrs)
    R.check("缺用户名视为不可用",
            not secrets.identity_from_values({"full address": "h"}).is_usable())
    R.check("地址+用户名可用", ident.is_usable())

    # 会话总线的判定：DBUS 环境变量缺失时，$XDG_RUNTIME_DIR/bus 仍算可用
    # （secret-tool 的 GDBus 会回退到它；曾经漏判导致钥匙串被误报为不可用）
    with tempfile.TemporaryDirectory() as runtime:
        empty = {"XDG_RUNTIME_DIR": runtime}
        R.check("没有环境变量也没有 bus socket 时不可用",
                not secrets.session_bus_available(empty))
        bus = os.path.join(runtime, "bus")
        with open(bus, "w"):
            pass
        R.check("只有 $XDG_RUNTIME_DIR/bus 时可用",
                secrets.session_bus_available(empty))
    R.check("有 DBUS_SESSION_BUS_ADDRESS 时可用",
            secrets.session_bus_available({"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x"}))
    R.check("只有环境变量、socket 不存在也算可用",
            secrets.session_bus_available(
                {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x", "XDG_RUNTIME_DIR": "/nope"}))


# --------------------------------------------------------------- askpass

def test_askpass_helper() -> None:
    R.group("askpass helper")
    script = ROOT / "core" / "askpass.py"
    base_env = {**os.environ, "SFLGUI_SECRET_BACKEND": "none"}

    r = subprocess.run([sys.executable, str(script)], capture_output=True, env=base_env)
    R.eq("无 attrs 时退出 1", r.returncode, 1)
    R.eq("无 attrs 时无输出", r.stdout, b"")

    env2 = {**base_env, "SFLGUI_SECRET_ATTRS": '{"application": "x"}'}
    r2 = subprocess.run([sys.executable, str(script)], capture_output=True, env=env2)
    R.eq("后端不可用时退出 1", r2.returncode, 1)
    R.eq("后端不可用时无输出", r2.stdout, b"")

    env3 = {**base_env, "SFLGUI_SECRET_ATTRS": "not-json"}
    r3 = subprocess.run([sys.executable, str(script)], capture_output=True, env=env3)
    R.eq("坏 JSON 退出 1", r3.returncode, 1)


# --------------------------------------------------------------- AppController

def test_controller() -> None:
    R.group("AppController")
    from PyQt6.QtWidgets import QApplication
    from ui.controller import AppController

    _ = QApplication.instance() or QApplication([])
    profiles.ensure_dirs()
    b = AppController()

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

    # 钥匙串注入：只放 helper 路径和属性，绝不放密码
    attrs = {"application": "x", "host": "h", "username": "u"}
    env = launch.askpass_env(attrs)
    R.check("设置 FREERDP_ASKPASS", "askpass.py" in env["FREERDP_ASKPASS"])
    R.eq("属性以 JSON 传入", json.loads(env["SFLGUI_SECRET_ATTRS"]), attrs)
    R.check("环境里不含密码", "s3cr3t" not in json.dumps(env))


def test_password() -> None:
    R.group("密码 / 钥匙串")
    from PyQt6.QtWidgets import QApplication
    from ui.controller import AppController
    from core.rdpfile import KEY_SAVE_PASSWORD

    _ = QApplication.instance() or QApplication([])
    profiles.ensure_dirs()

    fake = FakeSecretBackend()
    c = AppController(secrets_backend=fake)
    c.setField("full address", "10.2.3.4")
    c.setField("username", "alice")
    R.check("后端可用", c.passwordSupported)
    R.check("初始未保存", not c.passwordSaved)

    R.check("保存密码成功", c.setPassword("s3cr3t"))
    R.check("标记已置", c.passwordSaved)
    attrs = secrets.build_attrs(secrets.identity_from_values(
        {"full address": "10.2.3.4", "server port": 3389, "username": "alice"}))
    R.eq("钥匙串里有密码", fake.get(attrs), "s3cr3t")
    R.check("标记写入 .rdp", c._collect().get_bool(KEY_SAVE_PASSWORD, False))
    R.check("标记可往返", "gui_save_password" in c.previewText)

    # 改动连接身份 → 标记清除（旧条目保留，等待用户清理）
    c.setField("full address", "10.2.3.5")
    R.check("改地址后标记清除", not c.passwordSaved)
    R.eq("旧条目仍在", fake.get(attrs), "s3cr3t")
    c.setField("full address", "10.2.3.4")
    R.check("改回地址不会自动恢复标记", not c.passwordSaved)

    # 清除
    c.setPassword("s3cr3t")
    R.check("清除成功", c.clearPassword())
    R.check("清除后条目消失", fake.get(attrs) is None)
    R.check("清除后标记消失", not c.passwordSaved)

    # 全部清理
    c.setPassword("a")
    c.setField("username", "bob")
    c.setPassword("b")
    R.check("清理全部成功", c.purgePasswords())
    R.eq("清理后钥匙串为空", len(fake.store), 0)

    # 后端不可用时安全降级
    dead = AppController(secrets_backend=FakeSecretBackend(available=False))
    dead.setField("full address", "h")
    dead.setField("username", "u")
    R.check("不可用时不显示支持", not dead.passwordSupported)
    R.check("不可用时保存被拒", not dead.setPassword("x"))

    # 缺用户名时保留密码
    nom = AppController(secrets_backend=FakeSecretBackend())
    nom.setField("full address", "h")
    R.check("缺用户名时保存被拒", not nom.setPassword("x"))


def main() -> int:
    try:
        test_rdpfile()
        test_extraargs()
        test_profiles()
        test_schema()
        test_secrets()
        test_askpass_helper()
        test_controller()
        test_password()
        test_launch()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    return R.finish()


if __name__ == "__main__":
    sys.exit(main())
