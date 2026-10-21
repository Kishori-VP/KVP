const fs = require('fs');
const path = require('path');

// Read mr.js
const mrPath = path.join(__dirname, 'frontend/src/lib/mr.js');
const mrContent = fs.readFileSync(mrPath, 'utf8');

// Parse keys
const mrKeys = new Set();
const lines = mrContent.split('\n');
for (const line of lines) {
  const m = line.match(/^\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*:/);
  if (m) {
    mrKeys.add(m[1].replace(/\\"/g, '"'));
  }
}

console.log('Total keys in mr.js:', mrKeys.size);

function getFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat && stat.isDirectory()) {
      results = results.concat(getFiles(fullPath));
    } else if (file.endsWith('.jsx') || file.endsWith('.js')) {
      results.push(fullPath);
    }
  });
  return results;
}

const files = getFiles(path.join(__dirname, 'frontend/src'));
const missing = new Map();

files.forEach(file => {
  if (file.endsWith('mr.js')) return;
  const content = fs.readFileSync(file, 'utf8');
  // Match t('...') and t("...")
  const regex = /\bt\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    const str = (match[1] || match[2] || '').replace(/\\'/g, "'").replace(/\\"/g, '"');
    if (str && !mrKeys.has(str)) {
      if (!missing.has(str)) missing.set(str, []);
      missing.get(str).push(path.basename(file));
    }
  }
});

console.log('Total missing keys:', missing.size);
const sorted = Array.from(missing.entries()).sort((a, b) => b[1].length - a[1].length);
for (const [k, src] of sorted) {
  console.log(`MISSING: "${k}" [${src.join(', ')}]`);
}
