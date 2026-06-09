import csv
import io
import datetime
import pandas as pd
from sqlalchemy.orm import Session as DBSession
from models.finance import BankTransaction, ExpenseCategory, Expense, Income
from config import EXPENSE_CATEGORIES

CATEGORIZATION_RULES = {
    "Rent/Mortgage": ["mortgage", "rent", "housing", "housing authority", "home loan"],
    "Utilities": ["power", "efl", "fiji electricity", "water", "wafa", "waste", "gas", "electricity"],
    "Internet": ["telecom", "tfl", "digicel", "vodafone", "ink", "unwired"],
    "Insurance": ["insurance", "bsplife", "lic fiji", "medical insurance", "car insurance"],
    "School Fees": ["school", "college", "university", "usp", "fnu", "fees"],
    "Childcare": ["daycare", "kindergarten", "nanny", "childcare"],
    "Transport": ["shell", "mobil", "totale", "total fuel", "bus fare", "taxi", "lubricants", "parking"],
    "Subscriptions": ["netflix", "spotify", "disney", "prime", "microsoft", "adobe", "apple.com", "icloud"],
    "Groceries": ["mh cc", "morris hedstrom", "shoprite", "rajendra", "supermarket", "groceries", "rb patel", "kundan singh"],
    "Dining Out": ["restaurant", "cafe", "mcdonalds", "kfc", "burger", "pizza", "coffee", "bakery"],
    "Entertainment": ["cinema", "damodar", "life cinema", "club", "bar", "concert", "sports", "event"],
    "Medical": ["pharmacy", "chemist", "clinic", "hospital", "doctor", "dentist"],
    "Loan Payments": ["personal loan", "loan payment", "credit card payment", "bsp loan", "anz loan"]
}

def guess_category_by_description(description: str, db: DBSession, household_id: int) -> int | None:
    """
    Scans the description against keywords to find the matching category ID.
    If none matches, returns the 'Other' category.
    """
    desc_lower = description.lower()
    
    # 1. Match against categorization rules
    matched_cat_name = "Other"
    for cat_name, keywords in CATEGORIZATION_RULES.items():
        if any(kw in desc_lower for kw in keywords):
            matched_cat_name = cat_name
            break
            
    # 2. Get DB Category
    # System category will have household_id == Null, or specific household
    cat = db.query(ExpenseCategory).filter(
        (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True),
        ExpenseCategory.name == matched_cat_name
    ).first()
    
    return cat.id if cat else None

def load_bank_csv_safely(text_data: str) -> pd.DataFrame | None:
    lines = text_data.splitlines()
    target_keywords = ["date", "details", "description", "withdrawal", "deposit", "amount", "debit", "credit", "particulars"]
    start_idx = 0
    for idx, line in enumerate(lines[:15]):
        line_lower = line.lower()
        if any(kw in line_lower for kw in target_keywords):
            if "," in line or ";" in line:
                start_idx = idx
                break
    
    clean_csv_data = "\n".join(lines[start_idx:])
    try:
        return pd.read_csv(io.StringIO(clean_csv_data))
    except Exception:
        return None

def parse_bank_csv(
    db: DBSession, 
    household_id: int, 
    bank_name: str, 
    file_contents: bytes
) -> tuple[int, int, int]:
    """
    Parses a CSV file based on the bank selected (ANZ, BSP, Westpac, HFC, Bred).
    Inserts bank transactions and attempts duplicate detection.
    Returns (imported_count, matched_count, duplicate_count)
    """
    # Decode contents
    try:
        text_data = file_contents.decode("utf-8")
    except UnicodeDecodeError:
        text_data = file_contents.decode("latin-1")
        
    df = load_bank_csv_safely(text_data)
    if df is None or df.empty:
        return 0, 0, 0
        
    imported = 0
    duplicates = 0
    matched = 0
    
    # Standardize columns based on bank selection
    # Columns we want to extract: Date, Description, Amount, Reference
    transactions_to_process = []
    
    bank_name = bank_name.upper()
    
    for _, row in df.iterrows():
        try:
            date_val = None
            desc_val = ""
            amount_val = 0.0
            ref_val = ""
            
            # Map row columns to standard terms
            row_dict = {str(k).strip().lower(): v for k, v in row.items()}
            
            if "ANZ" in bank_name:
                # ANZ CSV: Date, Details, Withdrawal, Deposit, Balance
                date_val = parse_date_flexible(row_dict.get("date", ""))
                desc_val = str(row_dict.get("details", ""))
                w_draw = parse_float_flexible(row_dict.get("withdrawal", 0.0))
                dep = parse_float_flexible(row_dict.get("deposit", 0.0))
                amount_val = dep if dep > 0 else -w_draw
                ref_val = str(row_dict.get("reference", ""))
                
            elif "BSP" in bank_name:
                # BSP CSV: Date, Description, Amount, Balance
                date_val = parse_date_flexible(row_dict.get("date", ""))
                desc_val = str(row_dict.get("description", ""))
                amount_val = parse_float_flexible(row_dict.get("amount", 0.0))
                ref_val = str(row_dict.get("reference", ""))
                
            elif "WESTPAC" in bank_name:
                # Westpac CSV: Date, Description, Debit, Credit, Balance
                date_val = parse_date_flexible(row_dict.get("date", ""))
                desc_val = str(row_dict.get("description", ""))
                dr = parse_float_flexible(row_dict.get("debit", 0.0))
                cr = parse_float_flexible(row_dict.get("credit", 0.0))
                amount_val = cr if cr > 0 else -dr
                ref_val = str(row_dict.get("reference", ""))
                
            elif "HFC" in bank_name:
                # HFC CSV: Date, Particulars, Debit, Credit, Balance
                date_val = parse_date_flexible(row_dict.get("date", ""))
                desc_val = str(row_dict.get("particulars", ""))
                dr = parse_float_flexible(row_dict.get("debit", 0.0))
                cr = parse_float_flexible(row_dict.get("credit", 0.0))
                amount_val = cr if cr > 0 else -dr
                ref_val = str(row_dict.get("reference", ""))
                
            elif "BRED" in bank_name or "GENERIC" in bank_name:
                # BRED / Generic: Date, Description, Amount, Reference
                date_val = parse_date_flexible(row_dict.get("date", ""))
                desc_val = str(row_dict.get("description", ""))
                amount_val = parse_float_flexible(row_dict.get("amount", 0.0))
                ref_val = str(row_dict.get("reference", ""))
                
            # If date and description and amount are valid, process
            if date_val and desc_val and amount_val != 0.0:
                transactions_to_process.append((date_val, desc_val, amount_val, ref_val))
        except Exception:
            # Skip rows that fail to parse
            continue
            
    # Process transactions in DB
    for date_val, desc_val, amount_val, ref_val in transactions_to_process:
        # 1. Check if identical record already exists in database
        # Match by date, amount, description, reference
        exists = db.query(BankTransaction).filter(
            BankTransaction.household_id == household_id,
            BankTransaction.transaction_date == date_val,
            BankTransaction.amount == amount_val,
            BankTransaction.description == desc_val
        ).first()
        
        if exists:
            duplicates += 1
            continue
            
        # 2. Categorize
        category_id = guess_category_by_description(desc_val, db, household_id)
        
        # 3. Create the BankTransaction
        tx = BankTransaction(
            household_id=household_id,
            account_bank=bank_name,
            transaction_date=date_val,
            amount=amount_val,
            description=desc_val,
            reference=ref_val,
            status="imported",
            category_id=category_id
        )
        db.add(tx)
        imported += 1
        
    db.commit()
    return imported, matched, duplicates

def parse_date_flexible(val) -> datetime.date | None:
    """
    Tries various standard formats to parse a cell as a date object.
    """
    if not val or pd.isna(val):
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None

def parse_float_flexible(val) -> float:
    """
    Tries to clean a cell value and parse it into a clean float.
    Handles currency symbols, commas, and parentheses for negative values.
    """
    if not val or pd.isna(val):
        return 0.0
    val_str = str(val).replace(",", "").replace("$", "").strip()
    
    # Handle accounting brackets: e.g. (120.00) -> -120.00
    if val_str.startswith("(") and val_str.endswith(")"):
        val_str = "-" + val_str[1:-1]
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def reconcile_transaction(db: DBSession, household_id: int, tx_id: int) -> bool:
    """
    Creates an actual Expense or Income record from an imported BankTransaction.
    """
    tx = db.query(BankTransaction).filter(
        BankTransaction.id == tx_id,
        BankTransaction.household_id == household_id
    ).first()
    
    if not tx or tx.status == "matched":
        return False
        
    # Reconcile as Expense or Income
    if tx.amount < 0:
        # Create Expense
        # Ensure category exists
        category_id = tx.category_id
        if not category_id:
            # Fallback to Other
            other_cat = db.query(ExpenseCategory).filter(
                (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True),
                ExpenseCategory.name == "Other"
            ).first()
            category_id = other_cat.id
            
        expense = Expense(
            household_id=household_id,
            category_id=category_id,
            amount=abs(tx.amount),
            date=tx.transaction_date,
            merchant=tx.description[:100],
            notes=f"Reconciled from bank statement. Ref: {tx.reference or ''}"
        )
        db.add(expense)
        db.commit()
        db.refresh(expense)
        
        tx.status = "matched"
        tx.matched_expense_id = expense.id
        
    else:
        # Create Income
        income = Income(
            household_id=household_id,
            source=tx.description[:100],
            amount=tx.amount,
            date=tx.transaction_date,
            description=f"Reconciled from bank statement. Ref: {tx.reference or ''}"
        )
        db.add(income)
        db.commit()
        db.refresh(income)
        
        tx.status = "matched"
        tx.matched_income_id = income.id
        
    db.commit()
    return True

def parse_sms_transaction_text(text: str) -> dict | None:
    """
    SMS Regex Patterns for M-PAiSA & MyCash.
    """
    import re
    text_clean = text.strip().replace("\n", " ")
    
    # 1. M-PAiSA payment made (Paid to ... of FJD ... on ...)
    # e.g., "Receipt No: 987654321. Paid to Vodafone Fiji of FJD 50.00 on 09/06/2026 13:45."
    # e.g., "Receipt No: 987654321. Paid to EFL of FJD 45.00 on 09/06/2026."
    m_paid_of_re = re.search(
        r"Paid\s+to\s+([^\s]+.*?)\s+of\s+(?:FJD|F\$)?\s*([\d\.]+)\s+on\s+([\d/-]+)", 
        text_clean, re.IGNORECASE
    )
    
    # 2. M-PAiSA payment standard (paid FJD ... to ... on ...)
    # e.g., "M-PAiSA: You have paid FJD 15.50 to MH Supermarket on 09/06/2026. Ref: 123456789."
    m_paid_re = re.search(
        r"(?:paid|sent)\s+(?:FJD|F\$)?\s*([\d\.]+)\s+to\s+([^on\s]+.*?)\s+on\s+([\d/-]+)", 
        text_clean, re.IGNORECASE
    )
    
    # 3. M-PAiSA receipt (received FJD ... from ... on ...)
    # e.g., "Receipt No: 456789012. You have received FJD 100.00 from John Doe on 09/06/2026 10:30."
    m_recv_re = re.search(
        r"received\s+(?:FJD|F\$)?\s*([\d\.]+)\s+from\s+([^on]+)\s+on\s+([\d/-]+)", 
        text_clean, re.IGNORECASE
    )
    
    amount = 0.0
    merchant = ""
    date_str = ""
    ref = ""
    is_income = False
    
    # Extract reference numbers
    ref_match = re.search(r"(?:Ref|Receipt No|TXN):\s*([A-Za-z0-9]+)", text_clean, re.IGNORECASE)
    if not ref_match:
        ref_match = re.search(r"(?:Receipt No|Ref|TXN)\s*([A-Za-z0-9]+)", text_clean, re.IGNORECASE)
    if ref_match:
        ref = ref_match.group(1)
        
    if m_paid_of_re:
        merchant = m_paid_of_re.group(1).strip()
        amount = -float(m_paid_of_re.group(2))
        date_str = m_paid_of_re.group(3).strip()
    elif m_paid_re:
        amount = -float(m_paid_re.group(1))
        merchant = m_paid_re.group(2).strip()
        date_str = m_paid_re.group(3).strip()
    elif m_recv_re:
        amount = float(m_recv_re.group(1))
        merchant = f"Deposit: {m_recv_re.group(2).strip()}"
        date_str = m_recv_re.group(3).strip()
        is_income = True
    else:
        return None
        
    parsed_date = None
    if date_str:
        for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                parsed_date = datetime.datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
    if not parsed_date:
        parsed_date = datetime.date.today()
        
    return {
        "amount": amount,
        "description": merchant,
        "transaction_date": parsed_date,
        "reference": ref,
        "is_income": is_income
    }

def import_sms_transaction(db: DBSession, household_id: int, sms_text: str) -> dict:
    """
    Parses a pasted M-PAiSA / MyCash transaction SMS and loads it into BankTransaction.
    """
    parsed = parse_sms_transaction_text(sms_text)
    if not parsed:
        return {"status": "error", "message": "Failed to parse SMS message format. Please check the text format."}
        
    date_val = parsed["transaction_date"]
    desc_val = parsed["description"]
    amount_val = parsed["amount"]
    ref_val = parsed["reference"]
    
    # Check if identical record already exists in database
    exists = db.query(BankTransaction).filter(
        BankTransaction.household_id == household_id,
        BankTransaction.transaction_date == date_val,
        BankTransaction.amount == amount_val,
        BankTransaction.description == desc_val
    ).first()
    
    if exists:
        return {"status": "warning", "message": f"Transaction already imported (Ref: {ref_val or 'N/A'})."}
        
    # Categorize
    category_id = guess_category_by_description(desc_val, db, household_id)
    
    # Create the BankTransaction
    tx = BankTransaction(
        household_id=household_id,
        account_bank="M-PAiSA / MyCash SMS",
        transaction_date=date_val,
        amount=amount_val,
        description=desc_val,
        reference=ref_val,
        status="imported",
        category_id=category_id
    )
    db.add(tx)
    db.commit()
    
    return {"status": "success", "message": f"Successfully parsed: {desc_val} of FJD {abs(amount_val):.2f} (Ref: {ref_val or 'N/A'})."}

