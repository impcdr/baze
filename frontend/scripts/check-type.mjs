import { readFileSync } from 'node:fs';

const files = [
  'src/app/chat/chat-panel.html',
  'src/app/product/manage-page.html',
  'src/app/product/app-card.html',
  'src/app/product/make-page.html',
];

const banned = /\btext-(?:base|lg|xl|[2-9]xl)\b|font-size\s*:/;
let failed = false;

for (const file of files) {
  const source = readFileSync(file, 'utf8');
  if (!source.includes('bz-copy')) {
    console.error(`${file}: reading copy must use the bz-copy class`);
    failed = true;
  }
  if (file.endsWith('chat-panel.html') || file.endsWith('manage-page.html') || file.endsWith('make-page.html')) {
    const headings = source
      .split('\n')
      .filter((line) => banned.test(line) && !line.includes('font-display'));
    for (const line of headings) {
      console.error(`${file}: chat and descriptions stay on bz-copy, not a larger size\n  ${line.trim()}`);
      failed = true;
    }
  }
}

if (failed) process.exit(1);
console.log('type scale ok');
