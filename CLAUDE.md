<!-- Working notes for Claude Code (the AI assistant that builds this project), in Chinese on purpose. User-facing docs: README.md / README_cn.md. -->

# QuickSnap：给 Claude Code 的开工须知

每次开工先读这份，再读 `PLAN.md`（需求、阶段、进度）。

- 用户不写代码。交流用中文、少术语。一次做一个阶段，做完停下讲清楚做了什么、怎么测；用户验收后才 git 提交。git 提交说明用英文。
- 验收对象是打包后的 `dist\QuickSnap\QuickSnap.exe`，每次交付都重新打包并跑 `--check` 自检。用户开着程序时打包会失败，请用户从托盘退出，不要强行关。
- Python：`C:\Users\Sky Chen\anaconda3\envs\quicksnap\python.exe`。conda / pip 的 exe 启动器坏了，用 `...\anaconda3\python.exe -m conda`、环境内 `python.exe -m pip`。
- 打包配方里必须手动带上 conda 的 `ffi*.dll`，否则 exe 里 ctypes 加载失败（已写在 QuickSnap.spec）。
- 界面文字一律 `tr("English")`，改完补 `app/locales/zh.json`、`ja.json`，跑 `python tools_dev/i18n_check.py`。
- 只用公开的 Windows 接口（RegisterHotKey、BitBlt 等），不装全局键盘 / 鼠标钩子。
- .bat 含中文要存 GBK + CRLF；目前 run.bat 只用英文。
- 交流一律中文（用户两次提醒过，长报告最容易滑回英文）。

## 远端仓库与发布

- GitHub：`https://github.com/skychenqianhang-hub/QuickSnap`（2026-11-07 起**公开**，MIT）。本地 `main` 跟踪 `origin/main`。gh 在 `C:\Program Files\GitHub CLI\gh.exe`（不在 PATH 里）。用户验收后提交，顺手 `git push`；推送前确认没有密钥、没有拍到用户真实屏幕的图片。
- README.md（英文，GitHub 首页）/ README_cn.md（中文）面向外部用户，改了功能要同步。截图只用 `python tools_dev/make_screenshots.py` 在假桌面上生成，**绝不用用户的真实屏幕**。
- 发布新版本：改 `app/version.py` → 补 CHANGELOG.md（英文）→ `python installer/build_installer.py` → 提交并 push → `git tag -a vX.Y.Z` + push tag → `gh release create vX.Y.Z installer/output/QuickSnap-Setup-X.Y.Z.exe --title "QuickSnap X.Y.Z" --notes-file <说明>`（发布说明上英文下中文）。

