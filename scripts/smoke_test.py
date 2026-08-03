import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fresh DB/vector store for this test run
for p in ["smartreco.db"]:
    if os.path.exists(p):
        os.remove(p)
import shutil
if os.path.exists("chroma_data"):
    shutil.rmtree("chroma_data")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def check(label, resp, expect=200):
    ok = resp.status_code == expect
    print(f"[{'OK' if ok else 'FAIL'}] {label} -> {resp.status_code} (expected {expect})")
    if not ok:
        print("    body:", resp.text[:300])
    return resp

# Health
check("health", client.get("/healthz"))

# Register admin (first user)
r = check("register admin", client.post("/auth/register", json={"email": "admin@test.com", "password": "admin123"}))
admin_token = r.json()["access_token"]
assert r.json()["user"]["role"] == "admin", "first registered user should be admin"

# Register normal user
r = check("register user", client.post("/auth/register", json={"email": "user@test.com", "password": "user1234"}))
user_token = r.json()["access_token"]
assert r.json()["user"]["role"] == "user"

# Duplicate registration should 400
check("duplicate register rejected", client.post("/auth/register", json={"email": "admin@test.com", "password": "admin123"}), expect=400)

# Login
r = check("login admin", client.post("/auth/token", data={"username": "admin@test.com", "password": "admin123"}))

# Bad login
check("bad password rejected", client.post("/auth/token", data={"username": "admin@test.com", "password": "wrong"}), expect=401)

# Pages render
check("homepage", client.get("/"))
check("login page", client.get("/login"))
check("dashboard page", client.get("/dashboard"))
check("admin page", client.get("/admin"))

# Products - empty list
r = check("list products (empty)", client.get("/products"))
assert r.json() == []

# Non-admin cannot create product
check("non-admin blocked from creating product", client.post(
    "/products",
    json={"title": "X", "description": "Y", "category": "Z", "price": 10, "level": "beginner"},
    headers={"Authorization": f"Bearer {user_token}"},
), expect=403)

# Admin CAN create product (vector dual-write will fail gracefully - no network to Mesh in this sandbox)
r = check("admin creates product", client.post(
    "/products",
    json={"title": "Test Course", "description": "A course about testing things thoroughly.", "category": "QA Automation", "price": 49, "level": "beginner"},
    headers={"Authorization": f"Bearer {admin_token}"},
))
product = r.json()
print("    vector_synced (expected False - no Mesh network access in sandbox):", product["vector_synced"])
product_id = product["id"]

# List products now has 1
r = check("list products (1 item)", client.get("/products"))
assert len(r.json()) == 1

# Product detail page renders
check("product detail page", client.get(f"/product/{product_id}"))

# Admin stats
r = check("admin stats", client.get("/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}))
print("    stats:", r.json())

# Non-admin blocked from stats
check("non-admin blocked from admin stats", client.get("/admin/stats", headers={"Authorization": f"Bearer {user_token}"}), expect=403)

# Event batch ingestion
r = check("event batch ingest", client.post(
    "/events/batch",
    json={"events": [{"event_type": "search", "query": "testing"}, {"event_type": "view", "product_id": product_id}]},
    headers={"Authorization": f"Bearer {user_token}"},
))
print("    ingested:", r.json())

# Unauthenticated event ingest blocked
check("unauthenticated event ingest blocked", client.post("/events/batch", json={"events": []}), expect=401)

# Recommendation endpoint - will attempt a Mesh call and fail since sandbox has no
# network route to api.meshapi.ai. We expect a 500 here in-sandbox; this will work
# once MESH_API_KEY is set and running somewhere with real network access.
r = client.get("/recommendations/me", headers={"Authorization": f"Bearer {user_token}"})
print(f"[INFO] recommendation endpoint -> {r.status_code} (500 expected in this sandbox due to no Mesh network access)")

print("\nSMOKE TEST COMPLETE")
