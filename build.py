# -*- coding: utf-8 -*-
"""浮窗浏览器 —— 通用打包脚本（跨机器可用）

和 `build_exe.bat` 的区别：`build_exe.bat` 里写死了本机的 Python 虚拟环境路径，
换一台电脑就必须手改。这个脚本全部自动探测：

  * Python 解释器   —— 用当前运行 `python build.py` 的那个（可来自 venv）
  * WebView2 托管 DLL —— 从已安装的 `webview`(pywebview) 包里定位 `webview/lib`
  * 输出目录        —— 自动递增 `build_vN` / `dist_vN`，不覆盖历史产物

用法：

    python build.py                # 窗口版（正式发布用这个）
    python build.py --debug        # 控制台版（出错时看得到报错）
    python build.py --selftest     # 打完包立刻跑一遍内置自检
    python build.py --out v20      # 手动指定输出后缀（build_v20 / dist_v20）

前置依赖（只需装一次）：

    pip install pythonnet pywebview pyinstaller

产物：`dist_vN/FloatBrowser.exe`（或 `FloatBrowser_debug.exe`），
可直接双击运行，也可直接拷走当绿色版。
"""

import os
import re
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "float_browser_native.py")
ICON = os.path.join(HERE, "app.ico")


# --------------------------------------------------------------------------
# 环境探测
# --------------------------------------------------------------------------
def find_webview_lib():
    """定位 pywebview 自带的 WebView2 托管 DLL 目录（webview/lib）。"""
    try:
        import importlib.util

        spec = importlib.util.find_spec("webview")
        if spec is None or not spec.submodule_search_locations:
            return None
        pkg = list(spec.submodule_search_locations)[0]
        lib = os.path.join(pkg, "lib")
        return lib if os.path.isdir(lib) else None
    except Exception:
        return None


def check_pyinstaller():
    try:
        import PyInstaller  # noqa: F401

        return True
    except Exception:
        return False


def next_suffix():
    """扫描既有 build_vN / dist_vN，返回下一个可用编号。"""
    mx = 0
    for name in os.listdir(HERE):
        m = re.match(r"^(?:build|dist)_v(\d+)$", name)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    import argparse

    ap = argparse.ArgumentParser(description="打包浮窗浏览器为单文件 EXE")
    ap.add_argument("--debug", action="store_true",
                    help="生成控制台版（FloatBrowser_debug.exe），便于排错")
    ap.add_argument("--selftest", action="store_true",
                    help="打包完成后自动跑一次内置自检（FB_SELFTEST=1）")
    ap.add_argument("--out", default=None,
                    help="输出目录后缀，默认自动递增，如 v20 -> dist_v20 / build_v20")
    args = ap.parse_args()

    if not os.path.isfile(MAIN):
        print("[错误] 找不到主程序：%s" % MAIN)
        return 1
    if not os.path.isfile(ICON):
        print("[警告] 找不到图标 app.ico，打包后将使用 PyInstaller 默认图标")

    if not check_pyinstaller():
        print("[错误] 当前 Python 环境没有 PyInstaller。请先执行：")
        print("       %s -m pip install pythonnet pywebview pyinstaller" % sys.executable)
        return 1

    lib = find_webview_lib()
    if not lib:
        print("[错误] 找不到 pywebview 的 webview/lib 目录。请先执行：")
        print("       %s -m pip install pywebview" % sys.executable)
        return 1

    core = os.path.join(lib, "Microsoft.Web.WebView2.Core.dll")
    winforms = os.path.join(lib, "Microsoft.Web.WebView2.WinForms.dll")
    loader = os.path.join(lib, "runtimes", "win-x64", "native", "WebView2Loader.dll")
    for p in (core, winforms, loader):
        if not os.path.isfile(p):
            print("[错误] 缺少 WebView2 依赖文件：%s" % p)
            return 1

    suffix = args.out or ("v%d" % next_suffix())
    distpath = os.path.join(HERE, "dist_" + suffix)
    workpath = os.path.join(HERE, "build_" + suffix)
    logpath = os.path.join(HERE, "build_%s.log" % suffix)
    name = "FloatBrowser_debug" if args.debug else "FloatBrowser"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console" if args.debug else "--windowed",
        "--name", name,
        "--icon", ICON,
        "--hidden-import", "clr",
        "--hidden-import", "pythonnet",
        "--collect-submodules", "clr_loader",
        "--add-binary", "%s;." % core,
        "--add-binary", "%s;." % winforms,
        "--add-binary", "%s;." % loader,
        "--add-binary", "%s;." % ICON,
        "--distpath", distpath,
        "--workpath", workpath,
        "--specpath", workpath,
        "--noconfirm",
        MAIN,
    ]

    print("Python   : %s" % sys.executable)
    print("webview  : %s" % lib)
    print("输出目录 : %s" % distpath)
    print("=" * 60)
    print(" ".join('"%s"' % c if " " in c else c for c in cmd))
    print("=" * 60)

    with open(logpath, "w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        print("[失败] PyInstaller 退出码 %d，完整日志见：%s" % (proc.returncode, logpath))
        return proc.returncode

    exe = os.path.join(distpath, name + ".exe")
    if not os.path.isfile(exe):
        print("[失败] 未生成 %s，请查看日志：%s" % (exe, logpath))
        return 1

    print("[完成] %s （%.1f MB）" % (exe, os.path.getsize(exe) / 1024 / 1024))
    print("       构建日志：%s" % logpath)

    if args.selftest:
        print("[自检] 以 FB_SELFTEST=1 运行新 EXE ...")
        env = dict(os.environ, FB_SELFTEST="1")
        r = subprocess.run([exe], env=env, cwd=distpath,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = (r.stdout or b"").decode("utf-8", "replace")
        tail = "\n".join(out.strip().splitlines()[-25:])
        print(tail)
        print("[自检] 退出码 %d；运行日志 %s" % (
            r.returncode, os.path.join(os.environ.get("LOCALAPPDATA", distpath),
                                       "FloatBrowser", "FloatBrowser_crash.log")))
        return r.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
