"""probeutil — 编译并使用 FreeRDP 的 C 探针。

`probe.c` 链接本机的 FreeRDP 头文件/库，能把一个 .rdp 文件解析后的**全部
settings** dump 出来。`genschema.py` 和 `audit_defaults.py` 都依赖它。

探针是针对**本机安装的 FreeRDP 版本**编译的，所以升级 FreeRDP 后重跑即可。
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_SRC = os.path.join(HERE, "probe.c")
PROBE_BIN = os.path.join(HERE, "probe")

# 每次 populate 都会重新生成的随机值，属于噪声
NOISE = {"FreeRDP_CorrelationId"}


class ProbeError(RuntimeError):
    pass


def ensure_probe() -> str:
    """必要时编译探针，返回可执行文件路径。"""
    if os.path.exists(PROBE_BIN) and os.path.getmtime(PROBE_BIN) > os.path.getmtime(PROBE_SRC):
        return PROBE_BIN

    cmd = [
        "gcc", "-O1", "-w", PROBE_SRC, "-o", PROBE_BIN,
        "-I/usr/include/freerdp3", "-I/usr/include/winpr3",
        "-lfreerdp3", "-lfreerdp-client3", "-lwinpr3",
    ]
    print("[probe] 编译探针:", " ".join(cmd), file=sys.stderr)
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise ProbeError(
            "找不到 gcc。探针需要编译，请安装 gcc 与 freerdp 的开发头文件\n"
            "  Arch:  pacman -S gcc freerdp"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ProbeError(
            f"编译失败（{exc.returncode}）。请确认装了 /usr/include/freerdp3 与 winpr3。\n"
            "  Arch:  pacman -S freerdp"
        ) from exc
    return PROBE_BIN


def dump_file(path: str) -> dict[str, str] | None:
    """解析一个 .rdp 文件并返回 {setting 名: 值的字符串}；解析失败返回 None。"""
    bin_ = ensure_probe()
    r = subprocess.run([bin_, path, "--dump"], capture_output=True, text=True)
    if "populate_ok=TRUE" not in r.stdout:
        return None
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if not line.startswith("S\t"):
            continue
        _, name, _type, value = line.split("\t", 3)
        if name not in NOISE:
            out[name] = value
    return out


def dump_text(text: str) -> dict[str, str] | None:
    """把内容写成临时文件再 dump。"""
    tmp = os.path.join(HERE, "_probe_tmp.rdp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        return dump_file(tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
