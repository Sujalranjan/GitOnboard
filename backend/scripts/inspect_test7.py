import json

with open(r'C:\Users\Dheeraj\.gemini\antigravity-ide\brain\01a1dfd0-b86e-4013-92bc-ca5eca90d87a\test7_coverage\test7_normal_path_result.json', 'r', encoding='utf-8-sig') as f:
    data = json.load(f)

print(f"Total turns: {len(data.get('turns', []))}")
for t in data.get('turns', []):
    idx = t.get('turn_index')
    tc = t.get('tool_call') or {}
    tname = tc.get('tool_name')
    args = tc.get('arguments')
    obs = t.get('tool_observation') or {}
    err = obs.get('error')
    print(f"Turn {idx}: {tname} -> {args}")
    if err:
        print(f"   ERROR: {err}")
