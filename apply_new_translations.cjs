const fs = require('fs');
const path = require('path');

const newTranslations = {
  "Handover village": "गाव हस्तांतरित करा",
  "Handover Village Responsibility": "गावाची जबाबदारी हस्तांतरित करा",
  "Confirm Handover": "हस्तांतरण निश्चित करा",
  "Village Handover Between Tais": "ताईंमधील गाव हस्तांतरण",
  "Transfer village responsibility from one Tai to another. The source Tai’s assignment for this village will be closed in history, and a new assignment will be started for the target Tai.": "एका ताईंकडून दुसऱ्या ताईंकडे गावाची जबाबदारी वर्ग करा. जुन्या ताईंची या गावाची नेमणूक इतिहासात बंद केली जाईल आणि नवीन ताईंसाठी नवीन नेमणूक सुरू होईल.",
  "From Tai (Handing over) *": "मूळ ताई (गाव देणाऱ्या) *",
  "Select source Tai": "मूळ ताई निवडा",
  "Village to Handover *": "हस्तांतरित करावयाचे गाव *",
  "Select village to handover": "हस्तांतरणासाठी गाव निवडा",
  "To Tai (Recipient) *": "नवीन ताई (गाव स्वीकारणाऱ्या) *",
  "Select the Tai taking over responsibility for this village.": "या गावाची जबाबदारी घेणाऱ्या नवीन ताई निवडा.",
  "Select recipient Tai": "नवीन जबाबदार ताई निवडा",
  "Included in Handover": "हस्तांतरणात समाविष्ट बाबी",
  "Transfer Kishori Groups of this village to new Tai": "या गावातील किशोरी गट नवीन ताईंकडे वर्ग करा",
  "Transfer open beneficiary cases in this village to new Tai": "या गावातील सुरू असलेली लाभार्थी प्रकरणे नवीन ताईंकडे वर्ग करा",
  "Handover Date": "हस्तांतरणाची तारीख",
  "Reason for Handover *": "हस्तांतरणाचे कारण *",
  "e.g. Area reallocation, medical leave, or workload balance": "उदा. कार्यक्षेत्र पुनर्रचना, वैद्यकीय रजा किंवा कामाचे नियोजन"
};

const mrPath = path.join(__dirname, 'frontend/src/lib/mr.js');
const mrContent = fs.readFileSync(mrPath, 'utf8');

// Parse existing key-value pairs
const lines = mrContent.split('\n');
const entries = new Map();

for (const line of lines) {
  const m = line.match(/^\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/);
  if (m) {
    const key = m[1].replace(/\\"/g, '"');
    const val = m[2].replace(/\\"/g, '"');
    entries.set(key, val);
  }
}

// Merge new
let added = 0;
for (const [k, v] of Object.entries(newTranslations)) {
  if (!entries.has(k) || entries.get(k) !== v) {
    entries.set(k, v);
    added++;
  }
}

// Sort alphabetically
const sortedKeys = Array.from(entries.keys()).sort((a, b) => a.localeCompare(b));

let output = '/** Marathi UI strings, keyed by the English text used in the code. Missing keys fall back to English. */\nexport default {\n';
for (const k of sortedKeys) {
  const escapedK = k.replace(/"/g, '\\"');
  const escapedV = entries.get(k).replace(/"/g, '\\"');
  output += `  "${escapedK}": "${escapedV}",\n`;
}
output += '};\n';

fs.writeFileSync(mrPath, output, 'utf8');
console.log(`Successfully merged ${added} translations into mr.js. Total keys now: ${entries.size}`);
