"""Fixed onboarding instructions that can be played aloud (UX-03).

The client asks for an instruction by KEY; the server owns the text, so nothing the user
typed (passwords, codes, CNIC numbers) can ever reach the speech provider through this path.
The same sentences are shown on screen (frontend i18n keys ``instructions.<key>``; a test keeps
the Urdu text identical). Audio is synthesised once per key/language/voice and cached.
"""

INSTRUCTIONS: dict[str, dict[str, str]] = {
    "signup_password": {
        "ur": "اپنا پاس ورڈ یاد رکھیں اور کسی کے ساتھ شیئر نہ کریں۔",
        "en": "Remember your password and do not share it with anyone.",
    },
    "onboarding_work": {
        "ur": "اپنا کام چنیں۔ پھر وہ خدمات چنیں جو آپ کرتے ہیں، اور ان میں سے اپنی خاص مہارت پر نشان لگائیں۔",
        "en": "Choose your trade. Then choose the services you offer, and mark your main speciality among them.",
    },
    "onboarding_areas": {
        "ur": "اپنا شہر چنیں، پھر وہ علاقے چنیں جہاں آپ کام کے لیے جا سکتے ہیں۔",
        "en": "Choose your city, then the areas you are willing to travel to for jobs.",
    },
    "identity_consent": {
        "ur": "کام لینے کے لیے اپنی شناخت کی تصدیق کریں۔ شناختی کارڈ کے سامنے والے حصے کی تصویر لیں، نام اور نمبر چیک کریں، پھر جمع کریں۔",
        "en": "Verify your identity to take jobs. Take a photo of the front of your identity card, check the name and number, then submit.",
    },
}
