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
| PyQt6 | 6.11.0 | 只用 `QtWidgets` / `QtCore` / `QtGui` |
| Qt | 6.11.2 | |
| 样式 | 系统 QStyle | QtWidgets 走 `QStyle`，**能跟随 Kvantum / qt6ct / 桌面主题**。实测 `QApplication.style().objectName() == "qt6ct-style"` 且 `libkvantum.so` 被加载。QtQuick Controls 不经过 `QStyle`，Kvantum 对它是像素级无效的——这正是从 QML 换到 QtWidgets 的原因（见 §9） |
| 平台 | Wayland | `QT_QPA_PLATFORM=wayland;xcb` |

**当前规模**：103 个 `.rdp` 键中实测 75 个有效，schema 收录 51 个字段 / 7 个分组。

## 3. 目录结构

```
├── sdl-freerdp3-gui      启动脚本（设环境变量后 exec python3 app.py）
├── app.py                入口：QApplication + MainWindow
├── core/                 运行时全部逻辑，不依赖 Qt
│   ├── rdpfile.py        .rdp 读写库（零依赖，可单独复用/发布）
│   ├── extraargs.py      gui_extra_args 里命令行 token 的替换
│   ├── keymap.py         【自动生成】键 → 类型 → 它驱动的 settings
│   ├── schema.py         UI 字段表（分组 / 标签 / 控件 / 默认值 / absent）
│   ├── profiles.py       配置的存取、软删除、GUI 状态
│   └── launch.py         启动 sdl-freerdp3
├── ui/                   QtWidgets 界面
│   ├── controller.py     状态 + 业务操作，只发信号、不碰 widget
│   ├── fields.py         schema → 控件（FieldRow / CollapsibleSection）
│   └── mainwindow.py     List-Detail 主界面
└── tools/                开发与验证，不参与运行时
```

**`core/` 里不允许 import Qt**（`ui/` 是唯一的 Qt 层）。这样核心逻辑可以脱离
GUI 单测，也是「UI 可以整体换掉」的前提——事实上已经换过一次（QML → QtWidgets，
见 §9）。

## 4. 铁律：UI 层里不允许出现 `.rdp` 语义

键名、类型、布尔反转、默认值、absent、序列化——**全部在 `core/schema`**。
UI（`ui/`）只负责渲染和收集输入。

违反这条会让 UI 无法替换，并且让逻辑无法单测。具体表现：

* UI 不得写死任何 `.rdp` 键名（`ui/fields.py` 只认 `fld.key` / `fld.widget`）
* UI 不得做类型转换或布尔反转（`invert` 在 `schema.ui_to_file` 里处理）
* UI 不得拼 `.rdp` 文本（`AppController.previewText` 由 Python 生成）

同理，**`FieldRow` 是按 `fld.widget` 分派的通用控件**——新增字段不需要改 `ui/`。

## 5. 数据流

```
selectProfile(name)                       newDraft()
      │                                        │
      ▼                                        ▼
  _reload_values()                     _reload_values(use_defaults=True)
      │ 缺失键 → f.absent_value             │ 缺失键 → f.default
      ▼                                        ▼
   self._values : dict[str, Any]  ──►  控件（reloaded：全量；valueEdited：跳过有焦点的文本框）
      │
      │ setField(key, value)  ← 用户编辑
      ▼
   _collect()  →  RdpFile  →  profiles.save()  →  <name>.rdp
      │                                  或
      └──► connectNow(): write_draft() + launch()
```

关键点：

* `_collect()` 是**唯一的序列化出口**，遵循 absent 约束（见 §7）
* `_reload_values()` 发 `reloaded`（全量、强制覆盖）；`setField()` 发 `valueEdited`，
  UI 同步时**跳过仍有焦点的 `QLineEdit`**（见 `FieldRow.set_value`），否则正在编辑、
  尚未提交的输入框会被重置。QML 时期靠「setField 默认不发 fieldsChanged」达到同一目的
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

> 表中结论的**原始探针材料**（FreeRDP 源码快照、逐键 A/B 的 `.rdp`、settings dump）
> 曾经放在 `research/`，现已从工作区清掉——需要时在 git 历史里拿：
> `git show 7cf1972 --stat` 查看清单，`git show 7cf1972:research/cmdline.c > /tmp/cmdline.c`
> 取单个文件。要**复现**结论请跑 `tools/genschema.py` / `tools/audit_defaults.py`，
> 它们才是会持续维护的部分。

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

`AppController.__init__` 的初始状态也是草稿，所以它也传 `use_defaults=True`（踩过）。

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

另外记录一个顺序事实（FreeRDP `cmdline.c`，原始快照见 git 历史 commit `7cf1972`）：
**先加载 `.rdp`，再解析命令行**，所以命令行总是后者优先。

## 9. 为什么是 QtWidgets，而不是 QtQuick

这是实测结论，不是口味问题。

| | QtWidgets（现在） | QtQuick Controls（以前） |
|---|---|---|
| 经过 `QStyle`？ | ✅ | ❌ |
| Kvantum 主题 | ✅ 生效 | ❌ **像素级零影响** |
| qt6ct / 桌面主题 | ✅ QStyle + palette + 字体 | ⚠️ 只有 palette / 字体 / 图标主题，且只有 `Fusion` 样式跟随 |
| 控件样式选择 | 系统 `QStyle`（或 `QT_STYLE_OVERRIDE`） | `QT_QUICK_CONTROLS_STYLE`（QtQuick 专有） |

实测证据：用 `QApplication` 启动时 `QApplication.style().objectName() == "qt6ct-style"`
且 `/proc/self/maps` 里出现 `libkvantum.so`；换成 `QGuiApplication` + QML 后，
`libkvantum.so` **根本不会被加载**，`QT_STYLE_OVERRIDE=kvantum` 对界面像素无任何影响。

启动器因此**不设** `QT_QUICK_CONTROLS_STYLE`：那是 QtQuick 专有的，对 Widgets 无效。

### 界面层约定

1. `ui/` 不得出现 `.rdp` 语义（见 §4）
2. `AppController` 不 import 任何 widget，只发信号；窗口订阅信号刷新自己。
   所以业务逻辑能脱离控件单测（`tools/test_core.py` 的 `AppController` 一节）
3. `FieldRow.set_value(force=False)` 会**跳过仍有焦点的 `QLineEdit`**；只有
   `reloaded` 走 `force=True` 强制覆盖（例如「还原」时焦点仍在输入框里）
4. 造控件 / 设值 / 取值的类型分派只在 `ui/fields.py` 一处，按 `fld.widget` 来，
   不要跨类型赋值（`QSpinBox` 只能吃 int，`QComboBox` 用 `itemData` 存枚举值）
5. `QListWidget` 重建期间要置 `_rebuilding` 门闩，否则 `currentRowChanged` 会在
   填充过程中触发 `selectProfile`，把正在编辑的配置切走
6. 分组折叠用 `QGroupBox(checkable=True)`（勾选框 = 展开）。坑：Qt 在取消勾选时
   会**禁用全部子控件**，重新勾选时又无条件 `setEnabled(True)`。所以收起时必须把
   `body` 隐藏（现在就是这么做的），并且**不要**把「按字段禁用控件」的状态直接
   设在 QGroupBox 的子控件上——用户折叠一次就被 Qt 重置了

> 迁移前的 QML 踩坑清单（自引用绑定 → abort、Repeater delegate 要
> `required property`、`ScrollView` 没有 `boundsBehavior`、`Layout.preferredWidth`
> 会当最小宽度用……）已随 `ui/*.qml` 一起删除，需要时看 git 历史。

### 分组 / 折叠控件长什么样

拿不准某种折叠头好不好看时，跑 `python3 tools/demo_sections.py`：
它把同一份内容塞进九种实现（QToolButton、QGroupBox、QTreeWidget、QToolBox、
disclosure 风……）并排展示，右上角还能实时切 `QStyle` 和主题（Kvantum / Fusion）。

## 10. 检查与代码生成

```bash
tools/check                  # 一键跑全部（约 5 秒）
tools/check --quick          # 跳过默认值审计

python3 tools/genschema.py   # 换 FreeRDP 版本后重新生成 core/keymap.py
```

| 脚本 | 作用 | 何时跑 |
|---|---|---|
| `tools/test_core.py` | 核心层单测（51 项），临时 XDG 目录 | 改 `core/`、`ui/controller.py` 或 `app.py` 后 |
| `tools/check_ui.py` | 离屏构建**真实主窗口**，断言 **0 条 Qt 警告** + 字段数 / 控件类型 / 编辑往返 | 改 `ui/` 后 |
| `tools/audit_defaults.py` | 默认值审计（absent 约束） | 改 `core/schema.py` 后 |
| `tools/genschema.py` | 重新生成 `core/keymap.py` | 升级 FreeRDP 后 |

`tools/check_ui.py` 以「0 警告」为硬指标：字段渲染失败的形态都会先抛警告（控件造错类型、
信号连到不存在的方法……），**0 警告 + 显式字段数断言**比单看个数可靠。

## 11. 如何新增一个字段

**不需要改任何界面代码**（表单由 schema 驱动）。步骤：

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

`text` / `path`（QLineEdit）、`int`（QSpinBox）、`bool`（QCheckBox）、`enum`（QComboBox，需 `options`）。
枚举选项的 `value` 存在 `itemData` 里，不要从显示文本反推。

### 反向键

`.rdp` 里 `disable xxx` 这类键，设 `invert=True`，UI 显示正向语义
（勾选 = 启用该功能 = 文件里写 `0`）。

### 虚拟字段

不对应任何 `.rdp` 键、由 `AppController` 特殊处理的字段（如 `gui_security`）：

1. 在 `schema.py` 定义 `Field`，并把 key 加进 `VIRTUAL_KEYS`
2. 在 `AppController._reload_values()` 里派生它的值
3. 在 `AppController.setField()` 里处理它的写入
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
| 暗色模式自动跟随 | 得靠桌面 portal 通知 Qt。现在的做法是 QtWidgets 跟随系统 palette（qt6ct / Kvantum），想换深色就在那边换 color scheme；自动跟随仍然不管 |
