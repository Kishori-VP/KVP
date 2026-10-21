const fs = require('fs');
const path = require('path');

const newTranslations = {
  "Ask AI": "AI ला विचारा",
  "Open database and index details": "डेटाबेस व इंडेक्स तपशील उघडा",
  "Minimize assistant": "सहाय्यक लहान करा",
  "Check database for newly added or modified data": "नवीन किंवा बदललेल्या माहितीसाठी डेटाबेस तपासा",
  "Syncing…": "सिंक करत आहे…",
  "Restore Ask AI": "AI सहाय्यक पूर्ववत करा",
  "Close Ask AI": "AI सहाय्यक बंद करा",
  "Connecting to Render… Free-tier server is waking up (~30-50s on initial load).": "सर्व्हरशी जोडणी सुरू आहे… सर्व्हर चालू होत आहे (पहिल्या वेळी ~30-50 सेकंद लागतात).",
  "The assistant returned an unreadable response. Please try again.": "सहाय्यकाकडून अयोग्य प्रतिसाद आला. कृपया पुन्हा प्रयत्न करा.",
  "All programmes & database assistant": "सर्व कार्यक्रम व डेटाबेस सहाय्यक",
  "Close assistant and clear conversation": "सहाय्यक बंद करा आणि संभाषण साफ करा",
  "Close assistant": "सहाय्यक बंद करा",
  "Knowledge database": "माहिती डेटाबेस",
  "Hide": "लपवा",
  "Indexed chunks:": "इंडेक्स केलेले भाग:",
  "Retrieval mode:": "शोध पद्धती:",
  "Chat model:": "चॅट मॉडेल:",
  "API configured:": "API कॉन्फिगर केले आहे:",
  "Sync New Data": "नवीन माहिती सिंक करा",
  "Do you want to force a full re-index of all records?": "तुम्हाला सर्व नोंदी नव्याने संपूर्ण री-इंडेक्स करायच्या आहेत का?",
  "Force a complete rebuild from scratch": "सुरुवातीपासून संपूर्ण नव्याने तयार करा",
  "Full Rebuild": "संपूर्ण पुनर्बांधणी",
  "Syncing:": "सिंक करत आहे:",
  "Syncing database…": "डेटाबेस सिंक होत आहे…",
  "Assistant ready": "सहाय्यक सज्ज आहे",
  "AI not configured": "AI कॉन्फिगर केलेले नाही",
  "Checking assistant status…": "सहाय्यकाची स्थिती तपासत आहे…",
  "Sync Data": "डेटा सिंक करा",
  "Sources:": "संदर्भ स्रोत:",
  "Searching database records…": "डेटाबेस नोंदी शोधत आहे…",
  "Ask about any programme or data…": "कोणत्याही कार्यक्रमाबद्दल किंवा माहितीबद्दल विचारा…",
  "Send message": "संदेश पाठवा",
  "Verify important records against the source data.": "महत्त्वाच्या नोंदी मूळ माहितीशी पडताळून पहा.",
  "Open Ask AI": "AI सहाय्यक उघडा",
  "PDF": "PDF",
  "Contact Coordinators to register:": "नोंदणीसाठी समन्वयकांशी संपर्क साधा:",
  "Call Programme Office": "प्रकल्प कार्यालयास फोन करा",
  "Email Registration Desk": "नोंदणी कक्षास ईमेल करा",
  "Select an attendance status before saving.": "जतन करण्यापूर्वी हजेरी स्थिती निवडा.",
  "Attendance saved successfully.": "हजेरी यशस्वीरीत्या जतन केली.",
  "NoteCam Check-In Photo": "NoteCam चेक-इन फोटो",
  "NoteCam Check-Out Photo": "NoteCam चेक-आऊट फोटो",
  "Hi! Ask me anything about our programmes, field activities, villages, beneficiaries, targets, cases, events, or attendance. I answer using all database records across all programmes.": "नमस्कार! आमच्या सर्व कार्यक्रमांबद्दल, क्षेत्रीय कामांबद्दल, गावे, लाभार्थी, उद्दिष्टे, प्रकरणे, कार्यक्रम किंवा हजेरीबद्दल काहीही विचारा. मी सर्व कार्यक्रमांच्या डेटाबेस नोंदींमधून उत्तरे देतो."
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
