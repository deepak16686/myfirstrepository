import chromadb

# Connect to ChromaDB (adjust host/port if needed)
client = chromadb.HttpClient(host='localhost', port=8000)

# Create collections
collections = [
    "templates_dockerfile",
    "templates_gitlab", 
    "golden_rules"
]

for collection_name in collections:
    try:
        collection = client.get_or_create_collection(name=collection_name)
        print(f"[OK] Collection '{collection_name}' created/verified")
    except Exception as e:
        print(f"[ERROR] creating '{collection_name}': {e}")

# List all collections to verify
print("\nAll collections:")
for collection in client.list_collections():
    print(f"  - {collection.name}")
