"""
End-to-End Verification script for Phase 2: Project Management APIs.
Runs against the live running server at http://localhost:8000.
"""
import sys
import requests

BASE_URL = "http://localhost:8000/api"

def run_verification():
    session = requests.Session()

    print("\n--- 1. Login with seeded test developer account ---")
    login_resp = session.post(
        f"{BASE_URL}/auth/login",
        json={
            "login_id": "developer@example.com",
            "password": "DeveloperDefault123!",
            "website": "",
            "phone_confirm": "",
        },
    )
    if login_resp.status_code != 200:
        # Try registering or using admin
        print(f"Login developer failed: {login_resp.status_code} {login_resp.text}")
        login_resp = session.post(
            f"{BASE_URL}/auth/login",
            json={
                "login_id": "admin@devnest.local",
                "password": "Password123!",
                "website": "",
                "phone_confirm": "",
            },
        )
    assert login_resp.status_code == 200, f"Failed to login: {login_resp.text}"
    user_info = login_resp.json()["data"]["user"]
    print(f"Logged in as: {user_info['email']} ({user_info['role']})")

    print("\n--- 2. Create Project (Section 2.2) ---")
    create_resp = session.post(
        f"{BASE_URL}/projects",
        json={
            "name": "Cloud Native FinTech",
            "description": "High-throughput microservices architecture.",
            "status": "In Progress",
            "order_index": 1,
            "color": "#6366F1",
            "icon": "server",
            "settings": {
                "default_sql_dialect": "postgresql",
                "auto_save_interval_ms": 2000,
            },
        },
    )
    assert create_resp.status_code == 201, f"Create project failed: {create_resp.text}"
    project = create_resp.json()["data"]
    p_id = project["id"]
    p_code = project["project_code"]
    p_slug = project["slug"]
    print(f"Project created: ID={p_id}, Code={p_code}, Slug={p_slug}, Status={project['status']}")
    assert len(p_code) == 20, f"Expected 20-char project_code, got {len(p_code)}"

    print("\n--- 3. List User Projects (Section 2.1) ---")
    list_resp = session.get(f"{BASE_URL}/projects?status=all&sort_by=order&order_dir=asc")
    assert list_resp.status_code == 200, f"List projects failed: {list_resp.text}"
    list_data = list_resp.json()["data"]
    print(f"Total projects found: {list_data['pagination']['total_items']}")
    matched = [item for item in list_data["items"] if item["id"] == p_id]
    assert len(matched) == 1, "Created project not found in listing"
    print(f"Project in list: my_role={matched[0]['my_role']}, members_count={matched[0]['members_count']}")

    print("\n--- 4. Get Project Details by UUID and Code (Section 2.3) ---")
    get_by_uuid = session.get(f"{BASE_URL}/projects/{p_id}")
    assert get_by_uuid.status_code == 200, f"Get by UUID failed: {get_by_uuid.text}"
    get_by_code = session.get(f"{BASE_URL}/projects/{p_code}")
    assert get_by_code.status_code == 200, f"Get by code failed: {get_by_code.text}"
    details = get_by_code.json()["data"]
    assert details["name"] == "Cloud Native FinTech"
    assert "stats" in details
    print(f"Summary verified: stats={details['stats']}")

    print("\n--- 5. Update Project Details (Section 2.4) ---")
    patch_resp = session.patch(
        f"{BASE_URL}/projects/{p_id}",
        json={
            "name": "Cloud Native FinTech v2",
            "description": "Updated high-throughput ledger spec.",
            "color": "#0EA5E9",
            "settings": {"auto_save_interval_ms": 1500},
        },
    )
    assert patch_resp.status_code == 200, f"Update failed: {patch_resp.text}"
    updated = patch_resp.json()["data"]
    assert updated["name"] == "Cloud Native FinTech v2"
    assert updated["color"] == "#0EA5E9"
    assert updated["settings"]["auto_save_interval_ms"] == 1500
    print("Project details successfully updated.")

    print("\n--- 6. Update Project Lifecycle Status (Section 2.5) ---")
    status_resp = session.patch(
        f"{BASE_URL}/projects/{p_id}/status",
        json={"status": "In Review"},
    )
    assert status_resp.status_code == 200, f"Status update failed: {status_resp.text}"
    assert status_resp.json()["data"]["status"] == "In Review"
    print(f"Status successfully updated to: {status_resp.json()['data']['status']}")

    print("\n--- 7. Update Display Order (Section 2.6) ---")
    order_resp = session.patch(
        f"{BASE_URL}/projects/{p_id}/order",
        json={"order_index": 7, "is_pinned": True},
    )
    assert order_resp.status_code == 200, f"Order update failed: {order_resp.text}"
    assert order_resp.json()["data"]["order_index"] == 7
    print("Personal display order updated.")

    print("\n--- 8. Delete Project with Confirmation Slug (Section 2.7) ---")
    # Mismatch attempt
    bad_del = session.request("DELETE", f"{BASE_URL}/projects/{p_id}", json={"confirm_slug": "wrong-slug"})
    assert bad_del.status_code == 400, f"Expected 400 on slug mismatch, got {bad_del.status_code}"
    print("Mismatched slug correctly rejected with 400 Bad Request.")

    # Successful delete
    good_del = session.request("DELETE", f"{BASE_URL}/projects/{p_id}", json={"confirm_slug": p_slug})
    assert good_del.status_code == 200, f"Delete failed: {good_del.text}"
    print("Project successfully purged.")

    # Verify 404 after deletion
    after_get = session.get(f"{BASE_URL}/projects/{p_id}")
    assert after_get.status_code == 404
    print("Verified 404 Not Found after deletion.")

    print("\n🎉 ALL PHASE 2 PROJECT ENDPOINTS VERIFIED SUCCESSFULLY AGAINST LIVE SERVER! 🎉")


if __name__ == "__main__":
    run_verification()
