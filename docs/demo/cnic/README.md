# Synthetic DEMO cards (not real CNICs)

Rehearsal images for the M4 identity check. Every person is fictional, and every number starts with `00000`,
which is never issued. Each card is visibly marked **DEMO**. The images carry no hidden data, so the OCR must
read the pixels.

| File | Printed name / number | Registry (`seed_demo_registry`) | Expected |
|---|---|---|---|
| `demo-card-bilal-ahmed.png` | Bilal Ahmed / 00000-1234567-1 | DEMO-REG-0001 | Match |
| `demo-card-sana-tariq.png` | Sana Tariq / 00000-7654321-2 | DEMO-REG-0002 | Match |
| `demo-card-imran-siddiqui.png` | Imran Siddiqui / 00000-2468135-3 | DEMO-REG-0003 | Match |
| `demo-card-wrong-name.png` | Kamran Shah / 00000-1234567-1 | number belongs to DEMO-REG-0001 | Name mismatch |
| `demo-card-unknown-number.png` | Usman Ali / 00000-9999999-9 | none | No record |
| `demo-card-sana-tariq-rotated.jpg` | sideways retake of Sana's card | DEMO-REG-0002 | Read after rotation → match |
| `demo-card-imran-siddiqui-lowquality.jpg` | small, blurred, low-contrast retake | DEMO-REG-0003 | Number only → type the name → match |
| `demo-card-unreadable.jpg` | heavily blurred | — | Unreadable → retake or type |

Run the real OCR on all of them (from `backend/`, venv active). In Windows `cmd`, pass the files one by one;
in bash you can loop over them:

```
python manage.py check_ai_providers --only cnic_ocr --cnic-image ..\docs\demo\cnic\demo-card-bilal-ahmed.png --cnic-image ..\docs\demo\cnic\demo-card-sana-tariq-rotated.jpg
```

The PNGs were rendered from an HTML template with headless Chrome. The JPEG variants were derived with Pillow
(rotation, downscaling, blur, contrast and JPEG quality).
