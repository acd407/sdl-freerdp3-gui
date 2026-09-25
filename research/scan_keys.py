#!/usr/bin/env python3
"""对 100 个 .rdp 键逐个做探针，得出每个键实际改变了哪些 setting。"""
import subprocess, os, sys, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "probe")
BASE = "full address:s:10.0.0.1\n"

keys = [k.strip() for k in open(os.path.join(HERE, "keys.txt")) if k.strip()]
keys = sorted(set(keys))

LINE_RE = re.compile(r"^\s+(FreeRDP_\S+)\s+(\S+)\s+(.*?) -> (.*)$")


def run(path):
    r = subprocess.run([PROBE, path], capture_output=True, text=True)
    if "parse_ok=TRUE" not in r.stdout:
        return None
    changed = {}
    for line in r.stdout.splitlines():
        m = LINE_RE.match(line)
        if m:
            changed[m.group(1)] = (m.group(3), m.group(4))
    return changed


def baseline():
    p = os.path.join(HERE, "_base.rdp")
    open(p, "w").write(BASE)
    return run(p) or {}


base = baseline()
# CorrelationId / ServerHostname 是噪声
NOISE = {"FreeRDP_CorrelationId"}
base = {k: v for k, v in base.items() if k not in NOISE}
print(f"# 基线注入的 setting 数: {len(base)}", file=sys.stderr)

tmp = os.path.join(HERE, "_scan.rdp")
results = {}
for k in keys:
    found = None
    for typ, val in (("i", "1"), ("s", "testval")):
        open(tmp, "w").write(BASE + f"{k}:{typ}:{val}\n")
        ch = run(tmp)
        if ch is None:
            found = {"parse": "FAIL"}
            break
        ch = {n: v for n, v in ch.items() if n not in NOISE}
        # 去掉与基线相同的项
        extra = {n: v for n, v in ch.items() if base.get(n) != v}
        if extra:
            found = {"type": typ, "value": val, "settings": extra}
            break
    if found is None:
        found = {"settings": {}}
    results[k] = found

os.remove(tmp)
if os.path.exists(os.path.join(HERE, "_base.rdp")):
    os.remove(os.path.join(HERE, "_base.rdp"))
json.dump(results, open(os.path.join(HERE, "keymap.json"), "w"), indent=1, ensure_ascii=False)

alive = [k for k, v in results.items() if v.get("settings")]
dead = [k for k, v in results.items() if not v.get("settings") and v.get("parse") != "FAIL"]
failed = [k for k, v in results.items() if v.get("parse") == "FAIL"]

print(f"\n=== 有效键 {len(alive)} ===")
for k in alive:
    v = results[k]
    s = ", ".join(f"{n}->{val[1]}" for n, val in v["settings"].items())
    print(f"  {k:38s} ({v.get('type')})  {s}")
print(f"\n=== 解析后无任何 setting 变化（疑似死键）{len(dead)} ===")
print("  " + " | ".join(dead))
if failed:
    print(f"\n=== 解析失败 {len(failed)} ===\n  " + " | ".join(failed))
