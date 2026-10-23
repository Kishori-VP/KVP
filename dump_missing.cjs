const fs = require('fs');
const path = require('path');

const mrContent = fs.readFileSync(path.join(__dirname, 'frontend/src/lib/mr.js'), 'utf8');
const mrKeys = new Set();
const lines = mrContent.split('\n');
for (const line of lines) {
  const m = line.match(/^\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*:/);
  if (m) mrKeys.add(m[1].replace(/\\"/g, '"'));
}

function getFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat && stat.isDirectory()) results = results.concat(getFiles(fullPath));
    else if (file.endsWith('.jsx') || file.endsWith('.js')) results.push(fullPath);
  });
  return results;
}

const files = getFiles(path.join(__dirname, 'frontend/src'));
const missing = new Set();

files.forEach(file => {
  if (file.endsWith('mr.js')) return;
  const content = fs.readFileSync(file, 'utf8');
  const regex = /\bt\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    const str = (match[1] || match[2] || '').replace(/\\'/g, "'").replace(/\\"/g, '"');
    if (str && !mrKeys.has(str)) missing.add(str);
  }
});

const arr = Array.from(missing).sort();
fs.writeFileSync(path.join(__dirname, 'missing_keys.json'), JSON.stringify(arr, null, 2), 'utf8');
console.log('Saved', arr.length, 'missing keys to missing_keys.json');
