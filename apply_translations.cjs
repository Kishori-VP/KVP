const fs = require('fs');
const path = require('path');

const mrFile = path.join(__dirname, 'frontend/src/lib/mr.js');
let content = fs.readFileSync(mrFile, 'utf8');

const newTranslations = {
  "Actions": "कृती",
  "Active targets": "सक्रिय उद्दिष्टे",
  "Activities Done": "पूर्ण केलेले उपक्रम",
  "Admin dashboard": "प्रशासक डॅशबोर्ड",
  "Admin — field management, village & target assignment": "प्रशासक — क्षेत्र व्यवस्थापन, गाव व उद्दिष्ट वाटप",
  "Admins": "प्रशासक",
  "All Tais": "सर्व ताई",
  "All active Tais": "सर्व सक्रिय ताई",
  "Applied targets: {c} updated for all active Tais.": "उद्दिष्टे लागू केली: सर्व सक्रिय ताईंसाठी {c} उद्दिष्टे अद्यतनित झाली.",
  "Apply default weekly ({w}) and monthly ({m}) visit targets to all active Tais?": "सर्व सक्रिय ताईंना साप्ताहिक ({w}) आणि मासिक ({m}) भेटींचे डीफॉल्ट उद्दिष्ट लागू करायचे का?",
  "Approval Status": "मंजुरी स्थिती",
  "Are you sure you want to delete this daily report?": "तुम्हाला हा दैनिक अहवाल नक्की हटवायचा आहे का?",
  "As Stakeholder, you have full oversight across both Admins and Tais (Volunteers). You can manage roles, view all field operations, and audit system actions.": "भागधारक म्हणून, तुमच्याकडे प्रशासक आणि ताई (स्वयंसेवक) दोघांवर संपूर्ण देखरेख आहे. तुम्ही भूमिका बदलू शकता, सर्व क्षेत्रीय काम पाहू शकता आणि प्रणालीचे ऑडिट करू शकता.",
  "Assign / Update": "नेमा / अद्यतन करा",
  "Assign a village to this Tai. Multiple villages can also be assigned from Tai details.": "या ताईला गाव नेमा. ताईच्या तपशीलातून एकापेक्षा जास्त गावे देखील नेमली जाऊ शकतात.",
  "Assign another village to this Tai. A Tai can be assigned to multiple villages concurrently.": "या ताईला आणखी एक गाव नेमा. एका ताईला एकाच वेळी अनेक गावे नेमली जाऊ शकतात.",
  "Assigned village only": "फक्त नेमलेले गाव",
  "Attendance already completed for today. Daily attendance is taken only once.": "आजची हजेरी आधीच पूर्ण झाली आहे. रोजची हजेरी दिवसातून एकदाच घेतली जाते.",
  "Attendance completed for today": "आजची हजेरी पूर्ण झाली",
  "Attendance date": "हजेरीची तारीख",
  "Attendance status": "हजेरी स्थिती",
  "Attendance taken for today.": "आजची हजेरी नोंदवली आहे.",
  "Back (Village)": "मागील कॅमेरा (गाव)",
  "Camera permission not granted or camera in use. Please enable camera access or choose a photo below.": "कॅमेरा परवानगी मिळालेली नाही किंवा कॅमेरा इतरत्र वापरला जात आहे. कृपया कॅमेरा चालू करा किंवा खालील फोटो निवडा.",
  "Capture your NoteCam photo with GPS & village stamp to mark attendance.": "हजेरी नोंदवण्यासाठी GPS आणि गावाच्या माहितीसह तुमचा नोटकॅम फोटो काढा.",
  "Change Role": "भूमिका बदला",
  "Check-in & Photo": "चेक-इन आणि फोटो",
  "Check-out & Photo": "चेक-आउट आणि फोटो",
  "Checked In at": "चेक-इन वेळ:",
  "Choose Photo": "फोटो निवडा",
  "Completed visits": "पूर्ण झालेल्या भेटी",
  "Completion rate": "पूर्णता दर",
  "Could not acquire GPS location.": "GPS स्थान मिळवता आले नाही.",
  "Could not obtain GPS location.": "GPS स्थान उपलब्ध झाले नाही.",
  "Could not start microphone. Please check permissions.": "मायक्रोफोन सुरू करता आला नाही. कृपया परवानगी तपासा.",
  "Daily Activity Report Details": "दैनिक उपक्रम अहवाल तपशील",
  "Daily check-in and check-out tracking with NoteCam GPS photos.": "नोटकॅम GPS फोटोसह रोजचे चेक-इन आणि चेक-आउट ट्रॅकिंग.",
  "Daily register": "दैनिक हजेरी नोंदवही",
  "Default targets updated successfully.": "डीफॉल्ट उद्दिष्टे यशस्वीरीत्या अद्यतनित झाली.",
  "Delete Report": "अहवाल हटवा",
  "Error stamping NoteCam photo.": "नोटकॅम फोटोवर माहिती नोंदवताना त्रुटी आली.",
  "Events conducted": "आयोजित केलेले कार्यक्रम",
  "Export to Excel": "एक्सेलमध्ये डाउनलोड करा",
  "Failed to apply default targets.": "डीफॉल्ट उद्दिष्टे लागू करता आली नाहीत.",
  "Failed to process photo.": "फोटोवर प्रक्रिया अयशस्वी झाली.",
  "Failed to record attendance.": "हजेरी नोंदवणे अयशस्वी झाले.",
  "Failed to save default targets.": "डीफॉल्ट उद्दिष्टे जतन करता आली नाहीत.",
  "Field team · multiple village assignment · performance · report submission": "क्षेत्रीय कार्यसंघ · अनेक गावांची नेमणूक · कामगिरी · अहवाल सादर करणे",
  "Front (Selfie)": "पुढील कॅमेरा (सेल्फी)",
  "GPS locating…": "GPS स्थान शोधत आहे…",
  "GPS unavailable": "GPS उपलब्ध नाही",
  "Girls Present": "उपस्थित मुली",
  "Groups Met": "भेट दिलेले गट",
  "Home": "मुख्यपृष्ठ",
  "Home Visits": "घरभेटी",
  "In": "आत (चेक-इन)",
  "Live camera stream not supported by this browser. Use photo upload below.": "या ब्राउझरमध्ये थेट कॅमेरा चालू होत नाही. कृपया खालील फोटो अपलोड पर्याय वापरा.",
  "Manage targets →": "उद्दिष्टे व्यवस्थापित करा →",
  "Microphone permission denied. Please allow microphone access.": "मायक्रोफोनची परवानगी नाकारली आहे. कृपया ब्राउझरमध्ये मायक्रोफोन चालू करा.",
  "More": "अधिक मेनू",
  "No active Tais found.": "कोणतीही सक्रिय ताई आढळली नाही.",
  "No active targets running. Set targets under Targets.": "सध्या कोणतेही सक्रिय उद्दिष्ट नाही. 'उद्दिष्टे' विभागात जाऊन उद्दिष्टे निश्चित करा.",
  "No planned or completed activities were found for this period.": "या कालावधीसाठी कोणतेही नियोजित किंवा पूर्ण उपक्रम आढळले नाहीत.",
  "Optional": "ऐच्छिक",
  "Other Meetings & Info": "इतर बैठका व माहिती",
  "Out": "बाहेर (चेक-आउट)",
  "Overall completion": "एकूण पूर्णता",
  "Pick a volunteer and village first.": "प्रथम ताई आणि गाव निवडा.",
  "Planned events": "नियोजित कार्यक्रम",
  "Planned visits": "नियोजित भेटी",
  "Planned vs actual activity": "नियोजित वि. प्रत्यक्ष उपक्रम",
  "Please take a NoteCam photo before submitting.": "कृपया हजेरी पाठवण्यापूर्वी नोटकॅम फोटो काढा.",
  "Recorded": "नोंदवलेले",
  "Recording… Pauses will not stop typing. Hit Stop when done.": "आवाज रेकॉर्ड होत आहे… बोलणे थांबवले तरी टायपिंग थांबणार नाही. बोलून झाल्यावर 'थांबवा' दाबा.",
  "Refresh GPS location": "GPS स्थान पुन्हा मिळवा",
  "Remarks (optional)": "शेरा (ऐच्छिक)",
  "Retry Camera": "कॅमेरा पुन्हा सुरू करा",
  "Review Remarks": "तपासणी शेरा",
  "Review Status": "तपासणी स्थिती",
  "Roles: Stakeholder (complete oversight), Admin (management), and Tai (field operations)": "भूमिका: भागधारक (संपूर्ण देखरेख), प्रशासक (व्यवस्थापन), आणि ताई (क्षेत्रीय कार्य)",
  "Saving…": "जतन होत आहे…",
  "Select Village for Attendance *": "हजेरीसाठी गाव निवडा *",
  "Select village for this report": "या अहवालासाठी गाव निवडा",
  "Socio-Economic Development Trust (SEDT)": "सोशियो-इकॉनॉमिक डेव्हलपमेंट ट्रस्ट (SEDT)",
  "Stakeholder Oversight Monitor": "भागधारक देखरेख कक्ष",
  "Stakeholder — complete oversight over admins and tais": "भागधारक — प्रशासक आणि ताई यांच्यावर संपूर्ण देखरेख",
  "Stakeholders": "भागधारक",
  "Start Voice Typing (English)": "इंग्रजीत बोलून टाईप करा",
  "Start Voice Typing (Marathi)": "मराठीत बोलून टाईप करा",
  "Starting camera…": "कॅमेरा सुरू होत आहे…",
  "Stop Voice Typing": "व्हॉइस टायपिंग थांबवा",
  "Successfully assigned/updated {n} target(s).": "{n} उद्दिष्टे यशस्वीरीत्या नेमली/अद्यतनित केली.",
  "Switch front/back camera": "पुढील/मागील कॅमेरा बदला",
  "Switch voice typing language": "बोलण्याची भाषा बदला",
  "Tai (Volunteer)": "ताई (स्वयंसेवक)",
  "Tai *": "ताई *",
  "Tai field activities, visits, follow-ups and targets.": "ताईंचे क्षेत्रीय उपक्रम, भेटी, पाठपुरावा आणि उद्दिष्टे.",
  "Tai target achievement (current active targets)": "ताईंची उद्दिष्टपूर्ती (सध्या चालू उद्दिष्टे)",
  "Tai — field worker (multi-village)": "ताई — क्षेत्रीय कार्यकर्त्या (अनेक गावे)",
  "Tais (Volunteers)": "ताई (स्वयंसेवक)",
  "Take Photo": "फोटो काढा",
  "Targets apply to the Tai’s assigned villages.": "उद्दिष्टे ताईला नेमून दिलेल्या गावांना लागू होतात.",
  "Targets can only be created or revised by an Admin or Stakeholder.": "उद्दिष्टे केवळ प्रशासक किंवा भागधारक तयार करू शकतात किंवा बदलू शकतात.",
  "Topics Discussed": "चर्चा केलेले विषय",
  "Total Tais": "एकूण ताई",
  "Total Users": "एकूण वापरकर्ते",
  "Update Role": "भूमिका अद्यतन करा",
  "Upload / Gallery": "गॅलरीतून फोटो निवडा",
  "View": "पहा",
  "Village coordinates have not been added yet. GPS-tagged visits will appear on this map when available.": "गावाचे भौगोलिक स्थान अद्याप जोडलेले नाही. GPS नोंदी उपलब्ध झाल्यावर या नकाशावर दिसतील.",
  "Village events, attendance and post-event reporting": "गावातील कार्यक्रम, उपस्थिती आणि कार्यक्रमानंतरचा अहवाल",
  "Village for Tai": "ताईसाठी गाव",
  "Voice input is not supported in this browser. Please use Chrome on Android or desktop.": "या ब्राउझरमध्ये व्हॉइस इनपुट चालत नाही. कृपया Android किंवा कॉम्प्युटरवर Chrome वापरा.",
  "Volunteer & Stakeholder Registration": "स्वयंसेवक व भागधारक नोंदणी",
  "You have already checked out today. Daily attendance is taken only once.": "तुम्ही आज आधीच चेक-आउट केले आहे. दिवसातून एकदाच हजेरी घेतली जाते.",
  "Your account is active, but no village is assigned yet. Contact your Stakeholder / Admin to receive an assignment before recording field work.": "तुमचे खाते सक्रिय आहे, परंतु अद्याप कोणतेही गाव नेमलेले नाही. क्षेत्रीय काम नोंदवण्यापूर्वी गावाची नेमणूक करून घेण्यासाठी आपल्या प्रशासकांशी संपर्क साधा.",
  "e.g. Starting field visits in Ward 2": "उदा. वॉर्ड क्रमांक २ मध्ये घरभेटी सुरू केल्या",
  "{n} Tai(s)": "{n} ताई",
  "{n} villages assigned": "{n} गावे नेमलेली आहेत",
  "Needy Girls": "गरजू मुली",
  "Needy girls": "गरजू मुली",
  "needy_girls": "गरजू मुली",
  "KVP Volunteer Activity Report": "KVP स्वयंसेवक उपक्रम अहवाल",
  "Default Tai Targets (Admin Configurable)": "डीफॉल्ट ताई उद्दिष्टे (प्रशासक बदलू शकतात)",
  "Weekly Visits Target (per Tai)": "साप्ताहिक भेटींचे उद्दिष्ट (प्रत्येक ताई)",
  "Monthly Visits Target (per Tai)": "मासिक भेटींचे उद्दिष्ट (प्रत्येक ताई)",
  "Save Defaults": "डीफॉल्ट जतन करा",
  "Apply Defaults to All Tais": "सर्व ताईंना डीफॉल्ट लागू करा"
};

// Parse existing dict
const lines = content.split('\n');
const existing = {};
for (const line of lines) {
  const m = line.match(/^\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/);
  if (m) {
    const k = m[1].replace(/\\"/g, '"');
    const v = m[2].replace(/\\"/g, '"');
    existing[k] = v;
  }
}

// Merge newTranslations
for (const [k, v] of Object.entries(newTranslations)) {
  existing[k] = v;
}

// Rebuild sorted mr.js
const sortedKeys = Object.keys(existing).sort();
let out = '/** Marathi UI strings, keyed by the English text used in the code. Missing keys fall back to English. */\nexport default {\n';
for (const k of sortedKeys) {
  const safeK = k.replace(/"/g, '\\"');
  const safeV = existing[k].replace(/"/g, '\\"');
  out += `  "${safeK}": "${safeV}",\n`;
}
out += '}\n';

fs.writeFileSync(mrFile, out, 'utf8');
console.log('Successfully updated mr.js with', sortedKeys.length, 'keys');
