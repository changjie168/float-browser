"""浮窗浏览器 —— 无边框 / 轻量 / 可钉在最上层。

基于 Python + pywebview，复用系统自带的 WebView2（Edge）引擎，
不捆绑 Chromium，因此内存占用极低。
"""
import os
import sys
import webbrowser

import webview

# 兼容 PyInstaller 打包：冻结后资源文件位于 sys._MEIPASS 下
if getattr(sys, "frozen", False):
    HERE = sys._MEIPASS
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "ui.html")
MIN_W, MIN_H = 240, 160


class Api:
    """暴露给前端（ui.html 内 JS）调用的原生能力。"""

    def __init__(self):
        self.window = None  # 由下方 main() 在窗口创建后注入

    def get_geometry(self):
        """返回 [x, y, width, height]（屏幕坐标）。"""
        w = self.window
        return [w.x, w.y, w.width, w.height]

    def set_geometry(self, x, y, w, h):
        """移动并缩放窗口，限制最小尺寸。"""
        w = max(MIN_W, int(w))
        h = max(MIN_H, int(h))
        self.window.move(int(x), int(y))
        self.window.resize(w, h)

    def toggle_pin(self):
        """切换『始终置顶』。pywebview 6.x 用 on_top 属性，赋值即生效。"""
        self.window.on_top = not self.window.on_top

    def minimize(self):
        self.window.minimize()

    def close(self):
        self.window.destroy()

    def open_external(self, url):
        """用系统默认浏览器打开（用于拒绝内嵌的站点）。"""
        if url:
            webbrowser.open(url)


def main():
    api = Api()
    window = webview.create_window(
        "浮窗浏览器",
        url=UI,
        width=460,
        height=340,
        min_size=(MIN_W, MIN_H),
        frameless=True,   # 无边框
        on_top=False,     # 默认不置顶，由 📌 切换
        easy_drag=False,  # 自定义拖动逻辑
        js_api=api,
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
