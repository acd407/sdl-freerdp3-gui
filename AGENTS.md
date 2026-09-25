# AGENTS.md

给在本仓库工作的开发者 / AI agent 的说明。用户文档见 [README.md](README.md)，
工具说明见 [tools/README.md](tools/README.md)。

---

## 1. 项目定位

FreeRDP 3 的图形化连接管理器：**`.rdp` 配置编辑器 + 启动器**。

它**不是** RDP 客户端——连接由 `sdl-freerdp3` 完成，本程序只负责生成/编辑 `.rdp`
文件、然后 fire-and-forget 地启动客户端。

**核心取向**：配置文件是唯一真身，本程序不引入私有格式。`.rdp` 文件可以手改、
可以拷给别人、`mstsc` / Remmina 也能读。

## 2. 环境事实（实测，不是推测）

| 组件 | 版本 | 备注 |
|---|---|---|
| FreeRDP | **3.31.1** | 系统包；`/usr/include/freerdp3` 的开发头文件**已安装**，探针因此能编译 |
| Python | 3.14 | |
| PyQt6 | 6.11.0 | **没有** `PyQt6.QtQuickControls2` 模块，所以只能用环境变量设样式，不能调 `QQuickStyle.setStyle()` |
| Qt | 6.11.2 | `qt6-declarative` 提供 QtQuick Controls（所以「`qt6-quickcontrols2` 未安装」是假象） |
| 样式 | Fusion | 通过 `QT_QUICK_CONTROLS_STYLE`；桌面风格，不依赖桌面环境 |
| 平台 | Wayland | `QT_QPA_PLATFORM=wayland;xcb` |

**当前规模**：103 个 `.rdp` 键中实测 75 个有效，schema 收录 51 个字段 / 7 个分组。

## 3. 目录结构

```
├── sdl-freerdp3-gui      启动脚本（设环境变量后 exec python3 app.py）
├── app.py                QML 桥：唯一的 Python ↔ QML 边界
├── core/                 运行时全部逻辑，不依赖 Qt
│   ├── rdpfile.py        .rdp 读写库（零依赖，可单独复用/发布）
│   ├── extraargs.py      gui_extra_args 里命令行 token 的替换
│   ├── keymap.py         【自动生成】键 → 类型 → 它驱动的 settings
│   ├── schema.py         UI 字段表（分组 / 标签 / 控件 / 默认值 / absent）
│   ├── profiles.py       配置的存取、软删除、GUI 状态
│   └── launch.py         启动 sdl-freerdp3
├── ui/
│   ├── Main.qml          List-Detail 主界面
│   └── FieldRow.qml      schema 驱动的单行表单组件
└── tools/                开发与验证，不参与运行时
```

**`core/` 里不允许 import Qt**（`app.py` 是唯一的 Qt 层）。这样核心逻辑可以脱离
GUI 单测，也是「UI 可以整体换掉」的前提。

## 4. 铁律：QML 里不允许出现 `.rdp` 语义

键名、类型、布尔反转、默认值、absent、序列化——**全部在 Python**。
QML 只负责渲染和收集输入。

违反这条会让 UI 无法替换，并且让逻辑无法单测。具体表现：

* QML 不得写死任何 `.rdp` 键名（`ui/FieldRow.qml` 只认 `fld.key` / `fld.widget`）
* QML 不得做类型转换或布尔反转（`invert` 在 `schema.ui_to_file` 里处理）
* QML 不得拼 `.rdp` 文本（`Bridge.previewText` 由 Python 生成）

同理，**`FieldRow.qml` 是按 `fld.widget` 分派的通用组件**——新增字段不需要改 QML。

## 5. 数据流

```
selectProfile(name)                       newDraft()
      │                                        │
      ▼                                        ▼
  _reload_values()                     _reload_values(use_defaults=True)
      │ 缺失键 → f.absent_value             │ 缺失键 → f.default
      ▼                                        ▼
   self._values : dict[str, Any]  ──►  QML 表单（fieldsChanged 时 sync()）
      │
      │ setField(key, value)  ← 用户编辑
      ▼
   _collect()  →  RdpFile  →  profiles.save()  →  <name>.rdp
      │                                  或
      └──► connectNow(): write_draft() + launch()
```

关键点：

* `_collect()` 是**唯一的序列化出口**，遵循 absent 约束（见 §7）
* `setField()` **默认不发 `fieldsChanged`**（否则正在编辑的输入框会被重置），
  只发 `previewChanged`。只有 `gui_security` ↔ `gui_extra_args` 联动时才发
* `saveAs` / `save` / `connectNow` 落盘后必须 `self._rdp = data`，
  否则紧接着的 `_reload_values()` 会从**旧内容**重算、清空表单（踩过）

## 6. 设计要点（都有实测依据）

| 决策 | 依据 |
|---|---|
| **单文件 `.rdp`**，GUI 元数据用 `gui_` 前缀键存在同一文件 | 实测 FreeRDP 静默接受未知键、应用设置时忽略、写回时保留（`write_custom_parameters`）。所以不需要 sidecar 文件 |
| **只用正向布尔键** | `disableclipboardredirection` / `disableprinterredirection` 是死键（settings 枚举里根本没有），实测无任何效果。反向键只保留 settings 枚举里确实存在的那批（`disable wallpaper` 等） |
| **「额外命令行参数」字段必需** | FreeRDP 的 103 个 `.rdp` 键里**没有任何安全层 / 证书键**。`/sec:tls` 和 `/cert:ignore` 只能走命令行 |
| **「安全方式」是虚拟字段** | 不写 `.rdp`，而是把 `/sec:...` 写进 `gui_extra_args`；替换时保留其余手写参数 |
| **GUI 不实现密码对话框** | `sdl-freerdp3` 自带凭据窗口（实测 `app-id=com.freerdp.client.sdl3`，标题 `Credentials required for <host>`），且它**不读 stdin**（`/from-stdin` 会因缺 TTY 报 `tcgetattr` 错） |
| **fire-and-forget 启动** | 不做输出解析和错误分类。GUI 常驻，客户端用 `start_new_session=True` 派生 |
| **文件保持最小** | FreeRDP 加载任何 `.rdp` 都会按 connection type 注入一整套图形/性能默认值，不写的项自然取默认 |

### 死键（不要加进 schema）

`core/keymap.py` 的 `DEAD_KEYS` 是在本机 FreeRDP 上实测无任何效果的键，
包括：`displayconnectionbar`、`pinconnectionbar`、`audioqualitymode`、
`superpan*`、`networkautodetect`/`bandwidthautodetect`（单独写无效，
要两者同时写才触发）、`disableclipboardredirection` 等。

`schema.py` 末尾有断言，会把死键和探针未确认的键挡在门外（`gui_` 前缀的除外）。

## 7. absent 约束（最重要的一条）

`_collect()` 只把「与 `Field.absent_value` 不同」的字段写进 `.rdp`，让文件保持最小。
这要求：

> **`absent` == FreeRDP 在该键缺失时的实际行为**，而不是「我们期望的默认值」。

两者不等时会出现隐蔽 bug：用户选中「默认值」→ 键被省略 → 行为变成 FreeRDP 的缺失行为。

**实测踩过的例子**：`audiomode` 的 UI 默认是 `0`（在本机播放），但 `.rdp` 里没有这个键时
`AudioPlayback` 和 `RemoteConsoleAudio` **都是 FALSE（音频全关）**。结果是选「在本机播放」
反而没有声音、远程 Windows 托盘显示「无音频设备」，而选「在服务器播放」却正常。

由 `tools/audit_defaults.py` 自动守住这条约束——逐个字段比较「省略该键」与
「写入默认值」两份 settings dump，0 个不符才算通过。

目前显式指定了 `absent` 的字段：

| 字段 | `default`（UI） | `absent`（键缺失时） |
|---|---|---|
| `audiomode` | 0 在本机播放 | **2 不播放** |
| `desktopwidth` | 1280 | 1024 |
| `desktopheight` | 800 | 768 |
| `autoreconnection enabled` | True | False |
| `bitmapcachepersistenable` | True | False |
| `dynamic resolution` | False | False（差异已确认无害，见审计里的 `BENIGN`） |

**移出 schema 的两个字段**（有跨字段副作用，实测）：
`desktop size id`（会篡改 `desktopwidth/height`）、
`redirectposdevices`（会改 `RedirectSerialPorts/ParallelPorts`）。

`_reload_values()` 也遵循这条约束：

* **载入已有文件** → 缺失键显示 `absent_value`（**真实行为**，而不是我们希望的值）
* **新建草稿**（`use_defaults=True`）→ 显示 `default`，这些值随后会被真正写进文件

`Bridge.__init__` 的初始状态也是草稿，所以它也传 `use_defaults=True`（踩过）。

## 8. `.rdp` 键 ≠ 命令行开关

用真实客户端的解析入口（`freerdp_client_settings_parse_command_line_ex`）实测：

| 写法 | DynamicRes | AuthLevel | Nla | Tls | **Rdp** |
|---|---|---|---|---|---|
| `.rdp` `dynamic resolution:i:1` | TRUE | – | – | – | – |
| 命令行 `+dynamic-resolution` | TRUE | – | – | – | – |
| `.rdp` `authentication level:i:0` | – | 0 | – | – | – |
| `.rdp` `enablecredsspsupport:i:0` | – | – | FALSE | TRUE | TRUE |
| **命令行 `/sec:tls`** | – | – | **FALSE** | TRUE | **FALSE** |

前几行说明 `.rdp` 键和命令行开关**是等效的**（走同一批 setting）。
只有 `/sec:tls` 额外关掉 `RdpSecurity`，而 **`.rdp` 里没有任何键能控制 `RdpSecurity`**。

另外记录一个顺序事实（`cmdline.c`）：**先加载 `.rdp`，再解析命令行**，
所以命令行总是后者优先。

## 9. QML / PyQt6 陷阱清单

这些都是实测崩溃或渲染失败后确认的，改动 `ui/` 前先读一遍。

### 会导致进程 abort

1. **`engine.warnings` 的参数是 `QList<QQmlError>`（Python list）**。
   写成 `lambda w: w.toString()` 会抛 `AttributeError`，被 PyQt6 升级成 `qFatal`。
   正确写法见 `tools/check_qml.py`。
2. **QML 自引用绑定**：`font.pixelSize: Math.round(font.pixelSize * 0.9)` → 绑定循环 → abort。
3. **`SpinBox.value` 是 int**：把字符串 `Number()` 出来的 `NaN` 塞进去触发断言。
   所以 `FieldRow.sync()` 按 `fld.widget` 分派，**不跨类型赋值**。
4. **析构顺序**：`bridge`（Python QObject）必须先于 QML 引擎销毁，见 `app.py:shutdown()`。
   顺序反了，QML 绑定会在 `bridge` 消失后求值，Qt 发 warning → PyQt6 升级成 `qFatal`。

> 排查这类问题时先看 `coredumpctl`，别反复触发崩溃（每次 dump 数 MB）。

### 会导致表单空白 / 错位

5. **独立组件当 delegate 时，`index` / `modelData` 必须显式声明为 `required property`**，
   否则 QML 不注入，取到 `undefined`。内联 `delegate: Frame {...}` 同理需要
   `required property var modelData`。
6. **不要直接绑 Python 的 `QVariantList<QVariantMap>`**。QML 对它的暴露方式是
   「map 的键作为 role」，嵌套 Repeater 里 `modelData` 不可靠 → 传 JSON 字符串再 `JSON.parse`。
7. **别把 `JSON.parse` 写在属性绑定里**。绑定会反复求值，每次产生**新数组**，
   导致内层 Repeater 无限重建 delegate、旧 delegate 销毁后绑定仍在求值 → 刷屏报错。
   只在 `Component.onCompleted` 里赋值一次。
8. **加就绪门闩**：`model: schemaReady ? schemaModel : []`。否则内层 Repeater 会在数据
   没就绪时先建一批 delegate，之后再重建 → 字段错位 + 空行。
9. **`TextField` / `SpinBox` 在用户输入时会打断属性绑定**，所以不能在声明里绑 `text:`，
   必须在 `sync()` 里显式同步，并由 `fieldsChanged` 触发。
10. **属性名/方法名不能以大写开头**（`property var F`、`function L()` 都会报错）。
11. **只给 `Layout.preferredWidth` 的控件会把自己的 preferred 当成最小宽度**，把整行卡住：
    行宽 = 190(标签) + 控件 preferred + 间距。结果是宽输入框能随窗口收缩、而含
    SpinBox(170) / ComboBox(280) 的行停在 490px 不缩 → 表单比面板宽 → 横向滚动条 +
    右侧被裁切，且不同分组的行宽还不一致（实测 760px 窗口）。修法：这类控件改成
    `Layout.fillWidth: true` + `Layout.maximumWidth: <原宽度>` + 一个较小的
    `Layout.minimumWidth`——宽窗口下不超过原宽度，窄窗口下可以收缩。见 `ui/FieldRow.qml`。
    连带的约束：标签列的 190px 无法再缩（给它更小的 `Layout.minimumWidth` 也无效），
    所以 `Main.qml` 右侧面板的 `SplitView.minimumWidth` 必须容得下最宽的一行（现为 420）。
12. **`ScrollView` 没有 `boundsBehavior`**（只在 `ListView`/`Flickable` 上有），直接写会
    报 `Cannot assign to non-existent property`。桌面应用不需要 Qt 默认的越界回弹，
    用 `Binding { target: sv.contentItem; property: "boundsBehavior"; value: Flickable.StopAtBounds }`
    设到内置 Flickable 上（用 Binding 而不是 `onCompleted`，contentItem 换掉时仍生效）。

## 10. 检查与代码生成

```bash
tools/check                  # 一键跑全部（约 5 秒）
tools/check --quick          # 跳过默认值审计

python3 tools/genschema.py   # 换 FreeRDP 版本后重新生成 core/keymap.py
```

| 脚本 | 作用 | 何时跑 |
|---|---|---|
| `tools/test_core.py` | 核心层单测（51 项），临时 XDG 目录 | 改 `core/` 或 `app.py` 后 |
| `tools/check_qml.py` | 无头加载 `Main.qml`，断言 **0 条 QML 警告** | 改 `ui/` 后 |
| `tools/audit_defaults.py` | 默认值审计（absent 约束） | 改 `core/schema.py` 后 |
| `tools/genschema.py` | 重新生成 `core/keymap.py` | 升级 FreeRDP 后 |

`tools/check_qml.py` 以「0 警告」为准而不是数控件个数：字段渲染失败的每种已知形态都会
产生警告，而 `findChildren` 穿不透 Repeater 的 delegate、`objectCreated` 也不覆盖组件内部
对象，都数不准。

## 11. 如何新增一个字段

**不需要改任何 QML**（表单由 schema 驱动）。步骤：

1. **确认这个键有效**。查 `core/keymap.py` 的 `KEY_SETTINGS`：值非空列表才算有效。
   若不在 `keys.txt` 里或 `KEY_SETTINGS` 为空，说明它是死键，不要加。
2. **在 `core/schema.py` 的 `FIELDS` 里加一条 `Field`**：
   `key`（必须是 `.rdp` 里的原名，含空格）、`group`、`label`（中文）、`widget`、
   `default`、必要时 `options`（枚举）、`invert`（反向键）、`help`。
3. **跑审计**：`python3 tools/audit_defaults.py`。
   如果它报这个字段，说明「键缺失时的行为」≠ `default`，需要显式给 `absent=`。
   把理由写进代码注释。
4. **跑全量检查**：`tools/check`。
5. 若字段有跨字段副作用（探针 diff 里出现不属于它的 setting），**不要加**，或先在
   审计里用 `BENIGN` 记录理由。

### widget 类型

`text` / `path`（TextField）、`int`（SpinBox）、`bool`（CheckBox）、`enum`（ComboBox，需 `options`）。

### 反向键

`.rdp` 里 `disable xxx` 这类键，设 `invert=True`，UI 显示正向语义
（勾选 = 启用该功能 = 文件里写 `0`）。

### 虚拟字段

不对应任何 `.rdp` 键、由 `Bridge` 特殊处理的字段（如 `gui_security`）：

1. 在 `schema.py` 定义 `Field`，并把 key 加进 `VIRTUAL_KEYS`
2. 在 `Bridge._reload_values()` 里派生它的值
3. 在 `Bridge.setField()` 里处理它的写入
4. `_collect()` 已自动跳过 `VIRTUAL_KEYS`

### 自定义键约定

本程序自己的元数据一律用 `gui_` 前缀（如 `gui_extra_args`、`gui_security`）。
FreeRDP 会忽略这些键，所以可以安全地存在同一个 `.rdp` 里。

## 12. 编码约定

* 注释和文档用中文，变量/函数名用英文
* `core/` 保持零第三方依赖（只用标准库）
* 纯逻辑优先：能被单测覆盖的不要放进 Qt 层
* 每次踩到坑，在 §9 或 §7 补一条，并说明**为什么**——这些约束都是实测出来的，
  不写清楚下次会再踩
* 不要在测试里触发崩溃：测试脚本先 `prctl(PR_SET_DUMPABLE, 0)` 禁止 core dump

## 13. 刻意不做的事

| 不做 | 原因 |
|---|---|
| 密码对话框 / keyring | `sdl-freerdp3` 自己弹窗，够用了。将来要接 keyring 的话，正确入口是 `FREERDP_ASKPASS`（FreeRDP 官方为 GUI 设计的接口） |
| 连接结果的错误分类 | 需要解析客户端 stderr，脆弱且随版本变化。实测过，不值得 |
| 侧车配置文件 | 自定义键可以直接存在 `.rdp` 里，实测安全 |
| 托盘图标 | 目标环境（niri）没有系统托盘 |
| 暗色模式自动跟随 | niri 没有 portal 通知 Qt 明暗，暂时不管 |
