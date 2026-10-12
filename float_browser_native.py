# -*- coding: utf-8 -*-
"""
浮窗浏览器（原生 WebView2 版）
================================
- 用系统自带的 Edge / WebView2 引擎直接顶层加载网页，绕过 X-Frame-Options / CSP 限制，
  因此 Google / GitHub / YouTube 等任何网站都能正常打开。
- 无边框 WinForms 外壳，自带地址栏、前进/后退/刷新、钉住置顶、全屏、最小化/关闭。
- 窗口四周有 1 像素浅灰描边；Windows 11 的 DWM 系统边框也会被一起接管成同色，
  避免系统强调色（紫色/蓝色）在窗口外圈露出来。
- 顶部控制条拖动移动，边缘/角落缩放。
- 全屏按钮进入「专注模式」：窗口位置与尺寸完全不变，只把上方地址栏 / 图标 / 描边
  全部隐藏，让网页占满整个窗口，屏幕上不出现任何控件；按 Esc 或 F11 退出。
- 图标全部用矢量线条自绘，不依赖 emoji 字体，避免显示不全 / 被裁剪。
- 网页里的超链接（target=_blank / window.open）不再弹出系统浏览器窗口，
  而是用**同款外壳**（无边框 + 同样的自绘工具栏 + 继承钉住状态）开新窗口；
  多个窗口共用一个 STA 线程与 WebView2 环境，最后一个窗口关闭才退出进程。
- 全站滚动条统一压成 3 像素细条（注入 CSS，纵向）；横向改为窗口底部一条更好的
  「App 级滑块」——只有页面横向溢出时才出现，可直接拖动 / 点按跳转，底部其余
  区域仍然负责窗口缩放，不牺牲拖动手感。
- 配色为灰白浅色系，苹果简约风。
- 不捆绑 Chromium，内存占用极低，契合“轻便、不占内存”。

运行（开发）：
    python float_browser_native.py
打包（生成 EXE）：
    pyinstaller --onefile --windowed --name FloatBrowser float_browser_native.py ...
"""

import os
import sys
import math
import json
import ctypes
import time
import tempfile
import threading
import traceback

# ---------------------------------------------------------------------------
# 崩溃日志 + 全局异常兜底（无论窗口版还是控制台版，任何异常都落盘并可弹窗）
# ---------------------------------------------------------------------------
def _log_dir():
    """日志文件目录。

    注意：打包后**不能**再写到 exe 所在目录 —— 程序装到 Program Files 后
    标准用户对该目录没有写权限，日志会全部丢失（整个写入被 try/except 静默吞掉，
    排查时极难定位）。所以冻结后统一写到 %LOCALAPPDATA%\\FloatBrowser，
    与 WebView2 的用户数据目录同级，任何安装位置都可写。
    """
    try:
        if getattr(sys, "frozen", False):
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "FloatBrowser")
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass
            return d
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


def _crash_log():
    return os.path.join(_log_dir(), "FloatBrowser_crash.log")


def _crash(msg):
    try:
        with open(_crash_log(), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _show_error(title, text):
    try:
        import clr  # noqa
        from System.Windows.Forms import MessageBox
        MessageBox.Show(str(text)[:3000], str(title), 0)
    except Exception:
        pass


def _global_exc(exc_type, exc_val, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
    _crash("=== UNHANDLED EXCEPTION @ %s ===\n%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), tb))
    _show_error("浮窗浏览器出错", tb)


sys.excepthook = _global_exc
try:
    threading.excepthook = lambda args: _global_exc(
        args.exc_type, args.exc_value, args.exc_traceback)
except Exception:
    pass


def _on_thread_exception(sender, e):
    """UI 线程上未被接住的异常（WinForms ThreadException）：只记日志，不弹框、不退出。"""
    try:
        info = getattr(e, "Exception", None)
        detail = ""
        try:
            if info is not None:
                detail = info.ToString()          # .NET 异常自带堆栈
        except Exception:
            detail = ""
        _crash("=== UI THREAD EXCEPTION @ %s ===\n%r\n%s"
               % (time.strftime("%Y-%m-%d %H:%M:%S"), info, detail))
    except Exception:
        pass


def _on_domain_exception(sender, e):
    """非 UI 线程的未处理异常（AppDomain 级）：同样落盘，尽力保住进程。"""
    try:
        _crash("=== APPDOMAIN UNHANDLED EXCEPTION @ %s ===\n%r"
               % (time.strftime("%Y-%m-%d %H:%M:%S"),
                  getattr(e, "ExceptionObject", None)))
    except Exception:
        pass


def _guard(handler):
    """给 WinForms 事件处理器套一层兜底。

    重要背景：在 pythonnet 里，事件处理器抛出的 Python 异常会冒泡到 .NET，
    被 WinForms 当成「未处理异常」→ 弹出系统级对话框
    「Microsoft .NET Framework：应用程序中发生了未处理的异常」（报错文本形如
    `'EventArgs' object has no attribute 'Y'`），用户只能点继续/退出，
    体验极差。凡是**回调型**事件（鼠标、绘制、浏览完成……）一律用本函数包一层：
    出错只写日志继续跑，绝不弹 .NET 错误框。
    """
    def wrapper(sender, e):
        try:
            return handler(sender, e)
        except Exception as ex:
            _crash("ERR: event handler %s failed: %r"
                   % (getattr(handler, "__name__", handler), ex))
            _crash(traceback.format_exc())
            return None
    try:
        wrapper.__name__ = getattr(handler, "__name__", "guarded")
    except Exception:
        pass
    return wrapper


# WinForms / WebView2 必须在 .NET 单线程单元（STA）中运行
import clr  # noqa: E402  (pythonnet 必须在最前加载)
from System.Threading import Thread, ThreadStart, ApartmentState  # noqa: E402

# 注意：在装配体加载前直接 `from System.Drawing import ...` 会 ModuleNotFoundError，
# 所以这里不写模块级 import，改为用 _ensure_drawing() 惰性加载 GDI+ 相关类型。
Array = Point = Pen = SolidBrush = SmoothingMode = None
_DRAWING_OK = False


def _ensure_drawing():
    """惰性加载 System.Drawing / Drawing2D 类型，重复调用无副作用。"""
    global Array, Point, Pen, SolidBrush, SmoothingMode, _DRAWING_OK
    if _DRAWING_OK:
        return
    try:
        clr.AddReference("System.Drawing")
    except Exception:
        pass
    from System import Array as _Array
    from System.Drawing import Point as _Point, Pen as _Pen, SolidBrush as _SolidBrush
    from System.Drawing.Drawing2D import SmoothingMode as _SmoothingMode
    Array, Point, Pen, SolidBrush = _Array, _Point, _Pen, _SolidBrush
    SmoothingMode = _SmoothingMode
    _DRAWING_OK = True


# ---------------------------------------------------------------------------
# 配色：灰白浅色系 · 苹果简约风（以 RGB 元组保存，颜色对象惰性构造）
# ---------------------------------------------------------------------------
BRAND_BG_RGB = (0xFA, 0xFA, 0xFC)      # 主背景：近白
HOVER_BG_RGB = (0xEC, 0xEC, 0xF0)      # 悬停底色：浅灰
ACTIVE_BG_RGB = (0x1D, 0x1D, 0x1F)     # 激活（钉住 / 全屏）：近黑胶囊
FG_RGB = (0x1D, 0x1D, 0x1F)            # 图标 / 文字前景：近黑
FG_ACTIVE_RGB = (0xFF, 0xFF, 0xFF)     # 激活态图标：白
BORDER_RGB = (0xD8, 0xD8, 0xDE)        # 1px 窗口描边：浅灰
HAIRLINE_RGB = (0xE6, 0xE6, 0xEB)      # 分隔细线：更浅的灰
INPUT_BG_RGB = (0xF1, 0xF1, 0xF5)      # 地址栏胶囊底色

# 底部横向滑块（3px 细条）：把 30% / 55% 透明度的灰预先混到近白背景上，
# 视觉上与网页里那条滚动条完全一致（WinForms 没有逐像素半透明，只能预混色）
THUMB_RGB = (0xC1, 0xC1, 0xC4)         # 滑块静止色 ≈ rgba(60,60,67,.30) 叠在 #FAFAFC
THUMB_HOVER_RGB = (0x92, 0x92, 0x96)   # 悬停 / 拖拽 ≈ rgba(60,60,67,.55)
TRACK_RGB = (0xED, 0xED, 0xF2)         # 极淡轨道

# 底部横向滑块尺寸（像素）
HBAR_H = 8            # 底部区域总高：上面 4px 放滑块，下面 4px 留给窗口缩放
HBAR_RESIZE = 4       # 底部保留给缩放的高度（指针落在这段 → 缩放而不是滑动）
HBAR_THUMB_H = 3      # 滑块可视高度
HBAR_THUMB_TOP = 0    # 滑块绘制的纵向起点
HBAR_INSET = 10       # 滑块左右内缩，避开窗口描边与下角缩放区
HBAR_THUMB_MIN = 26   # 滑块最小宽度（保证能抓住）


def _rgb(rgb):
    """由 RGB 元组构造 System.Drawing.Color（自动确保装配体已加载）。"""
    _ensure_drawing()
    from System.Drawing import Color
    return Color.FromArgb(rgb[0], rgb[1], rgb[2])


# ---------------------------------------------------------------------------
# Windows 11 DWM 窗口边框颜色接管
#   系统会用「强调色」在窗口最外圈画 1px 边框（用户看到的就是那圈紫色）。
#   属性 34 = DWMWA_BORDER_COLOR，可指定颜色或 DWMWA_COLOR_NONE 完全隐藏。
# ---------------------------------------------------------------------------
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF


def _dwm_set_border(hwnd, rgb=None, none=False):
    try:
        if none:
            val = ctypes.c_uint(DWMWA_COLOR_NONE)
        elif rgb is not None:
            val = ctypes.c_uint((rgb[2] << 16) | (rgb[1] << 8) | rgb[0])
        else:
            val = ctypes.c_uint(DWMWA_COLOR_DEFAULT)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), ctypes.c_uint(DWMWA_BORDER_COLOR),
            ctypes.byref(val), ctypes.sizeof(val))
        return True
    except Exception as ex:
        _crash("WARN: DwmSetWindowAttribute failed: %r" % ex)
        return False


# ---------------------------------------------------------------------------
# 圆角（苹果风胶囊）：给控件设置圆角 Region
# ---------------------------------------------------------------------------
def _round_region(ctrl, radius):
    try:
        from System.Drawing import Region
        from System.Drawing.Drawing2D import GraphicsPath
        w, h = ctrl.Width, ctrl.Height
        if w <= 2 or h <= 2:
            return
        r = min(radius, (h - 1) // 2, (w - 1) // 2)
        if r < 1:
            return
        d = r * 2
        p = GraphicsPath()
        p.AddArc(0, 0, d, d, 180.0, 90.0)
        p.AddArc(w - d - 1, 0, d, d, 270.0, 90.0)
        p.AddArc(w - d - 1, h - d - 1, d, d, 0.0, 90.0)
        p.AddArc(0, h - d - 1, d, d, 90.0, 90.0)
        p.CloseFigure()
        ctrl.Region = Region(p)
        p.Dispose()
    except Exception as ex:
        _crash("WARN: round region failed: %r" % ex)


# ---------------------------------------------------------------------------
# 定位应用图标（app.ico，由 make_icon.py 从 SVG 生成）
# ---------------------------------------------------------------------------
def _find_app_icon():
    """返回 app.ico 的绝对路径；冻结后从 sys._MEIPASS 取，否则从脚本同目录取。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(sys._MEIPASS, "app.ico"))
    cands.append(os.path.join(here, "app.ico"))
    for p in cands:
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# 定位 WebView2 托管 DLL（Core / WinForms）与本机加载器（WebView2Loader.dll）
# ---------------------------------------------------------------------------
def _find_webview_libs():
    """返回包含 WebView2 托管 DLL 的目录；冻结后从 sys._MEIPASS 取，否则从 pywebview 取。"""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(sys._MEIPASS)            # 单文件解包根目录
        candidates.append(os.path.dirname(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(here)
    try:
        import webview  # 仅用于定位 lib 路径，运行时不一定需要
        candidates.append(os.path.join(os.path.dirname(webview.__file__), "lib"))
    except Exception:
        pass
    for d in candidates:
        if d and os.path.exists(os.path.join(d, "Microsoft.Web.WebView2.Core.dll")):
            return d
    return None


def _add_native_paths(lib_dir):
    """把本机加载器 WebView2Loader.dll 所在目录加入 PATH。

    托管 DLL 通过 P/Invoke 找 WebView2Loader.dll，找不到内核就永远初始化不了
    （表现为输入地址毫无反应）。pywebview 也是这么做的。
    """
    if not lib_dir:
        return
    added = [lib_dir]
    for plat in ("win-x64", "win-x86", "win-arm64"):
        added.append(os.path.join(lib_dir, "runtimes", plat, "native"))
    for d in added:
        try:
            if os.path.isdir(d) and d.lower() not in os.environ.get("Path", "").lower():
                os.environ["Path"] = d + os.pathsep + os.environ.get("Path", "")
        except Exception:
            pass
    _crash("STEP: native search paths added = %r" % [d for d in added if os.path.isdir(d)])


def _user_data_folder():
    """WebView2 用户数据目录：固定位置，保证登录态 / 缓存能持久化。"""
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        p = os.path.join(base, "FloatBrowser", "WebView2Data")
    except Exception:
        p = os.path.join(tempfile.gettempdir(), "FloatBrowser_WebView2Data")
    try:
        os.makedirs(p, exist_ok=True)
    except Exception as ex:
        _crash("WARN: cannot create user data folder %r: %r" % (p, ex))
    return p


# ---------------------------------------------------------------------------
# 原生窗口消息常量（用于无边框拖动 / 缩放）
# ---------------------------------------------------------------------------
WM_NCLBUTTONDOWN = 0xA1
HT_CAPTION = 2
HT_LEFT, HT_RIGHT, HT_TOP, HT_TOPLEFT, HT_TOPRIGHT = 10, 11, 12, 13, 14
HT_BOTTOM, HT_BOTTOMLEFT, HT_BOTTOMRIGHT = 15, 16, 17

_user32 = ctypes.windll.user32

def _send_hit_test(hwnd, ht):
    """通过模拟标题栏/边框命中测试实现拖动 / 缩放。
    注意：pythonnet 3.0+ 不能 int(IntPtr)，传入前必须先 .ToInt64()。
    """
    ctypes.windll.user32.ReleaseCapture()
    ctypes.windll.user32.SendMessageW(
        ctypes.c_void_p(hwnd), ctypes.c_int(WM_NCLBUTTONDOWN),
        ctypes.c_int(ht), ctypes.c_int(0),
    )


# ---------------------------------------------------------------------------
# 矢量图标绘制（自绘，不依赖字体，保证任何环境下都完整显示）
# ---------------------------------------------------------------------------
# 图标相对缩放：前进 / 后退保持原尺寸（辨识度优先），其余统一缩小，整体更精致。
GLYPH_SCALE = {
    "back": 1.00,
    "fwd": 1.00,
    "reload": 0.90,
    "pin": 0.80,
    "min": 0.82,
    "full": 0.76,
    "restore": 0.76,
    "close": 0.84,
}
PEN_W = 1.55          # 描边线宽（缩放后会用 1/s 补偿，视觉线宽保持一致）


def _tri(g, brush, p1, p2, p3):
    """填充三角形（用于前进 / 后退 / 刷新箭头）。坐标可为浮点。"""
    pts = Array[Point](3)
    for i, p in enumerate((p1, p2, p3)):
        pts[i] = Point(int(round(p[0])), int(round(p[1])))
    g.FillPolygon(brush, pts)


def _arrow_head(g, brush, cx, cy, r, angle_deg, size=4.0, half=2.3):
    """在圆心 (cx,cy) 半径 r 的圆周 angle_deg 处，画一个沿顺时针切线的箭头。

    GDI 角度约定：0°= 右，90°= 下（屏幕坐标 y 向下），顺时针方向为角度增大方向。
    """
    a = math.radians(angle_deg)
    px = cx + r * math.cos(a)
    py = cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)     # 顺时针切线方向
    nx, ny = -ty, tx                       # 与之垂直的法线
    tip = (px + tx * size, py + ty * size)
    b1 = (px - tx * size * 0.5 + nx * half, py - ty * size * 0.5 + ny * half)
    b2 = (px - tx * size * 0.5 - nx * half, py - ty * size * 0.5 - ny * half)
    _tri(g, brush, tip, b1, b2)


def _draw_glyph(g, glyph, x, y, w, h, color):
    """在 (x, y, w, h) 区域内绘制指定图标。"""
    _ensure_drawing()
    g.SmoothingMode = SmoothingMode.AntiAlias
    cx = x + w // 2
    cy = y + h // 2
    s = GLYPH_SCALE.get(glyph, 1.0)
    if s != 1.0:
        # 以图标中心为基准缩放「形体」，描边线宽用 1/s 补偿，
        # 这样缩小的是尺寸而不是线条粗细 —— 图标看起来才够精致、不虚。
        g.TranslateTransform(float(cx), float(cy))
        g.ScaleTransform(float(s), float(s))
        g.TranslateTransform(float(-cx), float(-cy))
    pen = Pen(color, float(PEN_W / s))
    brush = SolidBrush(color)
    try:
        if glyph == "back":
            _tri(g, brush, (cx + 3, cy - 5), (cx + 3, cy + 5), (cx - 4, cy))
        elif glyph == "fwd":
            _tri(g, brush, (cx - 3, cy - 5), (cx - 3, cy + 5), (cx + 4, cy))
        elif glyph == "reload":
            # 重绘：开口圆环（缺口留在右上 60°）+ 明确的顺时针箭头。
            # 旧版是「12px 圆 + 一个伸到圈外的小三角」，看着就是个圆圈；现在
            # 圆更小、缺口更大、箭头更长，一眼能读出「刷新」。
            r = 6.4
            g.DrawArc(pen, cx - r, cy - r, r * 2, r * 2, 335, 295)
            _arrow_head(g, brush, cx, cy, r, 270, size=5.5, half=2.6)
        elif glyph == "pin":
            # 图钉：窄帽 + 收腰柱身 + 宽底盘 + 针尖（帽比底盘窄，免得看着像「T」）
            g.DrawLine(pen, cx - 3.2, cy - 6.0, cx + 3.2, cy - 6.0)
            g.DrawLine(pen, cx - 3.2, cy - 6.0, cx - 1.6, cy + 1.5)
            g.DrawLine(pen, cx + 3.2, cy - 6.0, cx + 1.6, cy + 1.5)
            g.DrawLine(pen, cx - 4.6, cy + 1.5, cx + 4.6, cy + 1.5)
            g.DrawLine(pen, cx, cy + 1.5, cx, cy + 6.5)
        elif glyph == "min":
            g.DrawLine(pen, cx - 6.0, cy + 4.0, cx + 6.0, cy + 4.0)
        elif glyph == "full":
            # 四角括号（进入专注模式）：缩短括号臂、留出明显的中间缺口，
            # 否则四段一拼接就成了一个「方框」。
            L, DX, DY = 5.0, 7.0, 6.5
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                x0 = cx + sx * DX
                y0 = cy + sy * DY
                g.DrawLine(pen, x0, y0, x0 - sx * L, y0)
                g.DrawLine(pen, x0, y0, x0, y0 - sy * L)
        elif glyph == "restore":
            # 四角内收（退出专注模式）：与 full 成对，臂朝外、尖端朝内
            L, DX, DY = 4.5, 5.5, 5.0
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                x0 = cx + sx * DX
                y0 = cy + sy * DY
                g.DrawLine(pen, x0 - sx * 2.5, y0, x0 + sx * L, y0)
                g.DrawLine(pen, x0, y0 - sy * 2.5, x0, y0 + sy * L)
        elif glyph == "close":
            g.DrawLine(pen, cx - 5, cy - 5, cx + 5, cy + 5)
            g.DrawLine(pen, cx - 5, cy + 5, cx + 5, cy - 5)
    finally:
        pen.Dispose()
        brush.Dispose()
        if s != 1.0:
            try:
                g.ResetTransform()
            except Exception:
                pass


def _fill_round(g, brush, x, y, w, h, r):
    """填充圆角矩形（.GraphicsPath；w/h 过小则退化成方块）。"""
    from System.Drawing.Drawing2D import GraphicsPath
    try:
        if w <= 0 or h <= 0:
            return
        rr = float(min(r, h / 2.0, w / 2.0))
        if rr < 0.5:
            g.FillRectangle(brush, float(x), float(y), float(w), float(h))
            return
        d = rr * 2.0
        p = GraphicsPath()
        try:
            p.AddArc(float(x), float(y), d, d, 180.0, 90.0)
            p.AddArc(float(x + w - d), float(y), d, d, 270.0, 90.0)
            p.AddArc(float(x + w - d), float(y + h - d), d, d, 0.0, 90.0)
            p.AddArc(float(x), float(y + h - d), d, d, 90.0, 90.0)
            p.CloseFigure()
            g.FillPath(brush, p)
        finally:
            p.Dispose()
    except Exception as ex:
        _crash("WARN: fill round rect failed: %r" % ex)


# ---------------------------------------------------------------------------
# 注入脚本（每个新文档都会执行）：
#   1) 全站滚动条统一压成 3 像素细条
#   2) 纯网页全屏模式下，网页里按 Esc / F11 也能退出
#      （网页有焦点时 WinForms 收不到按键，只能靠 JS 把消息回传给原生侧）
#   3) 把页面的横向滚动范围回传给外壳，用于绘制底部 3px 滑块
# ---------------------------------------------------------------------------
EXIT_MSG = "fb:exit-fullscreen"
SCROLL_MSG = "fb:scroll"

INJECT_JS = r"""
(function(){
  /* 1) 3 像素细滚动条。
     注意：本脚本在 document 起点执行，此时 document.head 与
     document.documentElement 都还是 null（实测确认），直接 appendChild 会抛异常、
     CSS 静默失效。因此必须等 documentElement 出现后再插入。 */
  var tries = 0;
  function styleIt(){
    try{
      if(!document.documentElement){
        if(tries++ < 200){ setTimeout(styleIt, 0); }
        return;
      }
      if(document.querySelector('style[data-fb-thin]')){ return; }
      var s = document.createElement('style');
      s.setAttribute('data-fb-thin','1');
      s.textContent =
        '::-webkit-scrollbar{width:3px;height:3px;background:transparent;}'+
        '::-webkit-scrollbar-track{background:transparent;}'+
        '::-webkit-scrollbar-thumb{background:rgba(60,60,67,.30);border-radius:3px;}'+
        '::-webkit-scrollbar-thumb:hover{background:rgba(60,60,67,.55);}'+
        '::-webkit-scrollbar-corner{background:transparent;}'+
        /* 文档级横向滚动条隐藏：改由外壳底部那条更好抓的滑块来控制，
           容器（代码块 / 表格等）自己的横向滚动条保持 3px 不变。 */
        'html::-webkit-scrollbar:horizontal,body::-webkit-scrollbar:horizontal{height:0px;}';
      (document.head||document.documentElement).appendChild(s);
    }catch(e){}
  }
  styleIt();

  /* 2) 纯网页全屏模式下，网页里按 Esc / F11 也退出：
        网页有焦点时 WinForms 收不到按键，只能让 JS 把消息回传给原生侧。 */
  try{
    window.addEventListener('keydown', function(ev){
      try{
        if(ev.key==='Escape' || ev.key==='F11'){
          window.chrome.webview.postMessage('fb:exit-fullscreen');
        }
      }catch(e){}
    }, true);
  }catch(e){}

  /* 3) 把「横向可滚动范围」回传给外壳：外壳据此画底部 3px 滑块。
        只在数值真正变化时才发消息，滚动时也不会刷屏。 */
  var FB_LAST = '?';
  function fbReport(){
    try{
      var se = document.scrollingElement || document.documentElement || document.body;
      if(!se){ return; }
      var cw = se.clientWidth || window.innerWidth || 0;
      var sw = se.scrollWidth || 0;
      try{ if(document.body && document.body.scrollWidth > sw){ sw = document.body.scrollWidth; } }catch(e){}
      var maxX = sw - cw;
      if(!(maxX > 1)){ sw = cw; maxX = 0; }
      var sl = (window.pageXOffset != null) ? window.pageXOffset
             : (se.scrollLeft || 0);
      if(sl < 0){ sl = 0; }
      if(sl > maxX){ sl = maxX; }
      var key = sw + '|' + cw + '|' + Math.round(sl);
      if(key === FB_LAST){ return; }
      FB_LAST = key;
      window.chrome.webview.postMessage(
        '{"t":"fb:scroll","sw":' + Math.round(sw) +
        ',"cw":' + Math.round(cw) + ',"sl":' + Math.round(sl) + '}');
    }catch(e){}
  }
  try{
    window.addEventListener('scroll', fbReport, true);   // 捕获阶段：页面内部滚动也能感知
    window.addEventListener('resize', fbReport);
    window.addEventListener('load', fbReport);
    window.addEventListener('DOMContentLoaded', fbReport);
    try{ new MutationObserver(fbReport).observe(document.documentElement,
          {childList:true, subtree:true}); }catch(e){}
    setInterval(fbReport, 500);      // 兜底：异步插入内容导致的布局变化
  }catch(e){}
  fbReport();
})();
"""


# ---------------------------------------------------------------------------
# 主页 HTML（苹果浅色风：搜索 + 常用站点）
# ---------------------------------------------------------------------------
HOME_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>
 html,body{height:100%}
 body{font-family:-apple-system,'Segoe UI',system-ui,'PingFang SC',sans-serif;
   background:#fafafc;color:#1d1d1f;display:flex;flex-direction:column;
   align-items:center;justify-content:center;margin:0;-webkit-font-smoothing:antialiased}
 h1{font-weight:600;margin:0 0 22px;font-size:19px;letter-spacing:.5px;color:#1d1d1f}
 form{width:62%;max-width:560px}
 input{width:100%;box-sizing:border-box;padding:11px 18px;border-radius:22px;
   border:1px solid #e6e6eb;font-size:15px;outline:none;background:#f1f1f5;color:#1d1d1f;
   transition:background .18s,border-color .18s,box-shadow .18s}
 input:focus{background:#fff;border-color:#d8d8de;box-shadow:0 1px 6px rgba(0,0,0,.06)}
 .links{margin-top:22px;display:flex;gap:9px;flex-wrap:wrap;justify-content:center;max-width:76%}
 a{color:#3c3c43;text-decoration:none;background:#f1f1f5;padding:8px 15px;border-radius:10px;
   font-size:13.5px;transition:background .18s,color .18s}
 a:hover{background:#e6e6eb;color:#1d1d1f}
 ::-webkit-scrollbar{width:3px;height:3px;background:transparent}
 ::-webkit-scrollbar-thumb{background:rgba(60,60,67,.30);border-radius:3px}
</style></head>
<body>
 <h1>浮窗浏览器</h1>
 <form onsubmit="location.href='https://www.bing.com/search?q='+encodeURIComponent(document.getElementById('q').value);return false">
   <input id="q" placeholder="搜索或输入网址" autofocus>
 </form>
 <div class="links">
  <a href="https://www.baidu.com/">百度</a>
  <a href="https://todesk.com/">ToDesk</a>
  <a href="https://streamingtool.douyin.com/">直播伴侣</a>
  <a href="https://www.xiaohongshu.com/">小红书</a>
 </div>
</body></html>"""


# ---------------------------------------------------------------------------
# 多窗口登记：网页里的 target=_blank / window.open 会开出「同款外壳」的新窗口，
# 所有窗口共用同一个 STA 线程与同一个 WebView2 环境（同一 UserDataFolder）。
# ---------------------------------------------------------------------------
_OPEN_FORMS = []


def _register_form(f):
    _OPEN_FORMS.append(f)


def _unregister_form(f):
    """窗口关闭后注销；最后一个窗口关掉才结束消息循环。"""
    try:
        _OPEN_FORMS.remove(f)
    except ValueError:
        pass
    if not _OPEN_FORMS:
        try:
            from System.Windows.Forms import Application
            Application.ExitThread()
        except Exception as ex:
            _crash("WARN: ExitThread failed: %r" % ex)


# ---------------------------------------------------------------------------
# 主程序（必须在 STA 线程中构建 WinForms UI）
# ---------------------------------------------------------------------------
def _build_and_run():
    try:
        _crash("STEP: start _build_and_run")
        lib_dir = _find_webview_libs()
        _crash("STEP: webview lib_dir = %r" % lib_dir)
        if not lib_dir:
            raise RuntimeError("找不到 WebView2 组件，请确认 pywebview 已安装或 DLL 已随包提供。")
        _add_native_paths(lib_dir)   # 让 P/Invoke 能找到 WebView2Loader.dll

        import clr
        clr.AddReference(os.path.join(lib_dir, "Microsoft.Web.WebView2.Core"))
        clr.AddReference(os.path.join(lib_dir, "Microsoft.Web.WebView2.WinForms"))
        try:
            clr.AddReference("System.Drawing")
        except Exception:
            pass
        _crash("STEP: AddReference WebView2 OK")

        from System.Drawing import (Color, Size, Point, Font, Rectangle, Icon, FontStyle)
        from System.Windows.Forms import (
            Application, Form, FormBorderStyle, FormWindowState, Screen,
            Padding, AutoScaleMode, BorderStyle, FormStartPosition, FlatStyle,
            TextBox, Button, Panel, Timer, ToolTip, Keys, Cursors, MessageBox,
            ControlStyles, UnhandledExceptionMode,
        )
        from Microsoft.Web.WebView2.WinForms import (WebView2,
                                                     CoreWebView2CreationProperties)
        _ensure_drawing()
        _crash("STEP: imports OK")

        # 配色（实例化 System.Drawing.Color）
        BRAND_BG = _rgb(BRAND_BG_RGB)
        HOVER_BG = _rgb(HOVER_BG_RGB)
        ACTIVE_BG = _rgb(ACTIVE_BG_RGB)
        FG_COLOR = _rgb(FG_RGB)
        FG_ACTIVE = _rgb(FG_ACTIVE_RGB)
        BORDER_COLOR = _rgb(BORDER_RGB)
        HAIRLINE_COLOR = _rgb(HAIRLINE_RGB)
        INPUT_BG = _rgb(INPUT_BG_RGB)

        WHITE = Color.FromArgb(0xFF, 0xFF, 0xFF)
        TITLE_H = 36          # 顶部控制条高度
        GRIP = 6              # 缩放手柄厚度
        BORDER = 1            # 窗口描边宽度（1 像素）
        MIN_W, MIN_H = 240, 160
        RIGHT_MARGIN = 8      # 右侧按钮组离窗口右边缘的距离
        BTN_W, BTN_H = 34, 30
        BTN_GAP = 40          # 右侧按钮之间的水平间距

        class GlyphButton(Button):
            """自绘图标按钮：矢量线条绘制，避免 emoji / 字体导致的裁剪与显示不全。"""

            paint_total = 0   # 诊断用：累计绘制次数

            def __init__(self, glyph, handler, tip=""):
                super().__init__()
                # 关键：标准 Button 的 UserPaint 默认为 false，走原生主题绘制，
                # 不会调用自绘逻辑；必须显式开启自绘，图标才会画出来。
                try:
                    self.SetStyle(
                        ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint
                        | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, True)
                except Exception as ex:
                    _crash("WARN: SetStyle failed: %r" % ex)
                self._glyph = glyph
                self._active = False
                self._hover = False
                self._paint_count = 0
                self.Text = ""
                self.Size = Size(BTN_W, BTN_H)
                self.FlatStyle = FlatStyle.Flat
                self.FlatAppearance.BorderSize = 0
                self.BackColor = BRAND_BG
                self.ForeColor = FG_COLOR
                self.TabStop = False
                self.Cursor = Cursors.Hand
                if tip:
                    try:
                        self._tip = ToolTip()
                        self._tip.SetToolTip(self, tip)
                    except Exception:
                        pass
                self.Click += handler
                # 注意：必须用 Paint 事件而不是覆写 OnPaint —— 本环境下 pythonnet
                # 对 protected 虚方法（OnPaint 等）的覆写不会派发，事件则稳定可用。
                self.Paint += _guard(self._on_paint)
                self.MouseEnter += _guard(self._on_enter)
                self.MouseLeave += _guard(self._on_leave)
                self.Resize += lambda s, e: _round_region(self, 8)

            def _on_enter(self, s, e):
                self._hover = True
                self.Invalidate()

            def _on_leave(self, s, e):
                self._hover = False
                self.Invalidate()

            def set_glyph(self, glyph):
                self._glyph = glyph
                self.Invalidate()

            def set_active(self, flag):
                flag = bool(flag)
                if flag != self._active:
                    self._active = flag
                    self.Invalidate()

            # 完全自绘（Paint 事件，不调用基类绘制），保证图标不被默认样式裁剪
            def _on_paint(self, s, e):
                self._paint_count += 1
                GlyphButton.paint_total += 1
                g = e.Graphics
                try:
                    if self._active:
                        bg = ACTIVE_BG
                    elif self._hover:
                        bg = HOVER_BG
                    else:
                        bg = self.BackColor
                    g.Clear(bg)
                    col = FG_ACTIVE if self._active else self.ForeColor
                    _draw_glyph(g, self._glyph, 0, 0,
                                self.ClientSize.Width, self.ClientSize.Height, col)
                except Exception as ex:
                    _crash("WARN: glyph paint failed (%s): %r" % (self._glyph, ex))

        # ------------------------------------------------------------------
        # 底部横向滑块（3px 细条）
        #   · 页面可横向滚动时才绘制；拖拽/点按直接驱动网页 window.scrollTo
        #   · 底部 4px 与左右下角仍然交给窗口缩放（跟原来的缩放手柄完全一致），
        #     页面没有横向溢出时整条都是缩放热区，不损失任何拖动体验
        # ------------------------------------------------------------------
        class HSliderBar(Panel):
            paint_total = 0   # 诊断用
            drag_total = 0

            def __init__(self, owner):
                super().__init__()
                self._owner = owner
                try:
                    self.SetStyle(
                        ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint
                        | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, True)
                except Exception as ex:
                    _crash("WARN: hslider SetStyle failed: %r" % ex)
                self.BackColor = BRAND_BG
                self.Height = HBAR_H
                self.TabStop = False
                self.Cursor = Cursors.SizeNS
                self._sw = self._cw = self._sl = 0
                self._hover = False
                self._drag = False
                self._drag_off = 0.0
                self.Paint += _guard(self._on_paint)
                self.MouseDown += _guard(self._on_down)
                self.MouseMove += _guard(self._on_move)
                self.MouseUp += _guard(self._on_up)
                self.MouseEnter += _guard(self._on_enter)
                self.MouseLeave += _guard(self._on_leave)

            # ---- 网页回传的横向滚动状态 ----
            def set_metrics(self, sw, cw, sl):
                try:
                    sw, cw, sl = int(sw), int(cw), int(sl)
                except Exception:
                    return
                if sw == self._sw and cw == self._cw and sl == self._sl:
                    return
                self._sw, self._cw, self._sl = sw, cw, sl
                self.Invalidate()

            def reset(self):
                self.set_metrics(0, 0, 0)

            def range(self):
                """可横向滚动的像素量（0 表示不需要滑块）。"""
                try:
                    return max(0, int(self._sw) - int(self._cw))
                except Exception:
                    return 0

            def scrollable(self):
                return self.range() > 1

            # ---- 几何 ----
            def _geo(self):
                """返回 (轨道x, 轨道宽, 滑块x, 滑块宽)。"""
                w = self.ClientSize.Width
                tx = HBAR_INSET
                tw = max(0, w - HBAR_INSET * 2)
                if tw <= 0:
                    return (0, 0, 0, 0)
                if not self.scrollable():
                    return (tx, tw, 0, 0)
                frac = min(1.0, float(self._cw) / float(max(1, self._sw)))
                thw = int(round(tw * frac))
                thw = max(HBAR_THUMB_MIN, min(thw, tw))
                free = tw - thw
                rng = self.range()
                ratio = 0.0 if rng <= 0 else max(0.0, min(1.0, float(self._sl) / float(rng)))
                thx = tx + int(round(free * ratio))
                return (tx, tw, thx, thw)

            def thumb_rect(self):
                tx, tw, thx, thw = self._geo()
                return (thx, HBAR_THUMB_TOP, thw, HBAR_THUMB_H)

            def _apply_ratio(self, ratio):
                rng = self.range()
                if rng <= 0:
                    return False
                x = int(round(max(0.0, min(1.0, ratio)) * rng))
                self._owner._hscroll_to(x)
                return True

            # ---- 交互：拖拽滑动 / 点按跳转 / 底部缩放 ----
            def _is_resize_zone(self, x, y):
                if y >= self.ClientSize.Height - HBAR_RESIZE:
                    return True
                return not self.scrollable()   # 无需滑动时整条都是缩放热区

            def _hit_test_for(self, x):
                w = max(1, self.ClientSize.Width)
                if x <= GRIP:
                    return HT_BOTTOMLEFT
                if x >= w - GRIP:
                    return HT_BOTTOMRIGHT
                return HT_BOTTOM

            def _on_down(self, s, e):
                if self._is_resize_zone(e.X, e.Y):
                    _send_hit_test(self._owner.Handle.ToInt64(), self._hit_test_for(e.X))
                    return
                tx, tw, thx, thw = self._geo()
                free = tw - thw
                HSliderBar.drag_total += 1
                try:
                    self.Capture = True
                except Exception:
                    pass
                self._drag = True
                if thw <= 0 or free <= 0:
                    return
                if e.X < thx or e.X > thx + thw:
                    # 点在轨道空白处 → 直接跳过去（滑块中心对齐指针）
                    self._drag_off = thw / 2.0
                    self._apply_ratio((e.X - self._drag_off - tx) / float(free))
                else:
                    # 按住滑块本体 → 保持相对位置
                    self._drag_off = e.X - thx

            def _on_move(self, s, e):
                if not self._drag:
                    self._sync_cursor(e.Y)
                    return
                tx, tw, thx, thw = self._geo()
                free = tw - thw
                if free <= 0:
                    return
                self._apply_ratio((e.X - self._drag_off - tx) / float(free))

            def _on_up(self, s, e):
                if not self._drag:
                    return
                self._drag = False
                try:
                    self.Capture = False
                except Exception:
                    pass
                self.Invalidate()

            def _sync_cursor(self, y=None):
                """按指针位置切换光标形状。y 缺省时自己按控件坐标算（MouseEnter 给的是
                普通 EventArgs，**没有 X/Y 字段** —— 直接读 e.Y 会抛 AttributeError）。"""
                try:
                    if y is None:
                        y = self.PointToClient(Cursor.Position).Y
                except Exception:
                    y = 0
                try:
                    if self._is_resize_zone(0, y):
                        self.Cursor = Cursors.SizeNS
                    else:
                        self.Cursor = Cursors.Hand
                except Exception:
                    pass

            def _on_enter(self, s, e):
                try:
                    self._hover = True
                    self._sync_cursor()          # 不要读 e.Y：MouseEnter 无坐标
                    self.Invalidate()
                except Exception as ex:
                    _crash("WARN: hslider enter failed: %r" % ex)

            def _on_leave(self, s, e):
                try:
                    self._hover = False
                    self.Invalidate()
                except Exception as ex:
                    _crash("WARN: hslider leave failed: %r" % ex)

            # ---- 绘制 ----
            def _on_paint(self, s, e):
                HSliderBar.paint_total += 1
                g = e.Graphics
                try:
                    g.SmoothingMode = SmoothingMode.AntiAlias
                    g.Clear(self.BackColor)
                    if not self.scrollable():
                        return
                    tx, tw, thx, thw = self._geo()
                    if thw <= 0:
                        return
                    track = SolidBrush(_rgb(TRACK_RGB))
                    hot = self._hover or self._drag
                    thumb = SolidBrush(_rgb(THUMB_HOVER_RGB if hot else THUMB_RGB))
                    try:
                        _fill_round(g, track, tx, HBAR_THUMB_TOP, tw, HBAR_THUMB_H, 1.5)
                        _fill_round(g, thumb, thx, HBAR_THUMB_TOP, thw, HBAR_THUMB_H, 1.5)
                    finally:
                        track.Dispose()
                        thumb.Dispose()
                except Exception as ex:
                    _crash("WARN: hslider paint failed: %r" % ex)

            # ---- 自检用：模拟把滑块拖到某个比例 ----
            def simulate_drag_ratio(self, ratio):
                return self._apply_ratio(ratio)

        class BrowserForm(Form):
            border_paint_total = 0   # 诊断用：描边绘制次数

            def __init__(self, initial_url=None, opener=None):
                """initial_url: 直接打开的地址（新窗口用）；opener: 父窗口（继承置顶与位置）。"""
                # 关键：必须先调用 .NET 基类构造，否则底层对象内部状态未初始化，
                # 后续设置 FormBorderStyle 等属性会抛 NullReferenceException。
                super().__init__()
                self.AutoScaleMode = AutoScaleMode.Dpi
                # 先强制创建窗口句柄（与 pywebview 相同的做法），
                # 之后设置 FormBorderStyle 才能安全地 RecreateHandle。
                _hwnd = self.Handle.ToInt64()
                self.FormBorderStyle = getattr(FormBorderStyle, "None")  # 无边框
                # 接管 Windows 11 的系统边框颜色：改成与自绘描边一致的浅灰，
                # 否则系统会用「强调色」（用户看到的紫色）画在最外圈。
                self._hwnd = _hwnd
                _dwm_set_border(_hwnd, rgb=BORDER_RGB)
                self.StartPosition = FormStartPosition.CenterScreen
                self.Size = Size(560, 440)
                self.MinimumSize = Size(MIN_W, MIN_H)
                self.BackColor = BRAND_BG
                self.TopMost = False
                self._initial_url = initial_url    # 新窗口：直接打开这个地址（None = 主页）
                self.KeyPreview = True
                self._immersive = False          # 纯网页全屏模式
                self._saved_bounds = None
                self._saved_state = None
                self._saved_topmost = False
                self._core_ready = False         # WebView2 内核是否已初始化完成
                self._pending_url = None         # 内核未就绪时暂存的待跳转地址
                self._init_ticks = 0
                self._init_failed = False
                _crash("STEP: form base init + frameless OK")

                # 窗口 / 任务栏图标（闪电）
                try:
                    ico = _find_app_icon()
                    if ico:
                        self.Icon = Icon(ico)
                except Exception as ex:
                    _crash("WARN: set icon failed: %r" % ex)

                # ---- WebView2 控件（占据标题栏以下全部区域）----
                self.webview = WebView2()
                self.webview.Margin = Padding(0)
                try:
                    self.webview.DefaultBackgroundColor = WHITE   # 浅色系：白底
                except Exception as ex:
                    _crash("WARN: set DefaultBackgroundColor failed: %r" % ex)
                # 关键：必须先设 CreationProperties（尤其 UserDataFolder），再显式调用
                # EnsureCoreWebView2Async 主动初始化内核。缺任一环 CoreWebView2 都会
                # 一直是 null —— 表现就是「输入地址毫无反应」。
                try:
                    props = CoreWebView2CreationProperties()
                    props.UserDataFolder = _user_data_folder()
                    props.AdditionalBrowserArguments = "--disable-features=ElasticOverscroll"
                    self.webview.CreationProperties = props
                    _crash("STEP: CreationProperties OK, UserDataFolder=%r"
                           % props.UserDataFolder)
                except Exception as ex:
                    _crash("WARN: set CreationProperties failed: %r" % ex)
                self.webview.CoreWebView2InitializationCompleted += _guard(self._on_core_ready)

                # ---- 顶部控制条 ----
                self.pnlTitle = Panel()
                self.pnlTitle.Height = TITLE_H
                self.pnlTitle.BackColor = BRAND_BG
                self.pnlTitle.MouseDown += _guard(
                    lambda s, e: _send_hit_test(self.Handle.ToInt64(), HT_CAPTION))

                # 左侧按钮：后退 / 前进 / 刷新
                self.btnBack = GlyphButton("back", self._go_back, "后退")
                self.btnFwd = GlyphButton("fwd", self._go_fwd, "前进")
                self.btnReload = GlyphButton("reload", self._reload, "刷新")
                self.btnBack.Left, self.btnFwd.Left, self.btnReload.Left = 8, 44, 80
                for b in (self.btnBack, self.btnFwd, self.btnReload):
                    b.Top = 3

                # 地址栏：外层胶囊面板 + 无边框输入框（苹果风）
                self.txtWrap = Panel()
                self.txtWrap.BackColor = INPUT_BG
                self.txtWrap.MouseDown += _guard(lambda s, e: self.txtUrl.Focus())
                self.txtUrl = TextBox()
                self.txtUrl.BorderStyle = getattr(BorderStyle, "None")  # 无边框输入框
                self.txtUrl.BackColor = INPUT_BG
                self.txtUrl.ForeColor = FG_COLOR
                self.txtUrl.Font = Font("Segoe UI", 10.5, FontStyle.Regular)
                self.txtUrl.AutoSize = False
                self.txtUrl.Height = 22
                self.txtUrl.Text = "主页"
                self.txtUrl.KeyDown += _guard(self._on_url_enter)
                self.txtWrap.Controls.Add(self.txtUrl)

                # 右侧按钮：全屏 / 钉住 / 最小化 / 关闭
                self.btnFull = GlyphButton("full", self._toggle_fullscreen, "专注模式：只留网页，隐藏工具栏（Esc 退出）")
                self.btnPin = GlyphButton("pin", self._toggle_pin, "钉住置顶")
                self.btnMin = GlyphButton("min", self._minimize, "最小化")
                self.btnClose = GlyphButton("close", self._close, "关闭")
                for b in (self.btnFull, self.btnPin, self.btnMin, self.btnClose):
                    b.Top = 3
                # 从右往左排布：关闭 / 最小化 / 钉住 / 全屏
                self._right_btns = [
                    (self.btnClose, RIGHT_MARGIN),
                    (self.btnMin, RIGHT_MARGIN + BTN_GAP),
                    (self.btnPin, RIGHT_MARGIN + BTN_GAP * 2),
                    (self.btnFull, RIGHT_MARGIN + BTN_GAP * 3),
                ]

                for c in (self.btnBack, self.btnFwd, self.btnReload, self.txtWrap,
                          self.btnFull, self.btnPin, self.btnMin, self.btnClose):
                    self.pnlTitle.Controls.Add(c)

                # ---- 底部横向滑块（3px 细条，方便左右滑动页面）----
                self.hbar = HSliderBar(self)

                # ---- 八向缩放手柄（透明，置于最上层）----
                self.grips = {}
                spec = {
                    "L": (HT_LEFT, GRIP, TITLE_H, Cursors.SizeWE),
                    "R": (HT_RIGHT, GRIP, TITLE_H, Cursors.SizeWE),
                    "B": (HT_BOTTOM, 0, GRIP, Cursors.SizeNS),
                    "TL": (HT_TOPLEFT, GRIP, TITLE_H, Cursors.SizeNWSE),
                    "TR": (HT_TOPRIGHT, GRIP, TITLE_H, Cursors.SizeNESW),
                    "BL": (HT_BOTTOMLEFT, GRIP, GRIP, Cursors.SizeNESW),
                    "BR": (HT_BOTTOMRIGHT, GRIP, GRIP, Cursors.SizeNWSE),
                }
                for name, (ht, w, h, cur) in spec.items():
                    g = Panel()
                    g.BackColor = Color.Transparent
                    g.Cursor = cur
                    g.Width, g.Height = w, h
                    g.MouseDown += _guard(
                        (lambda htw: (lambda s, e: _send_hit_test(self.Handle.ToInt64(), htw)))(ht))
                    self.grips[name] = g
                    self.Controls.Add(g)

                self.Controls.Add(self.webview)
                self.Controls.Add(self.hbar)
                self.Controls.Add(self.pnlTitle)
                for g in self.grips.values():
                    g.BringToFront()
                self.hbar.BringToFront()      # 底部滑块盖住缩放手柄，由它自己分发缩放/滑动
                self.pnlTitle.BringToFront()

                # 新窗口继承父窗口的外观状态：钉住（置顶）状态与窗口尺寸保持一致，
                # 并稍微错开位置，避免和父窗口完全重叠、看不出开了新窗口。
                if opener is not None:
                    try:
                        if opener.TopMost:
                            self.TopMost = True
                            self.btnPin.set_active(True)
                        try:
                            if (opener.Size.Width >= MIN_W and opener.Size.Height >= MIN_H):
                                self.Size = opener.Size     # 尺寸与窗口 1 一致
                        except Exception:
                            pass
                        self.StartPosition = FormStartPosition.Manual
                        self.Location = Point(opener.Left + 36, opener.Top + 36)
                    except Exception as ex:
                        _crash("WARN: inherit opener state failed: %r" % ex)

                self.Resize += _guard(lambda s, e: self._layout())
                self.Shown += _guard(lambda s, e: (self._layout(), self._start_core_init()))
                self.FormClosed += _guard(self._on_closed)
                self.KeyDown += _guard(self._on_key)
                # 浅灰 1 像素窗口描边 + 控制条下方分隔细线（事件方式，见 GlyphButton 处说明）
                self.Paint += _guard(self._on_paint_border)

                # 主动启动内核初始化，并挂上「初始化看门狗」（失败重试 + 超时提示）
                self._start_core_init()
                self._init_timer = Timer()
                self._init_timer.Interval = 1000
                self._init_timer.Tick += _guard(self._watch_init)
                self._init_timer.Start()

            # ---- 生命周期 ----
            def _on_closed(self, s, e):
                try:
                    self._init_timer.Stop()
                except Exception:
                    pass

            def _on_key(self, s, e):
                # 专注模式下：Esc / F11 恢复工具栏（窗口自身有焦点时生效；
                # 网页有焦点时由注入脚本 → _on_web_message 兜住）
                if self._immersive and e.KeyCode in (Keys.Escape, Keys.F11):
                    self._exit_immersive()

            # ---- 布局 ----
            def _layout(self):
                try:
                    w, h = self.ClientSize.Width, self.ClientSize.Height
                except Exception:
                    return
                if self._immersive:
                    # 纯网页模式：整个客户区都给网页，不留任何 UI
                    bx, by, tw, th, top = 0, 0, w, h, 0
                    bot = 0
                else:
                    bx, by = BORDER, BORDER
                    tw, th = w - 2 * BORDER, h - 2 * BORDER
                    top = TITLE_H
                    bot = HBAR_H          # 底部留出 8px 放 3px 横向滑块

                self.pnlTitle.Bounds = Rectangle(bx, by, tw, TITLE_H)
                self.webview.Bounds = Rectangle(bx, by + top, tw, max(0, th - top - bot))
                self.hbar.Bounds = Rectangle(bx, by + th - bot, tw, bot)

                # 地址栏胶囊：左侧 114 起，右侧避开按钮组
                wrap_left = 112
                wrap_right_reserve = RIGHT_MARGIN + BTN_GAP * 4 + 4
                wrap_w = max(70, tw - wrap_left - wrap_right_reserve)
                self.txtWrap.Bounds = Rectangle(bx + wrap_left, by + 4, wrap_w, 28)
                self.txtUrl.Bounds = Rectangle(10, 3, max(20, wrap_w - 20), 22)
                _round_region(self.txtWrap, 9)

                for b, off in self._right_btns:
                    b.Left = tw - off - b.Width

                # 缩放手柄
                g = self.grips
                g["L"].Bounds = Rectangle(bx, by + top, GRIP, th - top)
                g["R"].Bounds = Rectangle(bx + tw - GRIP, by + top, GRIP, th - top)
                g["B"].Bounds = Rectangle(bx, by + th - GRIP, tw, GRIP)
                g["TL"].Bounds = Rectangle(bx, by, GRIP, TITLE_H if top else GRIP)
                g["TR"].Bounds = Rectangle(bx + tw - GRIP, by, GRIP, TITLE_H if top else GRIP)
                g["BL"].Bounds = Rectangle(bx, by + th - GRIP, GRIP, GRIP)
                g["BR"].Bounds = Rectangle(bx + tw - GRIP, by + th - GRIP, GRIP, GRIP)

            # ---- 1 像素浅灰描边 + 控制条分隔细线（全屏模式不画）----
            def _on_paint_border(self, s, e):
                BrowserForm.border_paint_total += 1
                if self._immersive:
                    return
                w, h = self.ClientSize.Width, self.ClientSize.Height
                pen = Pen(BORDER_COLOR, 1)
                hair = Pen(HAIRLINE_COLOR, 1)
                try:
                    e.Graphics.DrawRectangle(pen, 0, 0, w - 1, h - 1)
                    e.Graphics.DrawLine(hair, BORDER, TITLE_H - 1, w - BORDER - 1, TITLE_H - 1)
                except Exception:
                    pass
                finally:
                    pen.Dispose()
                    hair.Dispose()

            # ---- 专注模式：只隐藏 UI，窗口尺寸 / 位置保持不变 ----
            def _toggle_fullscreen(self, s, e):
                if self._immersive:
                    self._exit_immersive()
                else:
                    self._enter_immersive()

            def _enter_immersive(self):
                """隐藏上方地址栏、图标、缩放手柄与描边，让网页占满窗口。

                注意：这里**不改变窗口尺寸与位置**（不铺满屏幕、不改 WindowState、
                不动 TopMost）—— 用户要的是「只显示网页内容」，不是把窗口放大到全屏。
                """
                try:
                    self._saved_state = self.WindowState
                    self._saved_bounds = self.Bounds
                    self._saved_topmost = self.TopMost
                except Exception:
                    self._saved_state, self._saved_bounds, self._saved_topmost = None, None, False
                self._immersive = True
                self.SuspendLayout()
                self.pnlTitle.Visible = False           # 隐藏上方地址栏与全部图标
                self.hbar.Visible = False               # 底部横向滑块也隐藏
                for g in self.grips.values():           # 缩放手柄也隐藏
                    g.Visible = False
                _dwm_set_border(self.Handle.ToInt64(), none=True)   # 连系统边框一起去掉
                self.btnFull.set_glyph("restore")
                self.btnFull.set_active(True)
                self.ResumeLayout()
                self._layout()
                self.Invalidate()
                _crash("STEP: immersive ON (chrome hidden, size kept = %s)" % self.Bounds)

            def _exit_immersive(self):
                self._immersive = False
                try:
                    # 专注模式本来就没改过尺寸，这里只是兜底恢复（状态 / 位置 / 钉住）
                    if self._saved_state is not None:
                        self.WindowState = self._saved_state
                    if self._saved_bounds is not None:
                        self.Bounds = self._saved_bounds
                    self.TopMost = bool(self._saved_topmost)   # 恢复原来的钉住状态
                except Exception:
                    pass
                self.pnlTitle.Visible = True
                self.pnlTitle.BringToFront()
                self.hbar.Visible = True
                self.hbar.BringToFront()
                for g in self.grips.values():
                    g.Visible = True
                    g.BringToFront()
                _dwm_set_border(self.Handle.ToInt64(), rgb=BORDER_RGB)
                self.btnFull.set_glyph("full")
                self.btnFull.set_active(False)
                self.btnPin.set_active(self.TopMost)
                self._layout()
                self.Invalidate()
                _crash("STEP: immersive OFF")

            # ---- WebView2 内核初始化 ----
            def _start_core_init(self):
                """显式启动内核初始化（可重入；已就绪则跳过）。

                这一步必须有：WinForms 版 WebView2 不会自己完成初始化，
                不调用 EnsureCoreWebView2Async 的话 CoreWebView2 永远是 null。
                """
                try:
                    if self.webview.CoreWebView2 is not None:
                        self._core_ready = True
                        return True
                    _ = self.webview.Handle.ToInt64()      # 强制创建控件句柄
                    self.webview.EnsureCoreWebView2Async(None)
                    _crash("STEP: EnsureCoreWebView2Async called")
                    return True
                except Exception as ex:
                    _crash("WARN: EnsureCoreWebView2Async failed: %r" % ex)
                    return False

            def _watch_init(self, s, e):
                """看门狗：内核迟迟未就绪 → 重试；超时 → 明确告知用户原因。"""
                try:
                    if self._core_ready or self._init_failed:
                        self._init_timer.Stop()
                        return
                    self._init_ticks += 1
                    if self._init_ticks in (3, 7):
                        self._start_core_init()
                    if self._init_ticks >= 20:
                        self._init_timer.Stop()
                        self.txtUrl.Text = "浏览器内核初始化失败"
                        try:
                            MessageBox.Show(
                                "浏览器内核（WebView2）初始化超时，无法打开网页。\n\n"
                                "请确认系统已安装 Microsoft Edge WebView2 运行时，"
                                "然后重新启动本程序。",
                                "浮窗浏览器", 0)
                        except Exception:
                            pass
                except Exception:
                    pass

            # ---- 导航 ----
            def _on_core_ready(self, sender, e):
                if not e.IsSuccess:
                    self._init_failed = True
                    try:
                        ex = getattr(e, "InitializationException", None)
                    except Exception:
                        ex = None
                    _crash("WARN: CoreWebView2 init NOT success: %r" % ex)
                    try:
                        MessageBox.Show(
                            "WebView2 初始化失败，无法打开网页。\n\n%r\n\n"
                            "请确认系统已安装 Microsoft Edge WebView2 运行时。" % (ex,),
                            "WebView2 初始化失败", 0)
                    except Exception:
                        pass
                    return
                try:
                    self.webview.CoreWebView2.Settings.IsStatusBarEnabled = False
                    self.webview.CoreWebView2.Settings.AreDefaultContextMenusEnabled = True
                except Exception as ex:
                    _crash("WARN: set settings failed: %r" % ex)
                self._core_ready = True

                # 注入脚本：3 像素细滚动条 + Esc/F11 退出纯网页模式
                try:
                    self.webview.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(INJECT_JS)
                    _crash("STEP: inject script registered (thin scrollbar + esc/f11)")
                except Exception as ex:
                    _crash("WARN: register inject script failed: %r" % ex)

                # 接收网页回传的消息（Esc / F11 → 退出纯网页模式）
                try:
                    self.webview.WebMessageReceived += _guard(self._on_web_message)
                    _crash("STEP: WebMessageReceived hooked")
                except Exception as ex:
                    _crash("WARN: hook WebMessageReceived failed: %r" % ex)

                # 拦截网页开新窗口（target=_blank / window.open）：默认会弹出系统
                # 浏览器窗口（有标题栏、地址栏，跟本程序完全不像），这里改成用
                # 我们自己的同款外壳窗口打开。
                try:
                    self.webview.CoreWebView2.NewWindowRequested += _guard(self._on_new_window)
                    _crash("STEP: NewWindowRequested hooked")
                except Exception as ex:
                    _crash("WARN: hook NewWindowRequested failed: %r" % ex)

                self.webview.NavigationCompleted += _guard(self._on_nav_done)
                try:
                    self.webview.CoreWebView2.NavigationStarting += _guard(self._on_nav_start)
                except Exception as ex:
                    _crash("WARN: hook NavigationStarting failed: %r" % ex)
                if self._initial_url:
                    # 新窗口：直接打开目标地址，不再显示主页
                    try:
                        self.webview.CoreWebView2.Navigate(self._initial_url)
                        self.txtUrl.Text = self._initial_url
                        _crash("INFO: new window navigate -> %s" % self._initial_url)
                    except Exception as ex:
                        _crash("WARN: new window navigate failed: %r" % ex)
                else:
                    try:
                        self.webview.NavigateToString(HOME_HTML)
                    except Exception as ex:
                        _crash("WARN: NavigateToString failed: %r" % ex)
                        try:
                            self.webview.CoreWebView2.Navigate("https://www.bing.com")
                        except Exception:
                            pass
                # 初始化期间用户已经输入过地址 → 现在补跳
                if self._pending_url:
                    pending, self._pending_url = self._pending_url, None
                    try:
                        self.webview.CoreWebView2.Navigate(pending)
                        _crash("INFO: deferred navigate executed: %s" % pending)
                    except Exception as ex:
                        _crash("WARN: deferred navigate failed: %r" % ex)

            def _on_web_message(self, sender, e):
                """接收注入脚本回传的消息：
                   · fb:exit-fullscreen  → 纯网页模式下按 Esc / F11 退出全屏
                   · {"t":"fb:scroll"}   → 页面横向滚动范围，用来画底部滑块
                """
                try:
                    msg = e.TryGetWebMessageAsString()
                except Exception as ex:
                    _crash("WARN: read web message failed: %r" % ex)
                    return
                if not msg:
                    return
                if msg == EXIT_MSG:
                    if self._immersive:
                        _crash("INFO: exit-fullscreen requested from page (esc/f11)")
                        self._exit_immersive()
                    return
                if msg[0] == "{":
                    try:
                        d = json.loads(msg)
                    except Exception:
                        return
                    if d.get("t") == SCROLL_MSG:
                        self.hbar.set_metrics(d.get("sw", 0), d.get("cw", 0),
                                              d.get("sl", 0))

            def _hscroll_to(self, x):
                """底栏滑块 → 驱动网页横向滚动."""
                if not self._core_ready:
                    return
                try:
                    self.webview.CoreWebView2.ExecuteScriptAsync(
                        "window.scrollTo(%d, window.scrollY);" % int(x))
                except Exception as ex:
                    _crash("WARN: hscroll_to failed: %r" % ex)

            def _on_new_window(self, sender, e):
                """网页要开新窗口（target=_blank / window.open）→ 用同款外壳窗口打开。

                WebView2 默认行为是在系统默认浏览器里开一个新窗口（带标题栏 / 地址栏，
                外观跟本程序完全不一致），所以这里必须接管。
                """
                try:
                    url = str(e.Uri)
                except Exception:
                    url = ""
                try:
                    user_initiated = bool(e.IsUserInitiated)
                except Exception:
                    user_initiated = None
                try:
                    e.Handled = True          # 阻止系统默认窗口 / 默认浏览器
                except Exception as ex:
                    _crash("WARN: set NewWindowRequested.Handled failed: %r" % ex)
                _crash("INFO: new-window request -> %r (userInitiated=%s)"
                       % (url, user_initiated))
                if not url:
                    return
                try:
                    _spawn_window(url, opener=self)
                except Exception as ex:
                    _crash("WARN: spawn window failed: %r -> fallback to same window" % ex)
                    try:
                        self._navigate(url)
                    except Exception:
                        pass

            def _on_nav_done(self, sender, e):
                try:
                    src = str(self.webview.Source)
                    if src and src != "about:blank":
                        self.txtUrl.Text = src
                except Exception:
                    pass

            def _on_nav_start(self, sender, e):
                # 开始新导航：先把滑块收起来，等新页面上报自己的滚动范围
                try:
                    self.hbar.reset()
                except Exception:
                    pass

            def _navigate(self, url):
                url = (url or "").strip()
                if not url:
                    return
                if not url.startswith("http://") and not url.startswith("https://"):
                    if "." in url and " " not in url:
                        url = "https://" + url
                    else:
                        import urllib.parse
                        url = "https://www.bing.com/search?q=" + urllib.parse.quote(url)
                core = None
                try:
                    core = self.webview.CoreWebView2
                except Exception:
                    core = None
                if core is None or not self._core_ready:
                    # 内核未就绪时先记下来，初始化完成后自动跳转
                    self._pending_url = url
                    _crash("INFO: navigate deferred (core not ready): %s" % url)
                    return
                try:
                    core.Navigate(url)
                    self.txtUrl.Text = url      # 立即回填，稍后由 _on_nav_done 校正为最终地址
                    _crash("INFO: navigate -> %s" % url)
                except Exception as ex:
                    _crash("WARN: navigate failed: %r" % ex)

            def _on_url_enter(self, sender, e):
                if e.KeyCode != Keys.Enter:
                    return
                e.SuppressKeyPress = True
                url = (self.txtUrl.Text or "").strip()
                if not url or "内核初始化" in url:
                    return
                if not self._core_ready:
                    # 内核还在初始化：暂存地址，并在地址栏给出可见反馈
                    self._navigate(url)
                    self.txtUrl.Text = "%s （内核初始化中，稍后自动打开…）" % url
                    return
                self._navigate(url)

            def _go_back(self, s, e):
                if not self._core_ready:
                    return  # 内核还没初始化完成，点了也没用（首启较慢时会遇到）
                try:
                    if self.webview.CanGoBack:
                        self.webview.GoBack()
                except Exception as ex:
                    _crash("WARN: go_back failed: %r" % ex)

            def _go_fwd(self, s, e):
                if not self._core_ready:
                    return
                try:
                    if self.webview.CanGoForward:
                        self.webview.GoForward()
                except Exception as ex:
                    _crash("WARN: go_fwd failed: %r" % ex)

            def _reload(self, s, e):
                if not self._core_ready:
                    return
                try:
                    self.webview.Reload()
                except Exception as ex:
                    _crash("WARN: reload failed: %r" % ex)

            def _toggle_pin(self, s, e):
                self.TopMost = not self.TopMost
                self.btnPin.set_active(self.TopMost)

            def _minimize(self, s, e):
                self.WindowState = FormWindowState.Minimized

            def _close(self, s, e):
                self.Close()

        # 同步执行一段 JS 并取回结果（自检专用：需要 message pump 让 Task 完成）
        def _eval_js(form, script, timeout=12):
            try:
                task = form.webview.CoreWebView2.ExecuteScriptAsync(script)
            except Exception as ex:
                return "ERR:%r" % (ex,)
            end = time.time() + timeout
            while time.time() < end:
                try:
                    if task.IsCompleted:
                        return str(task.Result)
                except Exception as ex:
                    return "ERR:%r" % (ex,)
                Application.DoEvents()
                time.sleep(0.05)
            return "TIMEOUT"

        # ---- 用「同款外壳」打开新窗口：无边框 + 同样的自绘工具栏 ----
        def _spawn_window(url, opener=None):
            frm = BrowserForm(initial_url=url, opener=opener)
            _register_form(frm)
            frm.FormClosed += lambda s, e: _unregister_form(frm)
            try:
                frm.Show()
            except Exception:
                _unregister_form(frm)
                raise
            _crash("STEP: new window spawned -> %s (open windows = %d)"
                   % (url, len(_OPEN_FORMS)))
            return frm

        def _self_test(f):
            """无界面自检（FB_SELFTEST=1 时启用）：
            用 PrintWindow / 屏幕截图真实抓取窗口像素，验证布局、1px 描边、自绘图标、
            内核初始化与真实导航、专注模式，以及「网页开新窗口」是否走同款外壳。
            """
            from System.Drawing import Bitmap, Graphics as _G
            from System.Drawing.Imaging import ImageFormat

            _pw = ctypes.windll.user32.PrintWindow
            _pw.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
            _pw.restype = ctypes.c_int

            def shot(tag):
                """PrintWindow(PW_RENDERFULLCONTENT=2) 抓取窗口内容（原生控件走 WM_PRINT，
                自绘按钮不会出现在其中，因此另配 shot_screen）。"""
                try:
                    w = max(1, f.ClientSize.Width)
                    h = max(1, f.ClientSize.Height)
                    bmp = Bitmap(w, h)
                    g = _G.FromImage(bmp)
                    hdc = g.GetHdc()
                    try:
                        ok = _pw(f.Handle.ToInt64(), hdc.ToInt64(), 2)
                    finally:
                        g.ReleaseHdc(hdc)
                    out = os.path.join(_log_dir(), "selftest_%s.png" % tag)
                    bmp.Save(out, ImageFormat.Png)
                    _crash("SELFTEST: shot %s -> %s (%dx%d, PrintWindow=%s)"
                           % (tag, out, w, h, ok))
                except Exception as ex:
                    _crash("SELFTEST: shot %s FAILED: %r" % (tag, ex))

            def shot_screen(tag):
                """屏幕级截图：能捕获自绘按钮的真实外观（需有可见桌面）。"""
                try:
                    r = f.Bounds
                    bmp = Bitmap(max(1, r.Width), max(1, r.Height))
                    g = _G.FromImage(bmp)
                    g.CopyFromScreen(r.X, r.Y, 0, 0, Size(r.Width, r.Height))
                    out = os.path.join(_log_dir(), "selftest_screen_%s.png" % tag)
                    bmp.Save(out, ImageFormat.Png)
                    _crash("SELFTEST: screen shot %s -> %s (%dx%d)"
                           % (tag, out, r.Width, r.Height))
                except Exception as ex:
                    _crash("SELFTEST: screen shot %s FAILED: %r" % (tag, ex))

            def dump_paint(tag):
                _crash("SELFTEST: paint@%s btnClose=%d btnFull=%d total=%d border=%d"
                       % (tag, f.btnClose._paint_count, f.btnFull._paint_count,
                          GlyphButton.paint_total, BrowserForm.border_paint_total))

            try:
                f.Show()
                Application.DoEvents()
                f._layout()
                Application.DoEvents()
                f.Refresh()
                Application.DoEvents()
                _crash("SELFTEST: normal bounds=%s client=%s" % (f.Bounds, f.ClientSize))
                shot("normal")
                shot_screen("normal")
                dump_paint("normal")

                # 等 WebView2 内核初始化（首次启动可能较慢），并验证真实导航
                for _ in range(200):
                    if f._core_ready:
                        break
                    Application.DoEvents()
                    time.sleep(0.1)
                _crash("SELFTEST: core_ready=%s source=%r"
                       % (f._core_ready, str(f.webview.Source)))
                if f._core_ready:
                    try:
                        f._navigate("https://www.bing.com")
                        for _ in range(150):
                            Application.DoEvents()
                            time.sleep(0.1)
                            if "bing.com" in str(f.webview.Source):
                                break
                        _crash("SELFTEST: after navigate source=%r addr=%r"
                               % (str(f.webview.Source), f.txtUrl.Text))
                        shot("navigated")
                        shot_screen("navigated")
                    except Exception as ex:
                        _crash("SELFTEST: navigate test FAILED: %r" % ex)

                # 专注模式：只隐藏 UI，窗口位置 / 尺寸必须保持不变
                before = f.Bounds
                f._enter_immersive()
                Application.DoEvents()
                f._layout()
                Application.DoEvents()
                f.Refresh()
                Application.DoEvents()
                after = f.Bounds
                same_size = (before.X == after.X and before.Y == after.Y
                             and before.Width == after.Width and before.Height == after.Height)
                _crash("SELFTEST: immersive bounds=%s (was %s) sizeKept=%s "
                       "panelVisible=%s gripsVisible=%s webviewBounds=%s"
                       % (after, before, same_size, f.pnlTitle.Visible,
                          any(g.Visible for g in f.grips.values()), f.webview.Bounds))
                shot("full_page")
                shot_screen("full_page")
                dump_paint("full_page")

                # 模拟「网页里按 Esc」：走 WebMessageReceived 通道，验证退出路径真的通
                class _FakeMsg(object):
                    def TryGetWebMessageAsString(self):
                        return EXIT_MSG

                f._on_web_message(None, _FakeMsg())
                Application.DoEvents()
                _crash("SELFTEST: after esc-message immersive=%s panelVisible=%s"
                       % (f._immersive, f.pnlTitle.Visible))
                if f._immersive:
                    f._exit_immersive()
                Application.DoEvents()
                _crash("SELFTEST: restored bounds=%s panelVisible=%s"
                       % (f.Bounds, f.pnlTitle.Visible))
                shot("restored")
                dump_paint("restored")

                # ---- 底部横向滑块：宽页面必须出现滑块，拖动必须真的滚动页面 ----
                def scan_thumb(tag):
                    """像素实证：把控件自身渲染出来逐行扫描（DrawToBitmap 会触发
                    Paint 事件，能捕到自绘的 3px 滑块；屏幕截图在无桌面环境不可靠）。"""
                    try:
                        w = max(1, f.hbar.ClientSize.Width)
                        h = max(1, f.hbar.ClientSize.Height)
                        bmp = Bitmap(w, h)
                        f.hbar.DrawToBitmap(bmp, Rectangle(0, 0, w, h))
                        for y in range(h):
                            xs = []
                            for x in range(w):
                                c = bmp.GetPixel(x, y)
                                if (c.R + c.G + c.B) < 650:      # 深于淡轨道/背景
                                    xs.append(x)
                            if xs:
                                _crash("SELFTEST[%s]: y=%d thumbPixels=%d x=[%d..%d]"
                                       % (tag, y, len(xs), min(xs), max(xs)))
                            else:
                                _crash("SELFTEST[%s]: y=%d no thumb pixels (轨道/背景)"
                                       % (tag, y))
                        # 顺手导出一张放大 8 倍的预览图，方便肉眼确认「3px 细条」观感
                        try:
                            from System.Drawing.Drawing2D import (InterpolationMode,
                                                                  PixelOffsetMode)
                            sc = 8
                            out = Bitmap(w * sc, h * sc)
                            og = _G.FromImage(out)
                            og.InterpolationMode = InterpolationMode.NearestNeighbor
                            og.PixelOffsetMode = PixelOffsetMode.Half
                            og.DrawImage(bmp, Rectangle(0, 0, w * sc, h * sc))
                            p = os.path.join(_log_dir(),
                                             "preview_bottom_slider_%s.png" % tag)
                            out.Save(p, ImageFormat.Png)
                            _crash("SELFTEST[%s]: zoom preview -> %s" % (tag, p))
                        except Exception as ex2:
                            _crash("SELFTEST[%s]: zoom preview FAILED: %r" % (tag, ex2))
                    except Exception as ex:
                        _crash("SELFTEST[%s]: thumb scan FAILED: %r" % (tag, ex))

                try:
                    f.Size = Size(520, 360)
                    Application.DoEvents()

                    def _wait_range(timeout=12):
                        end = time.time() + timeout
                        while time.time() < end:
                            Application.DoEvents()
                            if f.hbar.range() > 1:
                                return True
                            time.sleep(0.05)
                        return False

                    # 制造横向溢出：优先用「真实网页 + 300% 缩放」（最接近用户场景，
                    # 截图也是真实渲染）；不成立时兜底构造一张超宽测试页。
                    try:
                        f.webview.ZoomFactor = 3.0
                    except Exception as ex:
                        _crash("WARN: set ZoomFactor failed: %r" % ex)
                    got = _wait_range(10)
                    src_used = "zoom300"
                    if not got:
                        _crash("SELFTEST: zoom300 未产生横向溢出，改用超宽测试页")
                        f.webview.NavigateToString(
                            "<body style='margin:0;background:#fff'>"
                            "<div style='width:3000px;height:80px;"
                            "background:linear-gradient(90deg,#eeeeee,#555555)'></div>"
                            "<div style='height:120px'></div></body>")
                        got = _wait_range(12)
                        src_used = "wide-test-page"
                    _crash("SELFTEST: hslider sw=%d cw=%d sl=%d range=%d -> visible=%s (%s)"
                           % (f.hbar._sw, f.hbar._cw, f.hbar._sl, f.hbar.range(),
                              got, src_used))
                    # 网页自身的文档级横向滚动条应已被隐藏，避免和我们的滑块重复
                    probe = _eval_js(
                        f, "String((window.innerHeight||0)-(document.documentElement.clientHeight||0))", 8)
                    _crash("SELFTEST: native document h-scrollbar height = %r px (0 = 已隐藏)" % probe)
                    _crash("SELFTEST: hbar bounds=%s webview bounds=%s client=%s paints=%d"
                           % (f.hbar.Bounds, f.webview.Bounds, f.ClientSize,
                              HSliderBar.paint_total))

                    before_rect = f.hbar.thumb_rect()
                    before_x = _eval_js(f, "String(Math.round(window.scrollX||0))", 8)
                    shot("hslider_left")
                    scan_thumb("hslider_left")

                    # 把滑块拖到最右端 → 页面 scrollX 必须变大
                    moved = f.hbar.simulate_drag_ratio(1.0)
                    after_x = before_x
                    deadline = time.time() + 12
                    while time.time() < deadline:
                        Application.DoEvents()
                        after_x = _eval_js(f, "String(Math.round(window.scrollX||0))", 3)
                        if after_x.isdigit() and int(after_x) > 0:
                            break
                        time.sleep(0.1)
                    after_rect = f.hbar.thumb_rect()
                    shot("hslider_right")
                    scan_thumb("hslider_right")
                    _crash("SELFTEST: drag-to-right moved=%s scrollX %r -> %r "
                           "thumbRect %s -> %s"
                           % (moved, before_x, after_x, before_rect, after_rect))

                    # 拖回最左端
                    f.hbar.simulate_drag_ratio(0.0)
                    deadline = time.time() + 12
                    while time.time() < deadline:
                        Application.DoEvents()
                        if f.hbar._sl == 0:
                            break
                        time.sleep(0.05)
                    _crash("SELFTEST: drag-to-left -> sl=%d thumbRect=%s"
                           % (f.hbar._sl, f.hbar.thumb_rect()))

                    # 页面没有横向溢出时，滑块必须消失（不画任何东西）
                    try:
                        f.webview.ZoomFactor = 1.0
                    except Exception:
                        pass
                    f.webview.NavigateToString("<body style='margin:0'>窄页面</body>")
                    deadline = time.time() + 12
                    while time.time() < deadline:
                        Application.DoEvents()
                        if f.hbar.range() == 0:
                            break
                        time.sleep(0.05)
                    _crash("SELFTEST: narrow page -> range=%d scrollable=%s"
                           % (f.hbar.range(), f.hbar.scrollable()))
                    scan_thumb("hslider_none")
                except Exception as ex:
                    _crash("SELFTEST: hslider test FAILED: %r" % ex)
                    _crash(traceback.format_exc())

                # ---- 回归：MouseEnter 传的是普通 EventArgs（**没有 X/Y**）----
                # 真实事故：用户悬停底栏滑块时弹出 .NET 对话框
                # 「'EventArgs' object has no attribute 'Y'」（旧代码读了 e.Y）。
                try:
                    from System import EventArgs
                    plain = EventArgs.Empty
                    f.hbar._on_enter(f.hbar, plain)      # 直接调用不得抛异常
                    _crash("SELFTEST: hbar._on_enter(EventArgs) OK cursor=%s hover=%s"
                           % (f.hbar.Cursor, f.hbar._hover))
                    f.hbar._on_leave(f.hbar, plain)
                    _guard(f.hbar._on_enter)(f.hbar, plain)   # 走 _guard 路径也不得抛
                    _guard(f.btnClose._on_enter)(f.btnClose, plain)

                    def _boom(s, e):
                        raise RuntimeError("boom-test")
                    _guard(_boom)(f, plain)              # _guard 必须吞掉异常
                    _crash("SELFTEST: EventArgs 回归 OK（处理器容错 + _guard 吞异常均正常）")

                    # 全局异常网的真实触发：故意让一个 Paint 处理器抛异常（**不加 _guard**），
                    # 走 WinForms 消息循环 → 应由 Application.ThreadException 接管并只写日志，
                    # 而不是弹出「应用程序中发生了未处理的异常」系统对话框。
                    def _paint_boom(s, e):
                        raise RuntimeError("paint-boom-test")
                    f.hbar.Paint += _paint_boom
                    try:
                        f.hbar.Refresh()                # 触发真实 WM_PAINT
                        for _ in range(6):
                            Application.DoEvents()
                            time.sleep(0.05)
                    finally:
                        try:
                            f.hbar.Paint -= _paint_boom
                        except Exception:
                            pass
                    _crash("SELFTEST: 全局异常网触发测试结束（见上方 UI THREAD EXCEPTION 日志）")
                except Exception as ex:
                    _crash("SELFTEST: EventArgs 回归 FAILED: %r" % ex)
                    _crash(traceback.format_exc())

                # ---- 新窗口拦截：网页里的 window.open 必须开出「同款外壳」的窗口 ----
                # 先把主窗口调成一个有辨识度的尺寸，用来验证「新窗口与窗口 1 一致」
                f.Size = Size(700, 520)
                Application.DoEvents()
                _crash("SELFTEST: main resized to %s before spawning" % f.Size)
                try:
                    f.webview.CoreWebView2.ExecuteScriptAsync(
                        "window.open('https://cn.bing.com/?fb_newwin=1');")
                    _crash("SELFTEST: window.open issued from page")
                except Exception as ex:
                    _crash("SELFTEST: window.open exec FAILED: %r" % ex)
                spawned = None
                deadline = time.time() + 10
                while time.time() < deadline:
                    Application.DoEvents()
                    spawned = next((w for w in _OPEN_FORMS if w is not f), None)
                    if spawned is not None:
                        break
                    time.sleep(0.1)
                if spawned is None:
                    _crash("SELFTEST: NEW WINDOW NOT SPAWNED (open windows = %d)"
                           % len(_OPEN_FORMS))
                else:
                    _crash("SELFTEST: new window detected (open windows = %d), waiting core+nav..."
                           % len(_OPEN_FORMS))
                    deadline = time.time() + 25
                    while time.time() < deadline:
                        Application.DoEvents()
                        if spawned._core_ready and "bing.com" in str(spawned.webview.Source):
                            break
                        time.sleep(0.1)
                    try:
                        frameless = (spawned.FormBorderStyle
                                     == getattr(FormBorderStyle, "None"))
                    except Exception:
                        frameless = None
                    same_size = (spawned.Size.Width == f.Size.Width
                                 and spawned.Size.Height == f.Size.Height)
                    _crash("SELFTEST: newWin coreReady=%s frameless=%s toolbarVisible=%s "
                           "pinned=%s size=%s sameSizeAsMain=%s source=%r"
                           % (spawned._core_ready, frameless, spawned.pnlTitle.Visible,
                              spawned.TopMost, spawned.Size, same_size,
                              str(spawned.webview.Source)))
                    try:
                        bmp = Bitmap(max(1, spawned.ClientSize.Width),
                                     max(1, spawned.ClientSize.Height))
                        g = _G.FromImage(bmp)
                        hdc = g.GetHdc()
                        try:
                            _pw(spawned.Handle.ToInt64(), hdc.ToInt64(), 2)
                        finally:
                            g.ReleaseHdc(hdc)
                        out = os.path.join(_log_dir(), "selftest_newwin.png")
                        bmp.Save(out, ImageFormat.Png)
                        _crash("SELFTEST: shot newwin -> %s" % out)
                    except Exception as ex:
                        _crash("SELFTEST: shot newwin FAILED: %r" % ex)
                    shot_screen_win = spawned.Bounds
                    try:
                        bmp2 = Bitmap(max(1, shot_screen_win.Width),
                                      max(1, shot_screen_win.Height))
                        g2 = _G.FromImage(bmp2)
                        g2.CopyFromScreen(shot_screen_win.X, shot_screen_win.Y, 0, 0,
                                          Size(shot_screen_win.Width, shot_screen_win.Height))
                        out2 = os.path.join(_log_dir(), "selftest_screen_newwin.png")
                        bmp2.Save(out2, ImageFormat.Png)
                        _crash("SELFTEST: screen shot newwin -> %s" % out2)
                    except Exception as ex:
                        _crash("SELFTEST: screen shot newwin FAILED: %r" % ex)

                    # ---- 多窗口生命周期：关掉主窗口，另一个窗口不能被一起带走 ----
                    try:
                        f.Close()
                        for _ in range(10):
                            Application.DoEvents()
                            time.sleep(0.05)
                        _crash("SELFTEST: after closing MAIN -> openWindows=%d "
                               "newWindowDisposed=%s"
                               % (len(_OPEN_FORMS), spawned.IsDisposed))
                    except Exception as ex:
                        _crash("SELFTEST: close-main test FAILED: %r" % ex)
                _crash("SELFTEST: ALL DONE")
            except Exception:
                _crash("SELFTEST FAILED:\n%s" % traceback.format_exc())
            finally:
                for w in list(_OPEN_FORMS):
                    try:
                        w.Close()
                    except Exception:
                        pass

        _crash("STEP: BrowserForm class defined, creating instance")
        Application.EnableVisualStyles()
        Application.SetCompatibleTextRenderingDefault(False)
        # 兜底：把「UI 线程上未处理的异常」全部接管过来，只写日志、不让程序崩。
        # 否则 pythonnet 里事件处理器抛出的异常会被 WinForms 抛到系统级对话框
        # 「应用程序中发生了未处理的异常 …」，用户只能点继续/退出。
        try:
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException)
            Application.ThreadException += _guard(_on_thread_exception)
            _crash("STEP: UI exception net installed (CatchException + ThreadException)")
        except Exception as ex:
            _crash("WARN: install ThreadException handler failed: %r" % ex)
        try:
            from System import AppDomain
            AppDomain.CurrentDomain.UnhandledException += _guard(_on_domain_exception)
            _crash("STEP: AppDomain UnhandledException handler installed")
        except Exception as ex:
            _crash("WARN: install AppDomain handler failed: %r" % ex)
        form = BrowserForm()
        if os.environ.get("FB_SELFTEST") == "1":
            _crash("STEP: FB_SELFTEST enabled -> running self test")
            _register_form(form)
            form.FormClosed += lambda s, e: _unregister_form(form)
            _self_test(form)
            _crash("STEP: self test finished")
            return
        # 注意：这里不能用 Application.Run(form) —— 那样主窗口一关就会结束消息
        # 循环，把网页开出来的其它窗口一起带走。改成 Show + 无参 Run()，
        # 由 _unregister_form 在「最后一个窗口关闭」时才退出。
        _register_form(form)
        form.FormClosed += lambda s, e: _unregister_form(form)
        form.Show()
        _crash("STEP: main form shown, running Application.Run() (multi-window mode)")
        Application.Run()
        _crash("STEP: Application.Run returned")
    except Exception as ex:
        tb = traceback.format_exc()
        _crash("FATAL in _build_and_run:\n%s" % tb)
        _show_error("浮窗浏览器启动失败", tb)
        raise


if __name__ == "__main__":
    try:
        _crash("=== EXE START @ %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))
        # 必须在 .NET STA 线程中构建并运行 WinForms UI
        t = Thread(ThreadStart(_build_and_run))
        t.SetApartmentState(ApartmentState.STA)
        t.Start()
        t.Join()
    except Exception:
        tb = traceback.format_exc()
        _crash("FATAL top-level:\n%s" % tb)
        _show_error("浮窗浏览器启动失败", tb)
