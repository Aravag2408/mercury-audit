import pandas as pd
import json

# Load Synthea CSVs
patients = pd.read_csv('../synthea/output/csv/patients.csv')
conditions = pd.read_csv('../synthea/output/csv/conditions.csv')
medications = pd.read_csv('../synthea/output/csv/medications.csv')

# Synthea uses SNOMED-CT codes — filter by description keywords
# (Synthea models HIV; chlamydia/gonorrhea/syphilis/herpes modules are not included by default)
STD_SNOMED_CODES = [
    '86406008',   # HIV
    '235871004',  # Gonorrhea
    '76272004',   # Syphilis
    '33839006',   # Chlamydia
    '9861002',    # Herpes simplex
]
STD_KEYWORDS = [
    'HIV', 'immunodeficiency', 'chlamydia', 'gonorrhea',
    'gonorrhoea', 'syphilis', 'herpes', 'HPV', 'sexually transmitted'
]

keyword_pattern = '|'.join(STD_KEYWORDS)
code_match = conditions['CODE'].astype(str).isin(STD_SNOMED_CODES)
desc_match = conditions['DESCRIPTION'].str.contains(keyword_pattern, case=False, na=False)

std_conditions = conditions[code_match | desc_match]
std_patient_ids = std_conditions['PATIENT'].unique()
std_patients = patients[patients['Id'].isin(std_patient_ids)]

print(f"Found {len(std_patient_ids)} patients with STD conditions")

records = []
for _, patient in std_patients.iterrows():
    pid = patient['Id']
    pt_conditions = std_conditions[std_conditions['PATIENT'] == pid]
    pt_meds = medications[medications['PATIENT'] == pid]

    record = {
        "patient_id": f"AFIK-{str(pid)[:5].upper()}",
        "full_name": f"{patient['FIRST']} {patient['LAST']}",
        "dob": patient['BIRTHDATE'],
        "address": patient['ADDRESS'],
        "city": patient['CITY'],
        "diagnoses": pt_conditions['DESCRIPTION'].tolist(),
        "medications": pt_meds['DESCRIPTION'].tolist(),
        "hiv_status": "Positive" if any(
            str(c) == '86406008' or 'immunodeficiency' in str(d).lower()
            for c, d in zip(pt_conditions['CODE'], pt_conditions['DESCRIPTION'])
        ) else "Negative"
    }
    records.append(record)

output_path = '../data/patient_records.json'
with open(output_path, 'w') as f:
    json.dump(records, f, indent=2)

print(f"Generated {len(records)} STD patient records -> {output_path}")
