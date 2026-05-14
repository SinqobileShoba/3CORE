import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "local_pm_tool.db")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Applying database migrations...")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    print("Added email column to users table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("email column already exists in users table")
    else:
        raise

try:
    cursor.execute(
        "ALTER TABLE baseline_schedule ADD COLUMN unit_of_measure TEXT DEFAULT 'units'"
    )
    print("Added unit_of_measure column to baseline_schedule table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("unit_of_measure column already exists in baseline_schedule table")
    else:
        raise

try:
    cursor.execute(
        "ALTER TABLE baseline_schedule ADD COLUMN total_quantity REAL DEFAULT 0.0"
    )
    print("Added total_quantity column to baseline_schedule table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("total_quantity column already exists in baseline_schedule table")
    else:
        raise

try:
    cursor.execute(
        "ALTER TABLE baseline_schedule ADD COLUMN completed_quantity REAL DEFAULT 0.0"
    )
    print("Added completed_quantity column to baseline_schedule table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("completed_quantity column already exists in baseline_schedule table")
    else:
        raise

cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_progress (
        progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL,
        quantity REAL NOT NULL,
        progress_date DATE NOT NULL,
        notes TEXT,
        recorded_by INTEGER,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (activity_id) REFERENCES baseline_schedule(activity_id),
        FOREIGN KEY (recorded_by) REFERENCES users(user_id)
    )
""")
print("Created daily_progress table")

conn.commit()
conn.close()
print("Migration completed successfully!")
