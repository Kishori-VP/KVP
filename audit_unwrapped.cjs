const fs = require('fs');
const path = require('path');

function getFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat && stat.isDirectory()) {
      results = results.concat(getFiles(fullPath));
    } else if (file.endsWith('.jsx')) {
      results.push(fullPath);
    }
  });
  return results;
}

const allFiles = getFiles(path.join(__dirname, 'frontend/src'));
console.log(`Auditing ${allFiles.length} JSX files for unwrapped text...`);

let totalRaw = 0;

allFiles.forEach(fullPath => {
  const relPath = path.relative(__dirname, fullPath);
  const content = fs.readFileSync(fullPath, 'utf8');

  // Match text between JSX tags like >Some English Text<
  const regex = />([^<>{}\n]+)</g;
  let match;
  const rawTexts = new Set();
  while ((match = regex.exec(content)) !== null) {
    const text = match[1].trim();
    // Filter out symbols, whitespace, pure numbers, tailwind class remnants, code remnants
    if (
      text.length > 2 &&
      /^[A-Za-z]/.test(text) &&
      !text.includes('className') &&
      !text.includes('const ') &&
      !text.startsWith('http') &&
      !text.startsWith('import ') &&
      !text.startsWith('export ') &&
      !/^[0-9\s.,/\\:;+\-_*#@!&%()=[\]{}|~`^?><'"]+$/.test(text)
    ) {
      // Check if it's not a common technical or js keyword
      if (!['true', 'false', 'null', 'undefined', 'return', 'key', 'id'].includes(text)) {
        rawTexts.add(text);
      }
    }
  }

  // Also match placeholder="..." or title="..." or alt="..." where value has english words
  const attrRegex = /\b(placeholder|aria-label)\s*=\s*"([^"{}\n]+)"/g;
  while ((match = attrRegex.exec(content)) !== null) {
    const text = match[2].trim();
    if (text.length > 2 && /^[A-Za-z]/.test(text)) {
      rawTexts.add(`[${match[1]}] ${text}`);
    }
  }

  if (rawTexts.size > 0) {
    console.log(`\n=== Raw strings in ${relPath} (${rawTexts.size}) ===`);
    rawTexts.forEach(t => console.log('  "' + t + '"'));
    totalRaw += rawTexts.size;
  }
});

console.log(`\nAudit complete. Found ${totalRaw} potential unwrapped strings.`);
