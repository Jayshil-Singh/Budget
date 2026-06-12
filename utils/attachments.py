"""Save receipt uploads per household."""
import os
import uuid


def save_receipt(household_id: int, uploaded_file) -> str:
    folder = os.path.join("receipts", str(household_id))
    os.makedirs(folder, exist_ok=True)
    safe_name = (uploaded_file.name or "receipt").replace("..", "").replace("/", "_")
    filename = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path
