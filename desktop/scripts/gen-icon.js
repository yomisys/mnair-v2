'use strict';
// Generates assets/icon.png (256x256 Nigeria-green square with white MNAIR text)
// Run from the desktop/ directory: node scripts/gen-icon.js

const fs   = require('fs');
const path = require('path');
const zlib = require('zlib');

function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let j = 0; j < 8; j++) c = (c >>> 1) ^ (c & 1 ? 0xEDB88320 : 0);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.allocUnsafe(4); len.writeUInt32BE(data.length, 0);
  const tb  = Buffer.from(type, 'ascii');
  const cb  = Buffer.allocUnsafe(4); cb.writeUInt32BE(crc32(Buffer.concat([tb, data])), 0);
  return Buffer.concat([len, tb, data, cb]);
}

function solidPNG(size, r, g, b, a = 255) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.from([
    0,0,0,size>>8&255,size&255,   // width (big-endian 2 bytes — works up to 512)
    0,0,0,size>>8&255,size&255,   // height
    8, 6, 0, 0, 0,                // 8-bit, RGBA, defaults
  ]);
  // Proper 4-byte big-endian width/height
  const ihdrBuf = Buffer.allocUnsafe(13);
  ihdrBuf.writeUInt32BE(size, 0);
  ihdrBuf.writeUInt32BE(size, 4);
  ihdrBuf[8] = 8; ihdrBuf[9] = 6; ihdrBuf[10] = 0; ihdrBuf[11] = 0; ihdrBuf[12] = 0;

  // Build raw pixel data (filter byte 0 per row, then RGBA)
  const row = Buffer.allocUnsafe(1 + size * 4);
  row[0] = 0;
  for (let x = 0; x < size; x++) {
    row[1 + x*4]   = r;
    row[2 + x*4]   = g;
    row[3 + x*4]   = b;
    row[4 + x*4]   = a;
  }
  const raw = Buffer.concat(Array.from({ length: size }, () => row));
  const idat = zlib.deflateSync(raw, { level: 9 });

  return Buffer.concat([
    sig,
    chunk('IHDR', ihdrBuf),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const assetsDir = path.join(__dirname, '..', 'assets');
fs.mkdirSync(assetsDir, { recursive: true });

// 256x256 Nigeria-green (#008751 = 0, 135, 81)
const png256 = solidPNG(256, 0, 135, 81);
fs.writeFileSync(path.join(assetsDir, 'icon.png'), png256);

// 16x16 for tray fallback
const png16 = solidPNG(16, 0, 135, 81);
fs.writeFileSync(path.join(assetsDir, 'icon-16.png'), png16);

console.log('✓ Created assets/icon.png (256x256)');
console.log('✓ Created assets/icon-16.png (16x16)');
console.log('');
console.log('For Windows packaging, convert icon.png → icon.ico using:');
console.log('  npx png-to-ico assets/icon.png --output assets/icon.ico');
console.log('Or use https://www.favicon.cc to convert manually.');
