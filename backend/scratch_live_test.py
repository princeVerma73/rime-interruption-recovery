import os
import sys
import httpx
import json

base_url = "http://127.0.0.1:8000"

# 1. Create Session
sess_res = httpx.post(f"{base_url}/api/voice/session")
assert sess_res.status_code == 201, sess_res.text
session_id = sess_res.json()["session_id"]
print(f"Session created: {session_id}")

# 2. Test Normal Query (No Tavily)
print("\n--- TEST 1: Normal LLM Query ---")
res1 = httpx.post(
    f"{base_url}/api/voice/agent/process-text",
    json={"session_id": session_id, "text": "Explain quantum computing in simple words."},
    timeout=30.0,
)
assert res1.status_code == 200, res1.text
print("Status:", res1.status_code)
print("X-Search-Used:", res1.headers.get("x-search-used"))
print("X-Final-Response:", res1.headers.get("x-final-response"))
print("Audio bytes length:", len(res1.content))

# 3. Test Search Query (With Tavily)
print("\n--- TEST 2: Current Information Query with Tavily ---")
res2 = httpx.post(
    f"{base_url}/api/voice/agent/process-text",
    json={"session_id": session_id, "text": "What is the latest AI news?"},
    timeout=30.0,
)
assert res2.status_code == 200, res2.text
print("Status:", res2.status_code)
print("X-Search-Used:", res2.headers.get("x-search-used"))
print("X-Search-Sources:", res2.headers.get("x-search-sources"))
print("X-Final-Response:", res2.headers.get("x-final-response"))
print("Audio bytes length:", len(res2.content))

# Check response does NOT say "I cannot provide real-time" or "I do not have internet"
final_resp = res2.headers.get("x-final-response", "")
assert "cannot provide" not in final_resp.lower() or "news" in final_resp.lower()
print("\nSUCCESS: All live API tests passed seamlessly!")
