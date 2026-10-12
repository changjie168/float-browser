# -*- coding: utf-8 -*-
"""把浮窗浏览器的「开发源码」打包成一份 zip，方便拷贝到其他电脑继续开发。

只收源码 / 构建脚本 / 图标素材 / 安装器脚本 / 打包工具链，**不收**任何中间产物
（build_*、dist_*、*.log、自检截图、成品 exe 等），因此包很小，便于 U 盘或网盘携带。

用法：

    python pack_source.py                # 输出到桌面
    python pack_source.py --out D:\\x.zip

打包范围见下面的 INCLUDE_FILES / INCLUDE_DIRS，需要增删文件直接改这两个列表即可。
"""

import os
import sys
import time
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.basename(HERE) or "float-browser"

# ---------------------------------------------------------------------------
# 顶层文件白名单（相对项目根）
# ---------------------------------------------------------------------------
INCLUDE_FILES = [
    # —— 核心源码 ——
    "float_browser_native.py",   # 主程序（原生 WebView2 浮窗浏览器）
    "float_browser.py",          # 早期 iframe 版，仅作参考
    "README.md",
    "requirements.txt",
    "pack_source.py",            # 本打包脚本
    "build.py",                  # 跨机器通用打包脚本（自动探测环境）
    "build_exe.bat",             # 本机一键打包脚本（硬编码了 venv 路径，换机需改）
    "run.bat",
    # —— 图标 ——
    "app.ico",
    "app_1024.png",
    "make_icon.py",
    # —— 前端外壳 / 旧版素材 ——
    "preview.html",
    "ui.html",
    "start.html",
    # —— 小工具 ——
    "check_edge.py",
    "glyph_render_test.py",
    "probe_verify.py",
    # —— PyInstaller 规格文件 ——
    "FloatBrowser.spec",
    "FloatBrowser_debug.spec",
    # —— 换机说明 ——
    "换机开发指南.md",
]

# ---------------------------------------------------------------------------
# 目录级白名单：(目录名, 子项过滤函数)
# ---------------------------------------------------------------------------
def _iconbuild(rel, name, is_dir):
    return name != "node_modules"


def _installer(rel, name, is_dir):
    # 不收 20 MB 的安装程序成品与编译日志
    return not name.lower().endswith((".exe", ".log"))


def _tools(rel, name, is_dir):
    low = name.lower()
    if low.startswith("unins"):          # Inno Setup 自带的卸载程序，不需要
        return False
    if low.endswith((".chm", ".issig")):  # 帮助文档与签名校验文件，不需要
        return False
    if low == "examples":                # Inno Setup 自带示例
        return False
    if low == "innosetup.exe":           # Inno Setup 原始安装包（10 MB），已有便携版
        return False
    return True


INCLUDE_DIRS = [
    ("iconbuild", _iconbuild),   # SVG 源图 + resvg 转换脚本
    ("installer", _installer),   # Inno Setup 脚本生成器 + 已生成的 setup.iss
    ("_tools", _tools),          # InnoSetup6 便携版 + WebView2 引导程序
]

SKIP_EXT = {".log", ".pyc", ".tmp"}


def build_list():
    """返回 [(绝对路径, zip 内的相对路径)]"""
    items = []
    for rel in INCLUDE_FILES:
        p = os.path.join(HERE, rel)
        if os.path.isfile(p):
            items.append((p, rel))
        else:
            print("  [跳过·缺失] %s" % rel)

    for dname, filt in INCLUDE_DIRS:
        root = os.path.join(HERE, dname)
        if not os.path.isdir(root):
            print("  [跳过·缺失目录] %s" % dname)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, HERE)
            keep = []
            for d in dirnames:
                if d == "__pycache__":
                    continue
                if filt(rel_dir, d, True):
                    keep.append(d)
            dirnames[:] = keep
            for f in filenames:
                if os.path.splitext(f)[1].lower() in SKIP_EXT:
                    continue
                if not filt(rel_dir, f, False):
                    continue
                items.append((os.path.join(dirpath, f),
                              os.path.join(rel_dir, f).replace("\\", "/")))
    return items


def main():
    out = None
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    if not out:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
        stamp = time.strftime("%Y%m%d")
        out = os.path.join(desktop, "浮窗浏览器_源码_1.5.0_%s.zip" % stamp)

    print("项目根 : %s" % HERE)
    print("输出   : %s" % out)
    print("-" * 60)

    items = build_list()
    items.sort(key=lambda x: x[1])

    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src, rel in items:
            size = os.path.getsize(src)
            total += size
            zf.write(src, "%s/%s" % (PROJECT, rel))
            print("  + %-58s %8.1f KB" % (rel, size / 1024))

    print("-" * 60)
    print("共 %d 个文件，原始 %.1f MB -> 压缩包 %.1f MB"
          % (len(items), total / 1024 / 1024, os.path.getsize(out) / 1024 / 1024))
    print("完成。")


if __name__ == "__main__":
    main()
