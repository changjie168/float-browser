import { Resvg } from '@resvg/resvg-js';
import fs from 'fs';

// 源 SVG 已随项目保存，保证图标可复现重建（原图来自用户桌面）
const SRC = 'I:/0-lingshi/llq/float-browser/iconbuild/fuchuang.svg';
const OUT = 'I:/0-lingshi/llq/float-browser/app_1024.png';

const svg = fs.readFileSync(SRC, 'utf8');
const resvg = new Resvg(svg, {
  fitTo: { mode: 'width', value: 1024 },
  background: 'transparent',
});
const png = resvg.render().asPng();
fs.writeFileSync(OUT, png);
console.log('rendered ->', OUT, png.length, 'bytes');
