# tools/

开发与验证工具。**不参与运行时**，主程序只依赖 `core/`、`app.py`、`ui/`。

```bash
tools/check              # 一键跑全部检查
tools/check --quick      # 跳过较慢的默认值审计（约 4 秒）
```

## 检查脚本

| 文件 | 作用 |
|---|---|
| **`check`** | 一键入口，依次跑下面三个并汇总 |
| **`test_core.py`** | 核心层单元测试：`rdpfile` / `extraargs` / `profiles` / `schema` / `Bridge` / `launch`。用临时 XDG 目录，不碰真实配置 |
| **`check_qml.py`** | 无头加载 `ui/Main.qml`，断言 **0 条 QML 警告** |
| **`audit_defaults.py`** | 逐个字段验证「省略该键」等价于「写入默认值」——见主 README 的「absent 约束」 |

为什么 `check_qml.py` 以「0 警告」为准而不是数控件个数：字段渲染失败的每种已知形态都会产生警告
（`fld` 未注入 → TypeError；Repeater 反复重建 → 旧 delegate 绑定报错；独立组件未声明
`required property` → ReferenceError）。而 `findChildren` 穿不透 Repeater 的 delegate，
`objectCreated` 也不覆盖组件内部对象，都数不准。

## 代码生成

| 文件 | 作用 |
|---|---|
| **`genschema.py`** | 用探针对全部 `.rdp` 键做实测，生成 `core/keymap.py`（键 → 类型 → 它驱动的 settings）。**升级 FreeRDP 后重跑** |
| **`probe.c`** | C 探针：链接本机 FreeRDP 头文件/库，解析 `.rdp` 后把全部 settings dump 出来 |
| **`probeutil.py`** | 共享模块：按需编译探针（`probe.c` 比二进制新就重编） |
| **`keys.txt`** | 从 `libfreerdp-client3` 里提取出来的 103 个 `.rdp` 键名 |

```bash
python3 tools/genschema.py       # 重新生成 core/keymap.py
```

## 依赖

探针需要 `gcc` 和 FreeRDP 的头文件：

```bash
pacman -S gcc freerdp     # Arch
```

`probe` 二进制是构建产物，可以随时删掉，`probeutil.py` 会自动重编。
