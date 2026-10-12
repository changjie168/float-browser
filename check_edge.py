# -*- coding: utf-8 -*-
"""采样窗口边缘像素：核对 1px 描边颜色，以及右侧滚动条实际宽度。"""
import sys
from PIL import Image

files = sys.argv[1:] or ["selftest_screen_normal.png"]

for name in files:
    try:
        im = Image.open(name).convert("RGB")
    except Exception as e:
        print(name, "->", e)
        continue
    w, h = im.size
    print("== %s  %dx%d ==" % (name, w, h))
    print("  左上(0,0)       :", im.getpixel((0, 0)))
    print("  左边缘(0,h//2)  :", im.getpixel((0, h // 2)))
    print("  左下(0,h-1)     :", im.getpixel((0, h - 1)))
    print("  底边(w//2,h-1)  :", im.getpixel((w // 2, h - 1)))
    print("  右下(w-1,h-1)   :", im.getpixel((w - 1, h - 1)))
    print("  内缩(2,h//2)    :", im.getpixel((2, h // 2)))
    print("  内缩(w-3,h//2)  :", im.getpixel((w - 3, h // 2)))

    # 扫描最右 12 列，找滚动条（与页面底色不同的列）
    row = h // 2
    print("  右侧 12 列像素(自上而下取中部行):")
    cols = []
    for dx in range(1, 13):
        cols.append((w - dx, im.getpixel((w - dx, row))))
    for x, px in reversed(cols):
        print("    x=%4d -> %s" % (x, px))

    # 逐列求平均色，检测滚动条厚度
    print("  逐列平均色（最右 8 列）:")
    for dx in range(1, 9):
        x = w - dx
        tot = [0, 0, 0]
        n = 0
        for y in range(2, h - 2, 5):
            p = im.getpixel((x, y))
            tot[0] += p[0]
            tot[1] += p[1]
            tot[2] += p[2]
            n += 1
        print("    x=%4d 平均 = (%d, %d, %d)" % (x, tot[0] // n, tot[1] // n, tot[2] // n))
