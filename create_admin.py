from database import init_db, get_db
from werkzeug.security import generate_password_hash
import getpass

init_db()
print("Create your GHARMATE developer/admin account")
name = input("Your full name: ").strip()
username = input("Username: ").strip()
password = getpass.getpass("Password (minimum 8 characters): ")
if not name or not username or len(password) < 8:
    raise SystemExit("Name and username are required; password must be at least 8 characters.")
with get_db() as db:
    try:
        db.execute("INSERT INTO users(name,username,password_hash,role) VALUES(?,?,?,'admin')",
                   (name, username, generate_password_hash(password)))
    except Exception as exc:
        raise SystemExit(f"Could not create admin (username may already exist): {exc}")
print("Admin account created. Start GHARMATE with: python app.py")
