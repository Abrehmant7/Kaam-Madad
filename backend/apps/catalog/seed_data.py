"""Initial catalog content loaded by ``python manage.py seed_catalog``.

Records are matched by stable ``code``. Areas are SAMPLE catalog areas for the
Islamabad/Rawalpindi pilot — they are not claims that any worker covers them,
and coverage is not limited to this list (staff add areas/cities in the admin).
Area centre coordinates are intentionally left empty until verified.
"""

TRADES = [
    {"code": "electrician", "label_en": "Electrician", "label_ur": "الیکٹریشن", "icon": "zap", "sort_order": 10},
    {"code": "plumber", "label_en": "Plumber", "label_ur": "پلمبر", "icon": "wrench", "sort_order": 20},
    {"code": "ac_technician", "label_en": "AC technician", "label_ur": "اے سی ٹیکنیشن", "icon": "snowflake", "sort_order": 30},
]

SERVICE_TAGS = {
    "electrician": [
        ("elec_wiring_repair", "Wiring repair", "وائرنگ کی مرمت", "cable"),
        ("elec_new_wiring", "New wiring", "نئی وائرنگ", "hammer"),
        ("elec_fan_install", "Ceiling fan installation", "چھت کے پنکھے کی تنصیب", "fan"),
        ("elec_fan_repair", "Fan repair", "پنکھے کی مرمت", "fan"),
        ("elec_switch_socket", "Switch and socket repair", "سوئچ اور ساکٹ کی مرمت", "plug"),
        ("elec_light_fitting", "Light fitting", "لائٹ کی فٹنگ", "lightbulb"),
        ("elec_ups_inverter", "UPS / inverter installation", "یو پی ایس / انورٹر کی تنصیب", "battery"),
        ("elec_breaker_board", "Breaker and distribution board repair", "بریکر اور ڈسٹری بیوشن بورڈ کی مرمت", "toggle"),
    ],
    "plumber": [
        ("plmb_leak_repair", "Leak repair", "لیکیج کی مرمت", "droplet"),
        ("plmb_tap_shower", "Tap and shower installation", "نل اور شاور کی تنصیب", "shower"),
        ("plmb_drain_unblock", "Drain unblocking", "بند نالی کھولنا", "waves"),
        ("plmb_water_tank", "Water tank installation and cleaning", "پانی کی ٹینکی کی تنصیب اور صفائی", "cylinder"),
        ("plmb_motor_pump", "Water motor / pump repair", "پانی کی موٹر کی مرمت", "cog"),
        ("plmb_geyser", "Geyser installation and repair", "گیزر کی تنصیب اور مرمت", "flame"),
        ("plmb_bathroom_fittings", "Bathroom fittings (commode, basin)", "باتھ روم فٹنگز (کموڈ، واش بیسن)", "bath"),
        ("plmb_pipe_replacement", "Pipe replacement", "پائپ کی تبدیلی", "wrench"),
    ],
    "ac_technician": [
        ("ac_installation", "Split AC installation", "اسپلٹ اے سی کی تنصیب", "snowflake"),
        ("ac_removal_shifting", "AC removal and shifting", "اے سی اتارنا اور منتقل کرنا", "truck"),
        ("ac_service_cleaning", "AC service and cleaning", "اے سی کی سروس اور صفائی", "spray"),
        ("ac_gas_refill", "Gas refilling", "گیس ری فلنگ", "gauge"),
        ("ac_cooling_inspection", "Inspection: AC not cooling", "معائنہ: اے سی ٹھنڈک نہیں کر رہا", "thermometer"),
        ("ac_pcb_repair", "Circuit board (PCB) repair", "سرکٹ بورڈ (پی سی بی) کی مرمت", "circuit_board"),
        ("ac_window_service", "Window AC service", "ونڈو اے سی کی سروس", "wind"),
    ],
}

CITIES = [
    {"code": "islamabad", "label_en": "Islamabad", "label_ur": "اسلام آباد", "sort_order": 10},
    {"code": "rawalpindi", "label_en": "Rawalpindi", "label_ur": "راولپنڈی", "sort_order": 20},
]

# (code, English, Urdu, kind)
AREAS = {
    "islamabad": [
        ("isb-f-6", "F-6", "ایف-6", "sector"),
        ("isb-f-7", "F-7", "ایف-7", "sector"),
        ("isb-f-8", "F-8", "ایف-8", "sector"),
        ("isb-g-6", "G-6", "جی-6", "sector"),
        ("isb-g-9", "G-9", "جی-9", "sector"),
        ("isb-g-10", "G-10", "جی-10", "sector"),
        ("isb-g-11", "G-11", "جی-11", "sector"),
        ("isb-i-8", "I-8", "آئی-8", "sector"),
        ("isb-e-11", "E-11", "ای-11", "sector"),
        ("isb-blue-area", "Blue Area", "بلیو ایریا", "locality"),
        ("isb-bani-gala", "Bani Gala", "بنی گالہ", "locality"),
    ],
    "rawalpindi": [
        ("rwp-saddar", "Saddar", "صدر", "locality"),
        ("rwp-satellite-town", "Satellite Town", "سیٹلائٹ ٹاؤن", "locality"),
        ("rwp-raja-bazaar", "Raja Bazaar", "راجہ بازار", "locality"),
        ("rwp-chaklala-scheme-3", "Chaklala Scheme III", "چکلالہ اسکیم 3", "locality"),
        ("rwp-westridge", "Westridge", "ویسٹرج", "locality"),
        ("rwp-peshawar-road", "Peshawar Road", "پشاور روڈ", "locality"),
        ("rwp-adiala-road", "Adiala Road", "اڈیالہ روڈ", "locality"),
        ("rwp-bahria-town", "Bahria Town", "بحریہ ٹاؤن", "locality"),
    ],
}

SPECIALITY_QUESTIONS = [
    {
        "code": "services_offered",
        "prompt_en": "Which {trade} services do you offer?",
        "prompt_ur": "آپ {trade} کی کون سی خدمات فراہم کرتے ہیں؟",
        "help_en": "Select every service you offer.",
        "help_ur": "جو خدمات آپ فراہم کرتے ہیں، وہ سب منتخب کریں۔",
        "choice_source": "trade_services",
        "min_selections": 1,
        "max_selections": None,
        "sort_order": 10,
    },
    {
        "code": "primary_specialities",
        "prompt_en": "Which of these are your main specialities?",
        "prompt_ur": "ان میں سے آپ کی خاص مہارت کون سی ہے؟",
        "help_en": "Choose 1 to 3 of the services you offer.",
        "help_ur": "اپنی فراہم کردہ خدمات میں سے 1 سے 3 منتخب کریں۔",
        "choice_source": "services_offered",
        "min_selections": 1,
        "max_selections": 3,
        "sort_order": 20,
    },
    {
        "code": "services_not_offered",
        "prompt_en": "Which services do you NOT offer?",
        "prompt_ur": "آپ کون سی خدمات فراہم نہیں کرتے؟",
        "help_en": "Jobs for these services will not be sent to you.",
        "help_ur": "ان خدمات کے کام آپ کو نہیں بھیجے جائیں گے۔",
        "choice_source": "trade_services",
        "min_selections": 0,
        "max_selections": None,
        "sort_order": 30,
    },
]
