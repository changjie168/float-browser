# -*- coding: utf-8 -*-
"""由 resvg 渲染出的 app_1024.png 合成多尺寸 app.ico。"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(HERE, "app_1024.png")
ICO = os.path.join(HERE, "app.ico")

img = Image.open(PNG).convert("RGBA")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
frames = [img.resize(s, Image.LANCZOS) for s in sizes]
img.save(ICO, sizes=sizes)
print("saved ICO ->", ICO, "bytes:", os.path.getsize(ICO), "sizes:", sizes)
