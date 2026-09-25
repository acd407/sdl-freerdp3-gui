# research/ — 探索阶段的实测证据

**不参与运行时**，也不被任何脚本 import。这里只存放「AGENTS.md 里那些实测结论
从哪来」的原始材料，方便以后升级 FreeRDP 时对照、复现。

## 文件

| 文件 | 说明 |
|---|---|
| `probe.c` / `probe2.c` | C 探针的早期版本。现在的版本在 `tools/probe.c`（`probeutil.py` 按需重编） |
| `probe` / `probe2` | 上面两个探针编译出的二进制（构建产物，已 gitignore） |
| `keymap.json` / `keys.txt` | 探针跑出来的原始结果 / 从 `libfreerdp-client3` 提取的 103 个 `.rdp` 键名 |
| `scan_keys.py` | 当年用来生成 `keys.txt` / `keymap.json` 的脚本（现由 `tools/genschema.py` 取代） |
| `tree.json` | settings 枚举的树状 dump |
| `*.rdp` | 逐个键做 A/B 测试用的输入文件（`a`/`b*`/`c*`/… 按实验批次命名） |
| `w_before.txt` / `w_after.txt` / `shadow.log` | 探针输出的 settings dump（对照用） |
| `client.c` / `cmdline.c` / `file_3.31.0.c` / `file_master.c` | FreeRDP 3.31.0 与 master 的相关源码快照——「先加载 `.rdp` 再解析命令行」等结论即出自这里 |
| `sdl_*.c` | `sdl-freerdp3` 的源码快照（凭据窗口 `app-id`、标题等结论的来源） |

## 和 tools/ 的区别

`tools/` 是**会持续维护、要能跑**的检查与代码生成；`research/` 是**一次性**的
探索留痕，只读。要更新结论时先重跑 `tools/`，再把新的证据丢回这里。
