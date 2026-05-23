import hashlib
import sys

def generate_key(email):
    """
    Generates a local offline activation key for Alpha Hub Pro.
    Matches the validation logic inside app.js.
    """
    email = email.strip().upper()
    salt = "haowu999-quant-secret-salt-2026"
    data = f"AH-PRO-{email}-{salt}"
    h = hashlib.sha256(data.encode()).hexdigest().upper()
    return f"AH-PRO-{email}-{h[:8]}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_key.py <user_email>")
        print("Example: python3 generate_key.py customer@example.com")
    else:
        email = sys.argv[1]
        key = generate_key(email)
        print(f"\nSuccessfully generated license key for: {email}")
        print("-" * 50)
        print(f"Key: {key}")
        print("-" * 50)
        print("Provide this key to the customer. They can enter it under Settings -> Pro License to unlock Pro features.")
