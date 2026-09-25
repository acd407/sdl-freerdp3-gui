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
| **`test_core.py`** | 核心层单元测试：`rdpfile` / `extraargs` / `profiles` / `schema` / `AppController` / `launch`。用临时 XDG 目录，不碰真实配置 |
| **`check_ui.py`** | 离屏构建**真实主窗口**，断言 **0 条 Qt 警告** + 字段数 / 控件类型 / 一次编辑往返 |
| **`audit_defaults.py`** | 逐个字段验证「省略该键」等价于「写入默认值」——见主 README 的「absent 约束」 |

为什么 `check_ui.py` 以「0 警告」为硬指标：控件造错类型、信号连到不存在的方法、
在重建列表时误触发选择……这些都会先抛 Qt 警告；**0 警告 + 显式字段数断言**能盖住
纯看控件个数漏掉的形态。

## 设计对照

| 文件 | 作用 |
|---|---|
| **`demo_sections.py`** | 分组 / 折叠控件的视觉对照 demo：同一份示例内容塞进 9 种实现，右上角可实时切 `QStyle`（Kvantum / Fusion / 桌面主题）。纯给人看的，不参与运行时 |

```bash
python3 tools/demo_sections.py
DEMO_SMOKE_TEST=600 QT_QPA_PLATFORM=offscreen python3 tools/demo_sections.py   # 冒烟
```

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
