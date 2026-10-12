# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['clr', 'pythonnet']
hiddenimports += collect_submodules('clr_loader')


a = Analysis(
    ['I:/0-lingshi/llq/float-browser/float_browser_native.py'],
    pathex=[],
    binaries=[('C:/Users/admin/.workbuddy/binaries/python/envs/default/Lib/site-packages/webview/lib/Microsoft.Web.WebView2.Core.dll', '.'), ('C:/Users/admin/.workbuddy/binaries/python/envs/default/Lib/site-packages/webview/lib/Microsoft.Web.WebView2.WinForms.dll', '.'), ('C:/Users/admin/.workbuddy/binaries/python/envs/default/Lib/site-packages/webview/lib/runtimes/win-x64/native/WebView2Loader.dll', '.'), ('I:/0-lingshi/llq/float-browser/app.ico', '.')],
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
    name='FloatBrowser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['I:/0-lingshi/llq/float-browser/app.ico'],
)
