# sdl-freerdp3-gui

FreeRDP 3 的图形化连接管理器：**`.rdp` 配置编辑器 + 启动器**。

配置的「真身」就是 `.rdp` 文件本身 —— 可以手改、可以拷给别人、Windows 的 mstsc
和 Remmina 也能直接读，不存在只有本程序认识的私有格式。

界面是 List-Detail：左边连接列表，右边分组表单，底部是 `.rdp` 预览和操作按钮。

---

## 安装

依赖：`python3`、`python-pyqt6`、`sdl-freerdp3`

```bash
# 放到一个不会丢的位置（不要留在 /tmp）
git clone <repo> ~/repository/freerdp-gui
# 或直接拷贝目录

# 可选：做个软链接方便调用
ln -s "$HOME/repository/freerdp-gui/sdl-freerdp3-gui" ~/.local/bin/
```

## 运行

```bash
./sdl-freerdp3-gui
```

## 主题

样式走系统 `QStyle`，所以**跟随你的 Qt 主题**（qt6ct / Kvantum / 桌面主题）：
配色方案、字体、控件样式都会生效。实测 `QApplication.style().objectName()`
是 `qt6ct-style` 且加载了 `libkvantum.so`。

想临时固定某个样式，用标准环境变量：

```bash
QT_STYLE_OVERRIDE=Fusion  ./sdl-freerdp3-gui    # 强制 Fusion
QT_STYLE_OVERRIDE=kvantum ./sdl-freerdp3-gui   # 强制 Kvantum
```

历史：早期版本是 QML / QtQuick 界面，而 QtQuick Controls **不经过 `QStyle`**，
Kvantum 对它是像素级无效的——这就是后来换成 QtWidgets 的原因。

## 使用

### 快速连接

列表最上面固定的 **「快速连接」** 就是一次性草稿：

* 填地址 → 点「连接」→ 直接连，**不落盘**
* 点「保存…」→ 命名后变成正式配置
* 切到别的配置再切回来，草稿内容还在

「新建」和它其实是同一个东西，只是预填值的区别。

### 保存配置

* 每个配置 = `profiles/` 下的一个 `.rdp` 文件，**文件里只写与默认不同的项**
* 「另存为…」复制一份并改名；「还原」丢弃改动、从磁盘重读
* 「✕」删除是**软删除**，移到 `trash/`，可以找回

### 安全方式

「认证」组最上面的 **「安全方式」** 下拉，实际是在编辑「额外命令行参数」里的
`/sec:` 参数：

| 选项 | 写入 |
|---|---|
| 自动协商 | *(不指定)* |
| 仅 TLS | `/sec:tls` |
| 仅 NLA | `/sec:nla` |
| NLA + 扩展安全 | `/sec:nla,ext` |
| 仅 RDP | `/sec:rdp` |

如果你的服务器要求纯 TLS（连不上、报安全层协商失败），选「仅 TLS」。

**为什么它是个下拉而不是普通复选框**：`.rdp` 文件里**没有任何键**能表达安全层
选择，只能通过命令行参数传。所以它写进的是自定义键 `gui_extra_args`，同时那个
输入框仍然可以手写（`/cert:ignore`、`+dynamic-resolution` 之类），两者双向联动，
互不覆盖。

### 密码

**本程序不弹密码框。** `sdl-freerdp3` 自己会弹（标题 `Credentials required for <主机>`），
所以密码不经过本程序，也不会落盘。

如果那个窗口被平铺合成器当成普通窗口处理，见下面的 niri 一节。

## 数据位置

```
~/.config/sdl-freerdp3-gui/
├── profiles/<名称>.rdp   每个连接一个文件
├── trash/                删除的配置（软删除，可找回）
└── config.json           窗口尺寸等界面状态
```

快速连接的草稿写在 `$XDG_RUNTIME_DIR/sdl-freerdp3-gui/quick.rdp`，不污染配置目录。

配置文件的属性是 `0600`（只有你自己可读）。

## niri 等平铺合成器

`sdl-freerdp3` 的**凭据对话框和主窗口共用同一个 `app-id`**
（`com.freerdp.client.sdl3`）。如果你已经给它配了 `tiled-state true`，
那个对话框会被强制平铺，很难用。加一条按标题排除的规则：

```kdl
window-rule {
    match app-id=r#"^com.freerdp.client.sdl3$"#
    exclude title=r#"^Credentials required"#
    open-maximized-to-edges true
    geometry-corner-radius 0
    tiled-state true
}
window-rule {
    match app-id=r#"^com.freerdp.client.sdl3$"# title=r#"^Credentials required"#
    open-floating true
    default-column-width { fixed 460; }
    default-window-height { fixed 220; }
}
```

本程序自己的窗口 `app-id` 是 **`sdl-freerdp3-gui`**。想让它浮动就自己加规则：

```kdl
window-rule {
    match app-id=r#"^sdl-freerdp3-gui$"#
    open-floating true
    default-column-width { fixed 1060; }
    default-window-height { fixed 740; }
}
```

## 开发

架构说明、设计约束、踩过的坑、检查与代码生成流程，见 **[AGENTS.md](AGENTS.md)**；
工具说明见 **[tools/README.md](tools/README.md)**。

跑一遍全部检查：

```bash
tools/check
```
