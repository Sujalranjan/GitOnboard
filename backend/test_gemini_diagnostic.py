#!/usr/bin/env python3
"""Direct test of Gemini API to capture 429 error response."""
import asyncio
import httpx
import json
import sys
import os

async def test_gemini():
    """Make a Gemini request and capture error details."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set")
        sys.exit(1)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": "Hello, please respond briefly."}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 100,
        }
    }

    print("[TEST] Sending Gemini request...")
    print(f"[TEST] URL (redacted key): ...key={api_key[-10:]}")
    print(f"[TEST] Payload size: {len(json.dumps(payload))} bytes")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)

    print(f"\n[RESPONSE] Status Code: {resp.status_code}")
    print(f"[RESPONSE] Headers:")
    for key, value in resp.headers.items():
        if key.lower() not in ["authorization", "x-goog-user-project"]:
            print(f"  {key}: {value}")

    print(f"\n[RESPONSE] Body ({len(resp.text)} bytes):")
    print(resp.text[:2000])

    if resp.status_code == 429:
        print("\n[DIAGNOSTIC] Parsing 429 error details...")
        try:
            error_data = json.loads(resp.text)
            print(json.dumps(error_data, indent=2))
        except:
            print("Could not parse as JSON")

if __name__ == "__main__":
    asyncio.run(test_gemini())
