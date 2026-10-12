# -*- coding: utf-8 -*-
"""无界面渲染测试：把自绘图标画到 PNG。

产出两张图：
  glyph_test.png           1x 真实观感（浅底／深底激活态）+ 3x 放大看细节
  glyph_test_1x_zoom.png   把「真实 1x 光栅结果」用最近邻放大 4 倍，
                           用于判断小尺寸下图标是否还认得出、是否精致
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import float_browser_native as fb
    print("import ok", flush=True)
    fb._ensure_drawing()

    from System.Drawing import Bitmap, Color, Font, SolidBrush, Graphics
    from System.Drawing.Imaging import ImageFormat
    from System.Drawing.Drawing2D import InterpolationMode, PixelOffsetMode

    glyphs = ["back", "fwd", "reload", "pin", "min", "full", "restore", "close"]
    BW, BH = 34, 30          # 按钮尺寸（与程序内一致）
    W = BW + 10
    LIGHT = Color.FromArgb(0xFA, 0xFA, 0xFC)
    DARK = Color.FromArgb(0x1D, 0x1D, 0x1F)
    WHITE = Color.FromArgb(0xFF, 0xFF, 0xFF)
    BASE = os.path.dirname(os.path.abspath(__file__))

    def draw_row(g, z, bg, fg, top, names=False):
        for i, gl in enumerate(glyphs):
            x0 = 6 + int(i * W * z)
            g.FillRectangle(SolidBrush(bg), x0, top, BW * z, BH * z)
            st = g.Save()
            g.TranslateTransform(float(x0), float(top))
            g.ScaleTransform(float(z), float(z))
            fb._draw_glyph(g, gl, 0, 0, BW, BH, fg)
            g.Restore(st)
            if names:
                g.DrawString(gl, Font("Segoe UI", 7),
                             SolidBrush(Color.FromArgb(0x8A, 0x8A, 0x95)),
                             x0 + 2, top + BH * z + 4)

    # ---- 图 1：1x 常态 / 1x 激活态 / 3x 放大 ----
    rows = [(1, LIGHT, DARK, True), (1, DARK, WHITE, False), (3, LIGHT, DARK, True)]
    row_h = [int((BH + 30) * z) for z, _, _, _ in rows]
    bmp = Bitmap(int(W * len(glyphs) * 3) + 12, 10 + sum(row_h))
    g = Graphics.FromImage(bmp)
    g.Clear(Color.FromArgb(0xF2, 0xF2, 0xF6))
    top = 6
    for z, bg, fg, names in rows:
        draw_row(g, z, bg, fg, top, names)
        top += int((BH + 30) * z)
    p1 = BASE + r"\glyph_test.png"
    bmp.Save(p1, ImageFormat.Png)

    # ---- 图 2：真实 1x 光栅 → 最近邻放大 4 倍 ----
    small = Bitmap(int(W * len(glyphs)) + 12, BH + 8)
    gs = Graphics.FromImage(small)
    gs.Clear(LIGHT)
    draw_row(gs, 1, LIGHT, DARK, 4)
    big = Bitmap(small.Width * 4, small.Height * 4)
    gb = Graphics.FromImage(big)
    gb.InterpolationMode = InterpolationMode.NearestNeighbor
    gb.PixelOffsetMode = PixelOffsetMode.Half
    gb.DrawImage(small, 0, 0, big.Width, big.Height)
    p2 = BASE + r"\glyph_test_1x_zoom.png"
    big.Save(p2, ImageFormat.Png)

    print("saved:", p1, bmp.Width, bmp.Height, flush=True)
    print("saved:", p2, big.Width, big.Height, flush=True)
except Exception:
    print("FAILED:\n" + traceback.format_exc(), flush=True)
