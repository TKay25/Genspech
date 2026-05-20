import os
os.environ["DATABASE_URL"] = "sqlite:///local_test.db"
import app as app_module

client = app_module.app.test_client()
r1 = client.post("/api/quote", json={"name": "Test User", "phone": "1234567890"})
r2 = client.post("/api/chatbot", json={"message": "generator for 2 days urgent", "name": "Test User", "phone": "1234567890"})
r3 = client.get("/admin?key=genspech-admin")

txt = r3.get_data(as_text=True)
print(f"quote_status={r1.status_code}")
print(f"chatbot_status={r2.status_code}")
print(f"admin_status={r3.status_code}")
print(f"admin_has_dashboard={'Genspech Quote Dashboard' in txt}")
print("quote_snippet=" + r1.get_data(as_text=True)[:200].replace("\n", " "))
print("chatbot_snippet=" + r2.get_data(as_text=True)[:200].replace("\n", " "))
print("admin_snippet=" + txt[:200].replace("\n", " "))
