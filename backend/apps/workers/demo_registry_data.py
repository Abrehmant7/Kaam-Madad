"""FICTIONAL demo identity registry (demo deployments only).

The people and addresses are invented and the identifiers are synthetic: they all start with
00000, which no issued CNIC uses. Matching sample cards (marked "DEMO") are in docs/demo/cnic/.
Never add real data here.
"""

DEMO_RECORDS = [
    {
        "reference": "DEMO-REG-0001", "cnic": "0000012345671", "full_name_en": "Bilal Ahmed",
        "full_name_ur": "بلال احمد", "demo_address": "House 12, Street 4, Demo Town, Islamabad",
    },
    {
        "reference": "DEMO-REG-0002", "cnic": "0000076543212", "full_name_en": "Sana Tariq",
        "full_name_ur": "ثنا طارق", "demo_address": "Flat 3, Block B, Sample Colony, Rawalpindi",
    },
    {
        "reference": "DEMO-REG-0003", "cnic": "0000024681353", "full_name_en": "Imran Siddiqui",
        "full_name_ur": "عمران صدیقی", "demo_address": "Plot 7, Test Road, Example Sector, Islamabad",
    },
]

# Synthetic numbers on the rehearsal cards that are deliberately NOT a match:
# demo-card-unknown-number.png carries 00000-9999999-9 (no record);
# demo-card-wrong-name.png carries Bilal Ahmed's number with the name "Kamran Shah" (name mismatch).
UNKNOWN_NUMBER_SAMPLE = "0000099999999"
