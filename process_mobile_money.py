import pandas as pd
import re
import os
import sys
import pathlib
from io import StringIO


# Phone numbers: 9-digit local (6XXXXXXXX) or 12-digit intl (237XXXXXXXXX)
PHONE_RE   = re.compile(r'\b(?:237)?\d{9,10}\b')

# Transaction IDs: e.g. MP250221.0930.C42749 or PP250222.0746.C35694
TRANS_ID   = re.compile(r'\b[A-Z]{2}\d{6}\.\d{4}\.[A-Z]\d+\b')

# All-caps name tokens (2+ words, each 2+ uppercase letters)
CAPS_NAME  = re.compile(r'\b([A-Z]{2,}(?:\s+[A-Z]{2,})+)\b')


def safe_path(user_input):
    p = user_input.strip()
    for ch in ('"', "'", '\u2018', '\u2019', '\u201c', '\u201d'):
        p = p.strip(ch)
    return str(pathlib.Path(p.strip()).resolve())

def output_name(uid):
    # user0001 → user0001.xls
    return f"{uid.lower()}.xls"

def anonymize_text(text, participant_name, uid):
    """
    Apply replacement rules in order:
      1. Participant name  → uid
      2. Transaction IDs   → ID_MASKED
      3. Phone numbers     → XXXX
      4. Other CAPS names  → Mr.X
    """
    if not isinstance(text, str):
        return text
    
    if participant_name:
        text = re.sub(re.escape(participant_name), uid, text, flags=re.IGNORECASE)

    text = TRANS_ID.sub('ID_MASKED', text)

    text = PHONE_RE.sub('XXXX', text)

    def replace_caps(m):
        if m.group(0).lower() == uid.lower():
            return m.group(0)
        return 'Mr.X'
    text = CAPS_NAME.sub(replace_caps, text)

    return text


def read_transaction_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        with open(path, 'r', encoding='utf-8-sig') as f:
            raw = f.readlines()
        header_idx = next(
            (i for i, l in enumerate(raw) if re.match(r'Date[,;]', l.strip())), 0
        )
        return pd.read_csv(StringIO(''.join(raw[header_idx:])))
    elif ext in ('.xlsx', '.xls'):
        raw_df = pd.read_excel(path, header=None, engine='openpyxl' if ext == '.xlsx' else 'xlrd')
        header_row = 0
        for i, row in raw_df.iterrows():
            if any(str(v).strip().lower() == 'date' for v in row if pd.notna(v)):
                header_row = i
                break
        return pd.read_excel(path, header=header_row,
                             engine='openpyxl' if ext == '.xlsx' else 'xlrd')
    else:
        raise ValueError(f"Unsupported file type: {ext}")



def process_transaction(path, participant_name, uid):
    df = read_transaction_file(path)
    df = df.dropna(how='all').reset_index(drop=True)
    print(f"  Transactions found : {len(df)}")

    contenu_col = next((c for c in df.columns if 'contenu' in c.lower() or 'content' in c.lower()), None)
    if contenu_col:
        df[contenu_col] = df[contenu_col].apply(
            lambda x: anonymize_text(x, participant_name, uid)
        )
    else:
        print("  WARNING: No Contenu/Content column found — nothing anonymized.")

    keep_patterns = ('date', 'heure', 'time', 'contact', 'contenu', 'content')
    keep_cols = [c for c in df.columns if any(p in c.lower() for p in keep_patterns)]
    df = df[keep_cols]

    out_dir  = os.path.dirname(path)
    out_file = os.path.join(out_dir, output_name(uid))
    df.to_excel(out_file, index=False, engine='openpyxl')
    print(f"  Saved as     : {os.path.basename(out_file)}")
    return out_file



def process_demographics(path):
    ext = os.path.splitext(path)[1].lower()
    engine = 'openpyxl' if ext == '.xlsx' else 'xlrd'
    df = pd.read_excel(path, engine=engine)
    df = df.dropna(how='all').reset_index(drop=True)
    print(f"  Participants found : {len(df)}")

    name_col = next(
        (c for c in df.columns if c.lower() in ('user', 'name', 'nom', 'participant')), None
    )
    if name_col is None:

        name_col = df.columns[0]
        print(f"  WARNING: No 'user/name' column found — using first column '{name_col}'")

    uid_map = {name: f"user{str(i+1).zfill(4)}" for i, name in enumerate(df[name_col].dropna().unique())}
    df[name_col] = df[name_col].map(uid_map).fillna(df[name_col])


    df = df.rename(columns={name_col: 'user'})


    drop_cols = [c for c in df.columns if any(
        k in c.lower() for k in ('education', 'income', 'revenu', 'salaire')
    )]
    df = df.drop(columns=drop_cols, errors='ignore')

    out_dir  = os.path.dirname(path)
    out_file = os.path.join(out_dir, 'demographic_anonym.xls')
    df.to_excel(out_file, index=False, engine='openpyxl')
    print(f"  Saved as     : demographic_anonym.xls")
    print(f"  User ID map  : {uid_map}")
    return out_file


def main():
    print("=" * 60)
    print("  MoMo Transaction Anonymizer  (v3)")
    print("  CSC 3221 | ICT University | Adrien Tello")
    print("=" * 60)

    print("\nWhat would you like to do?")
    print("  1 → Anonymize a transaction file  (e.g. Jerry_trans.xls)")
    print("  2 → Anonymize the demographics file")
    mode = input("  Choice [1/2]: ").strip()

    print("\nDrag & drop your file here (or type the path):")
    path = safe_path(input("  File: "))

    if not os.path.exists(path):
        print(f"\n  ERROR: File not found → {path}")
        sys.exit(1)

    ext = os.path.splitext(path)[1].lower()
    if ext not in ('.csv', '.xlsx', '.xls'):
        print(f"\n  ERROR: Unsupported extension '{ext}'. Use .csv, .xls or .xlsx")
        sys.exit(1)

    print()

    if mode == '2':
        out = process_demographics(path)
    else:
        print("Enter the participant's REAL NAME as it appears in the file (e.g. JERRY THE MOUSE):")
        participant_name = input("  Real name: ").strip()

        print("Enter the USER_ID to assign (e.g. user0001):")
        uid = input("  USER_ID: ").strip()
        if not uid:
            print("  ERROR: USER_ID cannot be empty.")
            sys.exit(1)

        out = process_transaction(path, participant_name, uid)

    print(f"\n  DONE! Output: {os.path.basename(out)}")
    print("  Run again for the next participant.\n")


if __name__ == "__main__":
    main()
