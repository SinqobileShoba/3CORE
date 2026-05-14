import requests
import json
import sqlite3

BASE_URL = "http://localhost:8000"
DB_PATH = "local_pm_tool.db"

def test_api():
    # 1. Login to get token
    login_data = {
        "username": "admin",
        "password": "password"
    }
    r = requests.post(f"{BASE_URL}/auth/login", data=login_data)
    if r.status_code != 200:
        print("Login failed", r.text)
        return
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get a task to test with
    r = requests.get(f"{BASE_URL}/tasks/project/1/", headers=headers)
    tasks = r.json()
    if not tasks:
        print("No tasks found")
        return
    
    test_task = tasks[0]
    task_id = test_task['activity_id']
    old_status = test_task['status']
    print(f"Testing Activity ID: {task_id}, Current Status: {old_status}")

    # 3. Simulate File Upload
    files = {'file': ('test.txt', b'hello world', 'text/plain')}
    url = f"{BASE_URL}/tasks/{task_id}/upload/?doc_type=Final Document"
    
    try:
        r = requests.post(url, headers=headers, files=files)
        print("Upload Response Status:", r.status_code)
        print("Upload Response JSON:", r.json())
    except Exception as e:
        print("Upload Request Error:", e)

    # 4. Check DB directly
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT status FROM baseline_schedule WHERE activity_id=?", (task_id,))
        db_status = c.fetchone()[0]
        print(f"Status in DB after upload: {db_status}")
        conn.close()
    except Exception as e:
        print("DB check failed:", e)

if __name__ == "__main__":
    test_api()
