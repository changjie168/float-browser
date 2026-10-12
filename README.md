# 浮窗浏览器（Float Browser · 原生 WebView2 版）

<img width="712" height="404" alt="QQ截图20261012091920" src="https://github.com/user-attachments/assets/c17f1280-11a4-45d2-aed4-a78ae0928ab1" />
<img width="712" height="404" alt="QQ截图20261012091914" src="https://github.com/user-attachments/assets/8466d9a6-a7a9-4fbd-9741-0126d3e80ffb" />


一个主打「轻便、不占内存」的无边框浏览器：窗口无边框、可随意缩小 / 拖到任意尺寸、
支持 📌 钉住使其始终显示在所有窗口最上层，**并且能正常打开任何网站**。

纯 Python 实现（pythonnet + WinForms），复用系统自带的 **WebView2（Edge）引擎**，
**不捆绑 Chromium**，成品 EXE 约 17 MB，内存占用远低于 Electron / Chrome。
欢迎 Issue / PR / Star ⭐。

## 为什么是「原生 WebView2 版」

初版用 `<iframe>` 把网页塞进窗口，但 Google / GitHub / YouTube 等站点会返回
`X-Frame-Options` / CSP `frame-ancestors`，**明确禁止被 iframe 内嵌**，表现就是
「网站拒绝连接 / 空白」。这是 iframe 的死穴，无法绕过。

本版改用 **WebView2 引擎顶层加载网页**（和你在普通浏览器地址栏输入网址一样），
`X-Frame-Options` 只对“被框进别人页面”生效，对顶层导航完全无效——因此任何网站都能开。

## 特性

- **无边框**：没有系统标题栏，整块区域都是浏览区。
- **轻量低内存**：基于 Python + pythonnet + 系统自带的 **WebView2（Edge）引擎**，
  **不捆绑 Chromium**，内存占用远低于 Electron / Chrome（成品 EXE 约 17 MB）。
- **随意缩放**：八向缩放手柄（上下左右 + 四个角），最小可缩到 240×160。
- **自由拖动**：按住顶部控制条空白处拖动窗口。
- **钉住置顶**：点 📌 切换「始终在最上层」，边看网页边做别的事。
- **应用图标**：EXE 与任务栏图标为「白底圆角卡片 + 蓝黄纸飞机 + 黑色描边」（`app.ico`，
  由 `iconbuild/convert.mjs` + `make_icon.py` 从 `iconbuild/fuchuang.svg` 生成，
  含 16–256 共 7 个尺寸）。
- **完整地址栏**：◀ 后退 / ▶ 前进 / ⟳ 刷新；地址栏输入网址或搜索词回车即开。
- **底部横向滑块**：窗口底栏有一条 3px 细滑块，页面横向溢出时才出现，可直接拖动 /
  点按空白处跳转，方便左右滑动；底栏最下方 4px 与左右下角仍然用于缩放窗口。
- **专注模式**：点 ⛶ 隐藏上方地址栏与全部图标，只留网页（窗口尺寸/位置不变），
  Esc / F11 退出。

## 运行方式

### 方式零：安装到电脑（换机分发推荐）

到本仓库的 **Releases** 页面下载 `FloatBrowser_Setup_x.y.z.exe`（Inno Setup 制作），
双击即可安装：

- 默认**按当前用户安装**，装在 `%LOCALAPPDATA%\Programs\FloatBrowser`，**不弹 UAC**
  （需要装给所有用户时，右键「以管理员身份运行」安装程序即可）。
- 自动创建开始菜单项；可选创建桌面快捷方式。
- **自动处理 WebView2 运行时依赖**：安装前检测，目标机缺失时自动联网安装
  （引导程序约 2 MB，已内嵌）。Win10/Win11 多数机器已自带，不会触发这一步。
- 卸载：开始菜单里的「卸载 浮窗浏览器」，或控制面板 / 设置 → 应用。
- 用户数据（缓存、WebView2 配置）存在 `%LOCALAPPDATA%\FloatBrowser`，
  **卸载后保留**，重装即可接着用。

重新生成安装包（需先安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)，装好后记下其安装目录）：

```bash
cd installer
python make_iss.py                     # 生成 setup.iss（必须 UTF-8 BOM）
# 再用 Inno Setup 自带的 ISCC.exe 编译：
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
```

> `make_iss.py` 会自动内嵌 WebView2 引导程序。若本机没有
> `MicrosoftEdgeWebview2Setup.exe`，到微软官网下载后放到 `installer/` 同级或按脚本内路径放置。
> 更多细节（包括工具链免安装到项目内的做法）见《换机开发指南.md》。

### 方式一：直接双击 EXE（推荐，免 Python）
已构建好的成品在 `build_exe/dist/FloatBrowser.exe`，双击即可运行。
若启动异常（例如目标机缺失 WebView2 运行时），可改双击 `FloatBrowser_debug.exe`
（控制台版），它会把错误打印出来便于排查。

### 方式二：源码运行
```bash
cd float-browser
pip install pywebview pyinstaller   # pywebview 仅用于定位 WebView2 程序集
python float_browser_native.py
```

### 环境要求
- Windows 10 / 11（已自带 WebView2 运行时；若缺失，到
  https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/ 安装即可）。
- Python 3.8+（仅源码运行需要）。

## 使用说明

- 顶部地址栏：输入网址（如 `github.com`）或搜索词，回车打开。
- 📌：钉住 / 取消钉住（置顶）；—：最小化；✕：关闭。
- ◀ ▶ ⟳：后退 / 前进 / 刷新。
- 底部 3px 细滑块：网页横向溢出时自动出现，按住拖动即可左右滑动页面；
  点轨道空白处直接跳转；底部最下方几像素与窗口左右下角仍是缩放热区。

## 打包为 EXE（免 Python 运行）

一键打包脚本 `build_exe.bat`（Windows）：

```bat
build_exe.bat
```

它用 PyInstaller 生成 `build_exe/dist/FloatBrowser.exe`（窗口版）与
`FloatBrowser_debug.exe`（控制台版，便于排错），**无需安装 Python** 即可运行。
打包前需准备托管 venv 并 `pip install pywebview pyinstaller`。

> 打包要点：PyInstaller 需把 WebView2 的两个托管 DLL（Core / WinForms）和
> 本机加载器 `WebView2Loader.dll`（x64）一同打进包；pythonnet 的 `clr`
> 以 `--hidden-import` 引入。运行目标机只需系统自带（或已安装）的 WebView2 运行时。

## 文件结构

```
float-browser/
├── float_browser_native.py   # 原生 WebView2 浮窗浏览器（主程序，已修复内嵌限制）
├── build_exe.bat             # 一键打包脚本（窗口版）
├── app.ico / app_1024.png    # 应用图标（闪电）与高清源图
├── make_icon.py              # SVG → ICO 转换脚本（依赖 resvg-js + Pillow）
├── build_exe/dist/
│   ├── FloatBrowser.exe      # 成品（窗口版，双击即用，也可直接拷走当绿色版）
│   └── FloatBrowser_debug.exe# 成品（控制台版，便于排错）
├── installer/
│   ├── make_iss.py           # 生成 Inno Setup 安装脚本（UTF-8 BOM）
│   ├── setup.iss             # 安装脚本（由上面脚本生成，勿手改）
│   └── _check_uninst.py      # 小工具：列出本机的浮窗浏览器卸载登记项
├── 换机开发指南.md           # 换一台电脑从零跑起来的完整手册（环境/打包/发布）
├── LICENSE                   # MIT
├── _tools/                   # 打包工具链（不随仓库分发，见换机开发指南）
│   ├── InnoSetup6/           # Inno Setup 6.7.3（免 UAC 装在项目内）
│   └── MicrosoftEdgeWebview2Setup.exe  # WebView2 引导程序（内嵌进安装包）
├── iconbuild/
│   ├── fuchuang.svg          # 应用图标源文件
│   └── convert.mjs           # SVG → 1024px PNG（resvg-js）
├── float_browser.py          # 旧版（iframe，受 X-Frame-Options 限制，仅作参考）
├── ui.html / start.html      # 旧版外壳与主页
└── preview.html              # 纯前端模拟器（仅看交互效果，不含真实浏览）
```

## 开源许可

[MIT License](LICENSE)，可自由使用、修改与分发。
