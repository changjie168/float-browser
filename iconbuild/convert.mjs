import { Resvg } from '@resvg/resvg-js';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

// 源 SVG 已随项目保存，保证图标可复现重建（原图来自用户桌面）
const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, 'fuchuang.svg');
const OUT = join(__dirname, '..', 'app_1024.png');

const svg = fs.readFileSync(SRC, 'utf8');
const resvg = new Resvg(svg, {
  fitTo: { mode: 'width', value: 1024 },
  background: 'transparent',
});
const png = resvg.render().asPng();
fs.writeFileSync(OUT, png);
console.log('rendered ->', OUT, png.length, 'bytes');
