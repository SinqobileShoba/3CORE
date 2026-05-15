import os
import sys

from app.core.bootstrap import bootstrap_db


def init_db():
    if not os.getenv("ADMIN_INITIAL_PASSWORD"):
        print(
            "ERROR: ADMIN_INITIAL_PASSWORD env var is required to bootstrap the admin user.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("Creating database tables...")
    bootstrap_db(create_admin=True)
    print("Database initialized.")


if __name__ == "__main__":
    init_db()
