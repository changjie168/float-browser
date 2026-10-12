# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
import os
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "float_browser_native.py")
ICON = os.path.join(HERE, "app.ico")

# 定位 pywebview 自带的 WebView2 托管 DLL 目录（webview/lib），不写死本机路径
_webview_lib = None
_webview_spec = importlib.util.find_spec("webview")
if _webview_spec is not None and getattr(_webview_spec, "submodule_search_locations", None):
    _pkg = list(_webview_spec.submodule_search_locations)[0]
    _cand = os.path.join(_pkg, "lib")
    if os.path.isdir(_cand):
        _webview_lib = _cand

hiddenimports = ["clr", "pythonnet"]
hiddenimports += collect_submodules("clr_loader")

_binaries = []
if _webview_lib:
    for _dll in (
        "Microsoft.Web.WebView2.Core.dll",
        "Microsoft.Web.WebView2.WinForms.dll",
        os.path.join("runtimes", "win-x64", "native", "WebView2Loader.dll"),
    ):
        _binaries.append((os.path.join(_webview_lib, _dll), "."))
_binaries.append((ICON, "."))


a = Analysis(
    [MAIN],
    pathex=[],
    binaries=_binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FloatBrowser_debug",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
)
