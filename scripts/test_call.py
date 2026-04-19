"""Quick manual test of the call-server / Twilio integration."""
import json
import urllib.request

payload = {
    "patient_id": "aaaaaaaa-0000-0000-0000-000000000004",
    "urgency": "urgent",
}

req = urllib.request.Request(
    "http://127.0.0.1:8300/call-doctor",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as resp:
    body = json.loads(resp.read())
    print(json.dumps(body, indent=2))
