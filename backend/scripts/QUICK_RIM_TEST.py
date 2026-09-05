#!/usr/bin/env python3
"""Quick RIM graph expansion test."""
import json
import requests
import time

API_BASE_URL = "http://localhost:8000/api"

print("Testing RIM graph expansion...")
print("=" * 70)

# Test one query
query = "What is the main entry point?"
repo = "Deep-Guard-ML-Engine"

print(f"Query: {query}")
print(f"Repository: {repo}")
print()

try:
    print("Sending request to comparison endpoint...")
    response = requests.post(
        f"{API_BASE_URL}/repos/{repo}/rim-comparison/compare",
        json={"question": query},
        timeout=120  # Increase timeout for longer queries
    )

    if response.status_code == 200:
        result = response.json()
        trace = result.get("trace", {})

        print("✓ Request successful!")
        print()
        print("RIM Trace:")
        print(f"  Enabled: {trace.get('enabled')}")
        print(f"  Query: {trace.get('query')}")
        print()
        print(f"  Anchors (initial retrieval): {trace.get('anchor_count')}")
        print(f"  Anchor details:")
        for anchor in trace.get('anchors', [])[:3]:
            print(f"    - {anchor.get('name')} ({anchor.get('file')})")
        print()
        print(f"  Expanded entities (graph): {trace.get('expansion_count')}")
        print(f"  Expanded entity details:")
        for exp in trace.get('expanded_entities', [])[:3]:
            print(f"    - {exp.get('name')} ({exp.get('file')}) distance={exp.get('distance')}")
        print()
        print(f"  Relationships found: {len(trace.get('relationships', []))}")
        print(f"  Relationship types: {trace.get('relationship_types')}")
        print()
        print(f"  Total nodes expanded: {trace.get('total_nodes_expanded')}")
        print(f"  Graph depth: {trace.get('graph_depth')}")
        print()

        # Check if expansion occurred
        if trace.get('expansion_count', 0) > 0:
            print("✓ GRAPH EXPANSION DETECTED!")
        else:
            print("✗ No graph expansion detected")

    else:
        print(f"✗ Request failed: {response.status_code}")
        print(response.text[:500])

except requests.exceptions.Timeout:
    print("✗ Request timed out (endpoint is slow)")
except Exception as e:
    print(f"✗ Error: {e}")
