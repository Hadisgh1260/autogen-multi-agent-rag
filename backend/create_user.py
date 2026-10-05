import sys
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "users.db"


def hash_password(password: str):

    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()

    return password_hash, salt


def main():

    if len(sys.argv) != 3:

        print(
            "Usage:\n"
            "python backend/create_user.py "
            "USERNAME PASSWORD"
        )

        return

    username = sys.argv[1].strip()
    password = sys.argv[2]

    if not username or not password:

        print(
            "Username and password cannot be empty."
        )

        return

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            off_topic_count INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    password_hash, salt = hash_password(
        password
    )

    try:

        conn.execute(
            """
            INSERT INTO users (
                username,
                password_hash,
                password_salt,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                password_hash,
                salt,
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )

        conn.commit()

        print()
        print("User created successfully.")
        print(f"Username: {username}")
        print()

    except sqlite3.IntegrityError:

        print(
            f"User '{username}' already exists."
        )

    finally:

        conn.close()


if __name__ == "__main__":
    main()
