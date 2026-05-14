import sqlite3
import os

db_path = "local_pm_tool.db"

def inspect_db():
    abs_db_path = os.path.abspath(db_path)
    print(f"Checking database at: {abs_db_path}")
    
    if not os.path.exists(abs_db_path):
        print(f"Database {abs_db_path} not found.")
        return

    conn = sqlite3.connect(abs_db_path)
    cursor = conn.cursor()

    try:
        print("\n--- Recent Audit Logs ---")
        cursor.execute("SELECT created_at, event_type, category, description FROM audit_logs ORDER BY created_at DESC LIMIT 10")
        for row in cursor.fetchall():
            print(row)
            
        print("\n--- Tasks (baseline_schedule) Statuses ---")
        cursor.execute("SELECT DISTINCT status FROM baseline_schedule")
        print(cursor.fetchall())

        print("\n--- Task Outputs Doc Types ---")
        cursor.execute("SELECT DISTINCT doc_type FROM task_outputs")
        print(cursor.fetchall())

        print("\n--- Sample recent Task Outputs ---")
        cursor.execute("SELECT activity_id, file_name, doc_type, uploaded_at FROM task_outputs ORDER BY uploaded_at DESC LIMIT 5")
        for row in cursor.fetchall():
            print(row)

        print("\n--- Status of those Activities ---")
        # Try to find recent ones specifically
        cursor.execute("""
            SELECT b.activity_id, b.activity_name, b.status 
            FROM baseline_schedule b
            JOIN task_outputs t ON b.activity_id = t.activity_id
            ORDER BY t.uploaded_at DESC LIMIT 5
        """)
        for row in cursor.fetchall():
            print(row)
            
    except Exception as e:
        print(f"Error querying DB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_db()
