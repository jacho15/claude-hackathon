import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

print("patient_current_state rows:", sb.table("patient_current_state").select("*", count="exact").execute().count)
print("vitals_readings rows      :", sb.table("vitals_readings").select("*", count="exact").execute().count)
print("flags rows                :", sb.table("flags").select("*", count="exact").execute().count)
print("doctor_calls rows         :", sb.table("doctor_calls").select("*", count="exact").execute().count)

print()
print("Latest patient_current_state (sorted by NEWS2 desc):")
rows = (
    sb.table("patient_current_state")
    .select("patient_id,flag,news2_score,news2_risk,hr,spo2,last_updated")
    .order("news2_score", desc=True)
    .execute()
    .data
)
for r in rows:
    print(
        f"  pid={r['patient_id'][-4:]}  flag={r['flag']:<8}  "
        f"NEWS2={r['news2_score']} ({r['news2_risk']})  "
        f"HR={r['hr']}  SpO2={r['spo2']}  updated={r['last_updated']}"
    )

print()
print("Recent doctor_calls:")
dc = sb.table("doctor_calls").select("patient_id,doctor_name,urgency,status,reason,created_at").order("created_at", desc=True).limit(5).execute().data
for r in dc:
    print(f"  [{r['urgency']:<7}] -> {r['doctor_name']:<12} status={r['status']:<10} {r['reason']}")
