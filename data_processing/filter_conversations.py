from datasets import load_dataset
import pandas as pd

print("Loading dataset...")
dataset = load_dataset("ruslanmv/ai-medical-chatbot", split="train")
df = dataset.to_pandas()

STD_KEYWORDS = [
    'chlamydia', 'gonorrhea', 'gonorrhoea', 'syphilis',
    'HIV', 'herpes', 'HPV', 'genital warts', 'STD', 'STI',
    'sexually transmitted', 'trichomoniasis', 'discharge',
    'urethritis', 'cervicitis', 'PrEP', 'antiretroviral'
]

pattern = '|'.join(STD_KEYWORDS)
std_df = df[df['Description'].str.contains(pattern, case=False, na=False)]

print(f"Found {len(std_df)} STD-relevant conversations out of {len(df)}")

std_df[['Description', 'Doctor']].to_csv('../data/std_conversations.csv', index=False)
print("Saved to data/std_conversations.csv")
