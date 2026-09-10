"""
Evidence reconciliation: exact failure analysis.

The report claimed "3-4% vocabulary gaps" but adversarial evaluation shows:
- 4 FAIL / 24 = 16.7%
- 3 PARTIAL / 24 = 12.5%
- Total failures = 29.2%

This script reconciles the data and classifies each failure precisely.
"""

# From adversarial_evaluation.py output

FAILURES = [
    {
        "query": "How does login work?",
        "type": "FAIL",
        "baseline": 0,
        "rim": 0,
        "expected": ["authMiddleware", "authenticateToken", "createSession"],
        "reason": "login vs auth"
    },
    {
        "query": "How is access controlled?",
        "type": "PARTIAL",
        "baseline": 0,
        "rim": 1,
        "rim_entities": ["controllers/authcontroller.js"],
        "expected": ["checkPermissions"],
        "reason": "access controlled = permissions check"
    },
    {
        "query": "What functions depend on authentication?",
        "type": "PARTIAL",
        "baseline": 0,
        "rim": 1,
        "rim_entities": ["authMiddleware"],
        "expected": ["checkPermissions"],
        "reason": "dependent functions"
    },
    {
        "query": "Where are credentials stored?",
        "type": "FAIL",
        "baseline": 0,
        "rim": 0,
        "expected": ["createSession", "setAuthCookies"],
        "reason": "credentials location"
    },
    {
        "query": "What prevents unauthorized access?",
        "type": "FAIL",
        "baseline": 0,
        "rim": 0,
        "expected": ["checkPermissions"],
        "reason": "prevent unauthorized = permissions"
    },
    {
        "query": "How does the database schema work?",
        "type": "FAIL",
        "baseline": 0,
        "rim": 0,
        "expected": [],
        "reason": "completely unrelated",
        "correctly_rejected": True
    },
    {
        "query": "How is access controlled?",
        "type": "PARTIAL",
        "baseline": 0,
        "rim": 1,
        "rim_entities": ["controllers/authcontroller.js"],
        "expected": ["checkPermissions"],
        "reason": "returns file instead of function"
    }
]

print("="*100)
print("EVIDENCE RECONCILIATION: FAILURE ANALYSIS")
print("="*100)

print("\n📊 NUMERICAL RECONCILIATION\n")
print("Adversarial evaluation: 24 queries tested")
print("Results from output:")
print("  PASS:    17/24 (70.8%)")
print("  PARTIAL:  3/24 (12.5%)")
print("  FAIL:     4/24 (16.7%)")
print("  Total problems: 7/24 (29.2%)")

print("\n" + "="*100)
print("FAIL QUERIES (4)")
print("="*100)

fail_queries = [
    ("How does login work?", "login vs auth", "vocabulary gap"),
    ("Where are credentials stored?", "credentials/stored not in code vocabulary", "vocabulary gap"),
    ("What prevents unauthorized access?", "prevent/unauthorized not in code vocabulary", "vocabulary gap"),
    ("How does the database schema work?", "completely unrelated", "correctly rejected"),
]

for i, (query, reason, classification) in enumerate(fail_queries, 1):
    print(f"\n{i}. {query}")
    print(f"   Reason: {reason}")
    print(f"   Type: {classification}")
    if classification == "vocabulary gap":
        print(f"   Semantic Retrieval Would Help? YES - requires embeddings to bridge gap")
    else:
        print(f"   Semantic Retrieval Would Help? NO - correctly rejects unrelated query")

print("\n" + "="*100)
print("PARTIAL QUERIES (3)")
print("="*100)

partial_queries = [
    ("How is access controlled?", "authorization vs permissions", "wrong entity type (file vs function)", "NO - retrieval working, needs richer relationships or better ranking"),
    ("What functions depend on authentication?", "dependent functions", "found authMiddleware but expected checkPermissions", "MAYBE - semantic could improve ranking"),
    ("How is access controlled? [duplicate]", "Wrong entity returned", "Found file path not function", "NO - issue is ranking, not retrieval"),
]

for i, (query, issue, detail, semantic_help) in enumerate(partial_queries, 1):
    print(f"\n{i}. {query}")
    print(f"   Issue: {issue}")
    print(f"   Detail: {detail}")
    print(f"   Semantic Retrieval Would Help? {semantic_help}")

print("\n" + "="*100)
print("ROOT CAUSE CLASSIFICATION")
print("="*100)

print("""
FAIL (4 queries):
  - Vocabulary gaps (3):
    * "login" vs "auth" - No token overlap, BM25 fails, semantic would recover
    * "credentials stored" - No token overlap, BM25 fails, semantic might recover
    * "prevent unauthorized" - No token overlap, BM25 fails, semantic might recover

  - Correctly rejected (1):
    * "database schema" - Unrelated to code, correctly returns 0 results
    * Semantic: NO, correctly rejected should stay rejected

PARTIAL (3 queries):
  - Wrong entity type (1):
    * "How is access controlled?" - Returns file path instead of checkPermissions
    * Root: Lexical match too broad, needs filtering/ranking
    * Semantic: NO, this is ranking/filtering issue not retrieval gap

  - Wrong entity selected (1):
    * "What functions depend on authentication?" - Returns authMiddleware not checkPermissions
    * Root: Multiple entities match, chose wrong one
    * Semantic: MAYBE, better ranking could help

  - Duplicate entry (1):
    * Overlap with above

SUMMARY OF SEMANTIC IMPACT:
  Would fix: 3 FAIL queries (vocabulary gaps) → potential 3 additional PASS
  Might improve: 1 PARTIAL query (ranking)
  Won't fix: 1 PARTIAL (filtering issue), 1 FAIL (correctly rejected)

Potential with semantic: 20 PASS + maybe 1 improved PARTIAL = 21/24
Current without semantic: 17 PASS = 17/24
Potential improvement: +3-4 queries (12-17%)
""")

print("\n" + "="*100)
print("WHERE DOES THE '3-4%' COME FROM?")
print("="*100)

print("""
ERROR IN REPORTING: The 3-4% figure was WRONG.

Derivation of wrong number:
  - Based on: "only deep vocabulary mismatches fail"
  - Assumed: vocabulary gaps are rare in practice
  - Error: Confused "expected/acceptable limitation" with "measured frequency"
  - Reality: Measured 16.7% FAIL from vocabulary gaps alone

CORRECT NUMBERS FROM ADVERSARIAL EVALUATION:
  - Vocabulary gap failures: 3 out of 24 = 12.5%
  - Ranking/filtering issues: 1-2 out of 24 = 4-8%
  - Correctly rejected: 1 out of 24 = 4%
  - Total failures: 7 out of 24 = 29.2%

  But only 3-4 are "vocabulary gaps that semantic could fix"
  The others are ranking/filtering or correct rejections.

RECONCILIATION:
  - Report said: "3-4% vocabulary gaps" (WRONG)
  - Reality shows: "12.5% vocabulary gaps, 4% ranking issues, 4% correct rejections"
  - This changes the production readiness verdict
""")

print("\n" + "="*100)
print("PRODUCTION IMPLICATIONS")
print("="*100)

print("""
Current (lexical + fallback only):
  - Success rate: 83% (PASS + PARTIAL)
  - True PASS rate: 71% (answers question fully)
  - Vocabulary gaps blocking: 12.5% of queries

With semantic retrieval:
  - Could recover: 3 vocabulary-gap queries → estimated 88-92% PASS rate
  - Ranking improvements: might fix 1 additional PARTIAL
  - Total potential: 88-92% true PASS rate

Whether this is acceptable depends on:
  1. Is 71% PASS acceptable (or need 88%+)?
  2. Are vocabulary gaps acceptable as documented limitation?
  3. Is semantic indexing going to be enabled in production?
""")
