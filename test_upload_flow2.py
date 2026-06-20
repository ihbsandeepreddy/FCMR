import re, sys, requests
BASE = "http://127.0.0.1:8000"
s = requests.Session()
s.post(f"{BASE}/login", data={"username": "admin", "password": "admin123"}, allow_redirects=True)
r = s.get(f"{BASE}/")
eng_ids = re.findall(r'/engagements/([a-f0-9-]{36})/select', r.text)
if eng_ids:
    s.post(f"{BASE}/engagements/{eng_ids[0]}/select", allow_redirects=True)
    print(f"Selected engagement: {eng_ids[0][:8]}")
else:
    r2 = s.post(f"{BASE}/engagements", data={
        "name":"Test","client_name":"Client","period_from":"2026-01-01","period_to":"2026-12-31"
    }, allow_redirects=True)
    eng_ids2 = re.findall(r'/engagements/([a-f0-9-]{36})/select', r2.text)
    if eng_ids2:
        s.post(f"{BASE}/engagements/{eng_ids2[0]}/select", allow_redirects=True)
        print(f"Created+selected engagement: {eng_ids2[0][:8]}")
csv = "customer_id,full_name,lan,mobile_number,pan_number\nC001,Test,LAN001,9876543210,ABCDE1234F\n"
r = s.post(f"{BASE}/dashboard/upload",
    files={"files": ("cm_single.csv", csv.encode(), "text/csv")},
    data={"report_type": "customer_master", "consolidate": "off"},
    allow_redirects=True)
print(f"Upload: {r.status_code} at {r.url}")
if "map-columns" in r.url:
    print("FIXED: Single file upload redirects to map-columns")
else:
    print("Still going to:", r.url)
