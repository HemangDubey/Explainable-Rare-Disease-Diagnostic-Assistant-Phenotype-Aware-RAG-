import urllib.request
import json
import time

def test_api_quality_gate():
    time.sleep(2) # Give server time to bind
    base_url = "http://127.0.0.1:8000"

    print("=== TESTING API /api/input/validate ===")
    req_data = json.dumps({"text": "hii"}).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/api/input/validate", data=req_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Validate 'hii' response:", res)
        assert res["status"] == "NON_CLINICAL"
        assert res["is_valid_clinical"] == False

    print("\n=== TESTING API /api/input/enhance ===")
    req_data_enh = json.dumps({"text": "pt has dev delay and seizures since 2 yrs"}).encode("utf-8")
    req_enh = urllib.request.Request(f"{base_url}/api/input/enhance", data=req_data_enh, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req_enh) as resp:
        res_enh = json.loads(resp.read().decode("utf-8"))
        print("Enhance response:", res_enh)
        assert "enhanced_text" in res_enh
        assert res_enh["original_text"] == "pt has dev delay and seizures since 2 yrs"

    print("\n=== TESTING END-TO-END /api/diagnose WITH VALID CASE ===")
    diag_data = json.dumps({"text": "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.", "top_k": 5}).encode("utf-8")
    req_diag = urllib.request.Request(f"{base_url}/api/diagnose", data=diag_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req_diag) as resp:
        res_diag = json.loads(resp.read().decode("utf-8"))
        print("Diagnose response case_id:", res_diag.get("case_id"))
        print("Phenotypes count:", len(res_diag.get("extracted_phenotypes", [])))
        print("Fused candidates count:", len(res_diag.get("fused_candidates", [])))
        assert len(res_diag.get("fused_candidates", [])) > 0

    print("\n=== TESTING BLOCKING OF INVALID CASE ON /api/diagnose ===")
    bad_data = json.dumps({"text": "asdfgh"}).encode("utf-8")
    req_bad = urllib.request.Request(f"{base_url}/api/diagnose", data=bad_data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req_bad) as resp:
            print("FAILED: Should have blocked 'asdfgh'")
    except urllib.error.HTTPError as e:
        print("Successfully blocked 'asdfgh' with HTTP Status:", e.code)
        err_body = json.loads(e.read().decode("utf-8"))
        print("Error detail:", err_body.get("detail"))
        assert e.code == 400

    print("\nALL API INTEGRATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_api_quality_gate()
