import chromadb
import sys

# Connect to ChromaDB
try:
    client = chromadb.HttpClient(host='localhost', port=8000)
    client.heartbeat()
    print("[OK] Connected to ChromaDB")
except Exception as e:
    print(f"[ERROR] Cannot connect to ChromaDB: {e}")
    print("  Ensure ChromaDB container is running on port 8000")
    sys.exit(1)

# Get collections
try:
    dockerfile_collection = client.get_collection("templates_dockerfile")
    gitlab_collection = client.get_collection("templates_gitlab")
    golden_rules_collection = client.get_collection("golden_rules")
    print(f"[OK] Collections loaded - Dockerfiles: {dockerfile_collection.count()}, "
          f"GitLab: {gitlab_collection.count()}, Rules: {golden_rules_collection.count()}")
except Exception as e:
    print(f"[ERROR] Collections not found: {e}")
    print("  Run: python ingest_templates.py")
    sys.exit(1)

# Test all stacks
stacks = [
    {"name": "java", "query_df": "java spring boot application", "query_ci": "java maven pipeline"},
    {"name": "python", "query_df": "python fastapi application", "query_ci": "python pytest pipeline"},
    {"name": "node", "query_df": "node express application", "query_ci": "node npm pipeline"},
]

test_num = 0
passed = 0
failed = 0

for stack in stacks:
    # Test Dockerfile retrieval
    test_num += 1
    print(f"\n{'=' * 60}")
    print(f"TEST {test_num}: Query Dockerfile by stack='{stack['name']}'")
    print("=" * 60)
    results = dockerfile_collection.query(
        query_texts=[stack["query_df"]],
        n_results=1,
        where={"stack": stack["name"]}
    )
    if results['ids'][0]:
        print(f"  [PASS] Found: {results['ids'][0][0]}")
        print(f"  Metadata: {results['metadatas'][0][0]}")
        print(f"  Content preview: {results['documents'][0][0][:150]}...")
        passed += 1
    else:
        print(f"  [FAIL] No Dockerfile template for stack '{stack['name']}'")
        failed += 1

    # Test GitLab CI retrieval
    test_num += 1
    print(f"\n{'=' * 60}")
    print(f"TEST {test_num}: Query GitLab CI by stack='{stack['name']}'")
    print("=" * 60)
    results = gitlab_collection.query(
        query_texts=[stack["query_ci"]],
        n_results=1,
        where={"stack": stack["name"]}
    )
    if results['ids'][0]:
        print(f"  [PASS] Found: {results['ids'][0][0]}")
        print(f"  Metadata: {results['metadatas'][0][0]}")
        print(f"  Content preview: {results['documents'][0][0][:150]}...")
        passed += 1
    else:
        print(f"  [FAIL] No GitLab CI template for stack '{stack['name']}'")
        failed += 1

# Test Golden Rules
test_num += 1
print(f"\n{'=' * 60}")
print(f"TEST {test_num}: Retrieve Golden Rules")
print("=" * 60)
results = golden_rules_collection.query(
    query_texts=["private registry constraints"],
    n_results=1
)
if results['ids'][0]:
    print(f"  [PASS] Found: {results['ids'][0][0]}")
    print(f"  Metadata: {results['metadatas'][0][0]}")
    print(f"  Content preview: {results['documents'][0][0][:200]}...")
    passed += 1
else:
    print("  [FAIL] No golden rules found")
    failed += 1

# Summary
print(f"\n{'=' * 60}")
print(f"  RETRIEVAL TEST RESULTS: {passed} passed, {failed} failed, {test_num} total")
print("=" * 60)

if failed > 0:
    print("\n  [ACTION] Run 'python ingest_templates.py' to load missing templates")
    sys.exit(1)
else:
    print("\n  All retrieval tests passed!")
    sys.exit(0)
