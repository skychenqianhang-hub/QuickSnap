# QuickSnap（快截）项目说明书

Windows 截图小工具：常驻托盘，按全局快捷键截图，结果自动进剪贴板，可选保存。

## 用户确认过的需求（2026-11-07）

- **一个快捷键**（默认 `Ctrl+Alt+A`，设置里可改）。按下后所有屏幕变暗：
  - 拖动 = 自选区域；
  - 单击 = 截鼠标下的那个窗口；点在空桌面上 = 截这块屏幕（阶段 2；阶段 1 先做「单击 = 整块屏幕」）。
  - 选好后有即时预览，可以拖边角调大小、整体移动（阶段 2）。
  - 工具条：复制（✓）/ 保存（默认文件夹）/ 另存为（自己选）/ 取消。任何一种完成方式都会复制到剪贴板。
- 多显示器：每块屏各自变暗，单击截的是点到的那块屏。
- 默认保存位置：优先用非系统盘（如 `D:\QuickSnap Screenshots`），没有才用 `图片\QuickSnap`。设置里可改；安装程序里让用户确认。
- 界面默认英文，可选简体中文、日语。
- 画图标注（框、箭头、画笔、文字、马赛克）放到以后。
- 命名：程序叫 QuickSnap（中文称呼「快截」），由 Claude 取名，用户未反对。

## 阶段

1. ✅（2026-11-07 验收）托盘常驻 + 全局快捷键 + 拖框截图 + 工具条 + 多屏 / 高分屏 + 打包 exe。
2. ✅（2026-11-07 验收）单击选窗口或整屏；选框可调整（拖边角、拖动整体、方向键微调）；放大镜（鼠标右下方，5 倍像素放大（用户觉得 8 倍太大）+ 绿色十字 + 坐标 / 色值，Ctrl+C 复制色值，方向键逐像素挪鼠标；放大镜信息框里写「方向键微调鼠标位置」，选好框后顶部提示「拖小方块调大小 · 方向键微调位置 · 回车或双击复制 · Esc 取消」；有放大镜后鼠标用普通箭头，不用十字（用户要求），只在框的边角 / 框内换成调大小 / 移动的箭头）。
3. ✅（2026-11-07 验收）设置窗口（托盘菜单「设置…」，或再次双击程序）：快捷键录入框（点一下再按组合键；单个字母 / Shift+字母不允许；被占用时提示并保留旧的）、保存位置（更改 / 打开，先试写确认能存）、开机自启（HKCU Run 项，尊重任务管理器里的禁用）、语言。改动立即生效，没有「保存」按钮。
4. 安装程序（Inno Setup，安装时选截图保存位置）+ 发布。
5. 画图标注（以后再说）。

## 技术要点

- Python 3.11 + PySide6 6.11.2，conda 环境 `quicksnap`（`C:\Users\Sky Chen\anaconda3\envs\quicksnap`）。
- 截屏：GDI BitBlt 一次抓整个虚拟桌面（物理像素），再按 EnumDisplayMonitors 的物理矩形切成每屏一张（`app/capture.py`）。
- 每块屏一个无边框置顶窗口（`app/overlay.py`），用 MonitorFromWindow 找到自己对应哪块屏；选框按物理像素存，画的时候才换算成 Qt 逻辑坐标，所以 125% / 150% 缩放下也准。
- 全局快捷键：RegisterHotKey + 一个不显示的窗口接收 WM_HOTKEY（`app/hotkey.py`）。不装键盘钩子。
- 开机自启：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `QuickSnap` 值，命令带 `--autostart`（启动时不弹气泡）；程序搬了位置会自动改指向（`app/autostart.py`）。
- 再次双击：第二个 QuickSnap.exe 用 FindWindow 找到隐藏窗口「QuickSnap hotkey sink」，发 WM_APP+1，让正在运行的那个打开设置窗口。
- 设置：`%APPDATA%\QuickSnap\config.json`（测试时可用环境变量 `QUICKSNAP_CONFIG_DIR` 换位置）。
- 界面文字：英文写在 `tr("...")` 里，`app/locales/zh.json`、`ja.json` 是译文；`python tools_dev/i18n_check.py` 查漏。

## 测试

- 自动测试：`python -m tests.test_core`
- 打包：`python -m PyInstaller --noconfirm --clean QuickSnap.spec` → `dist\QuickSnap\QuickSnap.exe`
- 打包后自检：`QuickSnap.exe --check 结果.txt`，末行 `ALL PASSED`。
- 真实快捷键测试：`python tools_dev/live_hotkey_test.py 输出目录`（会真的按 Ctrl+Alt+A 和 Esc）。
- 外观预览：`python tools_dev/preview_overlay.py 输出目录 [zh|ja|en]`。
- 这台电脑只有一块 1920×1080、100% 缩放的屏，多屏 / 混合缩放靠代码设计保证，尚未实机验证。

## 进度记录

- 2026-11-07 阶段 1 完成并验收。
- 2026-11-07 阶段 2 完成（窗口识别用 EnumWindows + DWM 可见边框，跳过隐藏 / 最小化 / 点击穿透 / 全透明 / 其他虚拟桌面的窗口；桌面本身 = 整屏）。用户验收时追加放大镜（参照微信截图），已做完，2026-11-07 和阶段 2 一起验收。
- 2026-11-07 阶段 3 完成并验收。自检发现临时快捷键接收器丢弃后监听没摘掉的问题，已修（HotkeyManager.close()）。
