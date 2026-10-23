"""English rendering of the baseline survey (Master Data form), which was filled in Marathi.

Question labels and common answers are translated; any other free text is transliterated
to Latin script so the English view never shows Devanagari.
"""

import json
import re
from pathlib import Path

from app.utils.translit import to_latin

# Free-text answers from the survey, translated once (normalised Marathi text -> English).
SENTENCES: dict[str, str] = json.loads((Path(__file__).with_name("survey_translations.json")).read_text(encoding="utf-8"))

QUESTIONS = {
    "जात": "Caste",
    "प्रवर्ग": "Category",
    "कुटुंबात कोण कोण आहे": "Family members",
    "जमीन (एकर)": "Land (acres)",
    "इतर व्यवसाय  आहे का ?": "Other occupation?",
    "कोण कोणती पिके घेतली जातात": "Crops grown",
    "वार्षिक उत्पन्न": "Annual income",
    "शिकून काय व्हायचे आहे": "Career goal",
    "कोणते विषय आवडतात": "Favourite subjects",
    "कोणते विषय आवडत नाहीत": "Disliked subjects",
    "शिक्षणात /विषय समजण्यास काय अडचणी आहेत असे वाटते.": "Difficulties in studies",
    "अभ्यास रोज किती तास करता?": "Daily study hours",
    "अभ्यासाचे नियोजन केले आहे का?": "Has a study plan?",
    "अवांतर वाचन करता का?": "Reads beyond textbooks?",
    "अवांतर वाचन करत असाल तर महिन्याला किती पुस्तके वाचता?": "Books read per month",
    "एकूणच शिक्षणात तुम्ही कोणत्या स्तरात आहात": "Overall education level",
    "हिरव्या पाल्याभाज्याचा वापर करता का ?": "Eats green leafy vegetables?",
    "करत असाल तर": "If yes, source",
    "परसबाग आहे का?": "Has a kitchen garden?",
    "असेल तर कोणकोणत्या भाज्या आहेत?": "Vegetables in the garden",
    "दुधाचा वापर करता का ?": "Uses milk?",
    "दुध उपलबद्धता": "Milk source",
    "फळांचा वापर आहारात करता का": "Eats fruit?",
    "करत असाल तर किती वेळा": "If yes, how often",
    "कोणती फळे": "Which fruits",
    "तुमचे हिमोग्लोबीन (HB )माहित आहे का?": "Knows her haemoglobin (Hb)?",
    "हिमोग्लोबिन वाढीसाठी काय खाता?": "Eats for haemoglobin",
    "काजू /बदाम/ खारीक/खोबरे ई. ड्राय फ्रुट्स चा वापर करता का?": "Eats dry fruits?",
    "करत असल्यास कधी": "If yes, how often",
    "सोयाबीनचा आहारात वापर करता का ?": "Eats soybean?",
    "करत असाल तर कशाप्रकारे": "If yes, how",
    "सोयाबीन पासून कोणते पदार्थ तयार करता": "Soybean dishes made",
    "तुम्ही कोणकोणत्या तृणधान्यांचा आहारात वापर करता": "Cereals eaten",
    "कच्च्या स्वरुपात कोणत्या फळभाज्या खाता": "Vegetables eaten raw",
    "भाजी धुवून घेता का": "Washes vegetables?",
    "कधी घुवून घेता": "When washed",
    "रोजच्या जेवणात कोणत्या डाळी वापरता?": "Pulses in daily meals",
    "शिजवलेले अन्न पुन्हा शिजवता का ?": "Reheats cooked food?",
    "ज्वारी/गव्हाचे पीठ चाळून घेता का ?": "Sieves jowar/wheat flour?",
    "अन्न शिजवण्यासाठी कोणकोणती भांडी वापरता ?": "Cooking utensils",
    "मोड आणून कडधान्य खाता का ?": "Eats sprouted pulses?",
    "खात असल्यास कोणती": "If yes, which",
    "गेले वर्षभरात किती वेळेस आजारी पडलात?": "Times ill in the past year",
    "आजारपणावर कुटुंबातील  सर्व सदस्यांचा  मिळून किती खर्च झाला?": "Family spending on illness",
    "मासिक पाळी सुरु झाली  का?": "Menstruation started?",
    "सुरु झाली असेल तर पाळी दरम्यान काय वापरता?": "Uses during periods",
    "आहार कोणता घेता": "Diet",
    "बाहेर इतरकोठे सहलीसाठी/फिरण्यासाठी जाता का?": "Goes on trips/outings?",
    "बाहेर कोठे एकटे असताना भीती वाटते का?": "Afraid when alone outside?",
    "बचत करता का?": "Saves money?",
    "करत असाल तर कोठे?": "If yes, where",
    "ध्येय निश्चित केले आहे का?": "Has set a goal?",
    "शिक्षणाव्यतिरिक्त काय आवडते?": "Interests besides studies",
    "कुठले खेळ आवडतात?": "Favourite sports",
    "या आवडीसाठी संस्थेने प्रशिक्षण आयोजित केल्यास भाग घेणार का?": "Would join training for this interest?",
    "तुम्ही तुमच्या गावासाठी काय करू शकता": "What she can do for her village",
    "संस्थेकडून तुमच्या अपेक्षा काय आहेत?": "Expectations from the organisation",
    "सर्व्हेक्षण करणाऱ्या व्यक्तीचा शेरा (प्रश्नावली व्यतिरिक्त काही माहिती असेल तर किंवा अनाथ, एकपालक, घराची परिस्थिती बघून तुमचा शेरा लिहावा)": "Surveyor's remarks",
    "फॉर्म भरणाऱ्या व्यक्तीचे नाव": "Form filled by",
    "वडील नसतील तर": "If father is not alive",
    "आई /वडील नसतील तर कोणाकडे राहता?": "If parents are not alive, lives with",
}

# Common answers and list items (answers like "गहू, ज्वारी, तांदूळ" are translated item by item).
WORDS = {
    "होय": "Yes", "नाही": "No", "काही नाही": "Nothing", "कधीच नाही": "Never", "एक": "Once", "दोन": "Twice",
    "तीन": "Three times", "चार": "Four times", "दररोज": "Daily", "वर्षाला": "Yearly", "महिन्याला": "Monthly",
    "आठवड्याला": "Weekly", "विकत": "Bought", "घरचे": "Home", "बाजारात विकत घेऊन": "Bought at market",
    "स्वत:च्या शेतातील": "From own farm", "चहासाठी": "In tea", "जेवणात": "In meals", "पिण्यासाठी": "For drinking",
    "शाकाहार": "Vegetarian", "मांसाहार": "Non-vegetarian", "मिश्र आहार": "Mixed", "कपडा": "Cloth",
    "सॅनिटरी पॅड": "Sanitary pad", "बँक": "Bank", "बचत गट": "Self-help group", "इतरत्र": "Elsewhere",
    "चिरण्य आधी": "Before cutting", "चिरण्या आधी": "Before cutting", "चिरल्या नंतर": "After cutting",
    "गहू": "Wheat", "ज्वारी": "Jowar", "बाजरी": "Bajra", "तांदूळ": "Rice", "नाचणी": "Ragi",
    "तूर": "Toor", "मुग": "Moong", "उडीद": "Urad", "हरभरा": "Chana", "मसूर": "Masoor", "मटकी": "Matki",
    "स्टील": "Steel", "जर्मन": "Aluminium", "लोखंडी": "Iron", "मातीची": "Clay", "पितळी": "Brass",
    "टोमॅटो": "Tomato", "कांदा": "Onion", "काकडी": "Cucumber", "गाजर": "Carrot", "बीट": "Beetroot",
    "मुळा": "Radish", "कोबी": "Cabbage", "मेथी": "Fenugreek", "पालक": "Spinach",
    "खेळ": "Sports", "डान्स": "Dance", "कराटे": "Karate", "गायन": "Singing", "चित्रकला": "Drawing",
    "खो खो": "Kho-kho", "खोखो": "Kho-kho", "कबड्डी": "Kabaddi", "क्रिकेट": "Cricket",
    "गणित": "Maths", "मराठी": "Marathi", "इंग्रजी": "English", "इंग्लिश": "English", "हिंदी": "Hindi",
    "विज्ञान": "Science", "इतिहास": "History", "भूगोल": "Geography",
    "पोलीस": "Police", "पोलिस": "Police", "डॉक्टर": "Doctor", "शिक्षक": "Teacher", "शिक्षिका": "Teacher",
    "नर्स": "Nurse", "वकील": "Lawyer", "इंजिनिअर": "Engineer", "आर्मी": "Army",
    "स्वच्छता": "Cleanliness", "स्वच्छता करणे": "Keeping it clean", "झाडे लावणे": "Planting trees", "मदत": "Help",
    "शैक्षणिक मदत": "Educational help", "नवीन माहिती मिळणे": "New information",
    "कापूस": "Cotton", "सोयाबीन": "Soybean", "सोयाबीन कापूस": "Soybean, cotton", "कापूस सोयाबीन": "Cotton, soybean",
    "गुळ - शेंगदाणे": "Jaggery and groundnuts", "पेंडखजूर": "Dates", "अंजीर": "Figs",
    "भिजवून": "Soaked", "भाजून": "Roasted", "पीठ करून": "As flour", "न्युट्रीला": "Nutrela",
    "समजत नाही": "Does not understand", "विधवा": "Widow", "परीत्यक्ता": "Abandoned",
}


# Word by word, for list-style answers such as fruits, subjects, crops and land/income amounts.
TOKENS = {
    # fruits
    "आंबा": "mango", "आंबे": "mango", "आबा": "mango", "आमाब": "mango", "केळी": "banana", "केळे": "banana", "केळ": "banana",
    "केली": "banana", "केळि": "banana", "कैळि": "banana", "किळे": "banana", "कोळी": "banana", "🍌": "",
    "चिकू": "chikoo", "चिकु": "chikoo", "चिक्कू": "chikoo", "चीकु": "chikoo", "चुकू": "chikoo",
    "सफरचंद": "apple", "सफरचंदा": "apple", "सरफरचंद": "apple", "सपरचंद": "apple", "पेरू": "guava", "पेरु": "guava",
    "पपई": "papaya", "अंगूर": "grapes", "अंगुर": "grapes", "अगुर": "grapes", "द्राक्ष": "grapes", "द्राक्षे": "grapes",
    "संत्री": "orange", "संत्रे": "orange", "संत्रा": "orange", "मोसंबी": "sweet lime", "अननस": "pineapple",
    "टरबूज": "watermelon", "टरबुज": "watermelon", "जांभूळ": "jamun", "डाळिंब": "pomegranate", "फणस": "jackfruit",
    "बोरे": "ber", "बोरी": "ber", "लिंब": "lemon", "लिंबू": "lemon", "खरबूज": "muskmelon", "सीताफळ": "custard apple",
    "मोसमी": "seasonal", "मोसम": "seasonal", "असमी": "seasonal", "फळे": "fruits", "फळ": "fruit",
    "आठवडी": "weekly", "आठवडा": "weekly", "आठवडे": "weekly", "बाजारातील": "market", "बाजार": "market", "बाजारात": "market",
    # vegetables
    "मेथी": "fenugreek", "पालक": "spinach", "वांगी": "brinjal", "वांगे": "brinjal", "टोमॅटो": "tomato", "कांदा": "onion",
    "भेंडी": "okra", "कोथिंबीर": "coriander", "मिरची": "chilli", "बटाटा": "potato", "दोडके": "ridge gourd",
    "भोपळा": "pumpkin", "कारले": "bitter gourd", "शेपू": "dill", "चुका": "sorrel", "अंबाडी": "roselle",
    "काकडी": "cucumber", "गाजर": "carrot", "बीट": "beetroot", "मुळा": "radish", "कोबी": "cabbage", "फुलकोबी": "cauliflower",
    # subjects
    "मराठी": "Marathi", "मरठी": "Marathi", "इंग्रजी": "English", "इंग्लिश": "English", "अंग्रेजी": "English",
    "हिंदी": "Hindi", "गणित": "Maths", "मॅथ": "Maths", "विज्ञान": "Science", "सायन्स": "Science",
    "इतिहास": "History", "भूगोल": "Geography", "भुगोल": "Geography", "राज्यशास्त्र": "Civics", "नागरिकशास्त्र": "Civics",
    "चित्रकला": "Drawing", "संस्कृत": "Sanskrit", "ग्रामर": "grammar", "सर्व": "all", "विषय": "subjects",
    # crops
    "सोयाबीन": "soybean", "कापूस": "cotton", "तूर": "toor", "तुर": "toor", "गहू": "wheat", "ज्वारी": "jowar",
    "हरभरा": "chana", "ऊस": "sugarcane", "बाजरी": "bajra", "मूग": "moong", "मुग": "moong", "उडीद": "urad",
    "भुईमूग": "groundnut", "करडई": "safflower", "हळद": "turmeric", "मका": "maize", "तांदूळ": "rice",
    # sports / interests
    "खो": "kho", "खोखो": "kho-kho", "कबड्डी": "kabaddi", "क्रिकेट": "cricket", "धावणे": "running", "रनिंग": "running",
    "लंगडी": "langdi", "डान्स": "dance", "गायन": "singing", "कराटे": "karate", "बॅडमिंटन": "badminton",
    "व्हॉलीबॉल": "volleyball", "रांगोळी": "rangoli", "मेहंदी": "mehendi", "वाचन": "reading", "खेळ": "sports",
    # careers
    "पोलीस": "police", "पोलिस": "police", "डॉक्टर": "doctor", "शिक्षक": "teacher", "शिक्षिका": "teacher",
    "नर्स": "nurse", "वकील": "lawyer", "इंजिनिअर": "engineer", "आर्मी": "army", "अधिकारी": "officer",
    "ऑफिसर": "officer", "आयपीएस": "IPS", "आयएएस": "IAS", "कलेक्टर": "collector", "तलाठी": "talathi",
    # amounts / units
    "एकर": "acres", "एक्कर": "acres", "येकर": "acres", "गुंठे": "gunthas", "हजार": "thousand", "हाजार": "thousand",
    "लाख": "lakh", "रुपये": "rupees", "रू": "rupees", "मेंढ्या": "sheep",
    "एक": "one", "दोन": "two", "तीन": "three", "चार": "four", "पाच": "five", "सहा": "six", "सात": "seven",
    "आठ": "eight", "नऊ": "nine", "दहा": "ten", "अकरा": "eleven", "बारा": "twelve", "वीस": "twenty", "पन्नास": "fifty",
    "अर्धा": "half", "अडीच": "two and a half", "दीड": "one and a half",
    # connectors
    "आणि": "and", "व": "and", "इ": "etc.", "ई": "etc.", "नाही": "no", "नाहीत": "none", "P": "", "p": "",
}

UNITS = {"acres", "gunthas", "thousand", "lakh", "rupees", "sheep"}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\s.।,]+$", "", text)).strip()


def _by_words(text: str) -> str | None:
    words = [w for w in re.split(r"[\s,.\-]+", re.sub(r"(\d)([^\d\s,])", r" ", text)) if w]
    out = []
    for w in words:
        if w in TOKENS:
            out.append(TOKENS[w])
        elif re.fullmatch(r"[\d.]+|[A-Za-z]+", w):
            out.append(w)
        else:
            return None
    out = [w for w in out if w]
    if not out:
        return None
    joined = " ".join(out) if any(w in UNITS or w[0].isdigit() for w in out) else ", ".join(out)
    return joined[0].upper() + joined[1:]


def _answer(value) -> str:
    text = _normalise(str(value))
    if text in WORDS:
        return WORDS[text]
    parts = [p.strip() for p in text.split(",")]
    if len(parts) > 1 and all(p in WORDS for p in parts if p):
        return ", ".join(WORDS[p] for p in parts if p)
    if text in SENTENCES:
        return SENTENCES[text]
    return _by_words(text) or to_latin(text) or text


def survey_in_english(survey: dict) -> dict:
    """The survey with English question labels and English (or transliterated) answers."""
    return {QUESTIONS.get(q.strip(), to_latin(q) or q) if not q.startswith("_") else q: (_answer(a) if not q.startswith("_") else a)
            for q, a in survey.items()}
