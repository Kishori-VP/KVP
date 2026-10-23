"""English rendering of the baseline survey (Master Data form), which was filled in Marathi.

Question labels and common answers are translated; any other free text is transliterated
to Latin script so the English view never shows Devanagari.
"""

from app.utils.translit import to_latin

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


def _answer(value) -> str:
    text = str(value).strip()
    if text in WORDS:
        return WORDS[text]
    parts = [p.strip() for p in text.split(",")]
    if len(parts) > 1 and all(p in WORDS for p in parts if p):
        return ", ".join(WORDS[p] for p in parts if p)
    return to_latin(text) or text


def survey_in_english(survey: dict) -> dict:
    """The survey with English question labels and English (or transliterated) answers."""
    return {QUESTIONS.get(q.strip(), to_latin(q) or q) if not q.startswith("_") else q: (_answer(a) if not q.startswith("_") else a)
            for q, a in survey.items()}
