"""
Comprehensive Test Suite for AI Dockerfile & GitLab CI Generator
Tests the full flow: ChromaDB retrieval -> API generation -> Output validation
Requires: All containers running in Docker Desktop (ChromaDB on :8000, API on :8080)
"""

import requests
import json
import os
import sys
import yaml
from datetime import datetime

# Configuration
CHROMADB_HOST = "localhost"
CHROMADB_PORT = 8000
API_HOST = "localhost"
API_PORT = 8080
OUTPUT_DIR = "test_output"

# Test counters
results = {"passed": 0, "failed": 0, "skipped": 0, "tests": []}


def log(msg, level="INFO"):
    prefix = {"INFO": "[INFO]", "PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "WARN": "[WARN]"}
    print(f"{prefix.get(level, '[INFO]')} {msg}")


def record(test_name, status, detail=""):
    results["tests"].append({"name": test_name, "status": status, "detail": detail})
    results[status] += 1
    log(f"{test_name}: {detail}", status.upper())


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(f"{OUTPUT_DIR}/dockerfiles", exist_ok=True)
    os.makedirs(f"{OUTPUT_DIR}/gitlab-ci", exist_ok=True)


# =============================================================================
# PHASE 1: Connectivity Tests
# =============================================================================

def test_chromadb_connectivity():
    """Test ChromaDB is reachable"""
    try:
        # Try v2 API first, fall back to v1
        resp = requests.get(f"http://{CHROMADB_HOST}:{CHROMADB_PORT}/api/v2/heartbeat", timeout=5)
        if resp.status_code != 200:
            resp = requests.get(f"http://{CHROMADB_HOST}:{CHROMADB_PORT}/api/v1/heartbeat", timeout=5)
        if resp.status_code == 200:
            record("chromadb_connectivity", "passed", "ChromaDB is reachable")
            return True
        else:
            record("chromadb_connectivity", "failed", f"HTTP {resp.status_code}")
            return False
    except Exception as e:
        record("chromadb_connectivity", "failed", f"Connection error: {e}")
        return False


def test_api_connectivity():
    """Test Generator API is reachable"""
    try:
        resp = requests.get(f"http://{API_HOST}:{API_PORT}/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            record("api_connectivity", "passed", f"API version: {data.get('version', 'unknown')}")
            return True
        else:
            record("api_connectivity", "failed", f"HTTP {resp.status_code}")
            return False
    except Exception as e:
        record("api_connectivity", "failed", f"Connection error: {e}")
        return False


# =============================================================================
# PHASE 2: ChromaDB Collection Tests
# =============================================================================

def test_chromadb_collections():
    """Verify all required collections exist and have data"""
    try:
        import chromadb
        client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)

        collections_to_check = ["templates_dockerfile", "templates_gitlab", "golden_rules"]
        all_ok = True

        for col_name in collections_to_check:
            try:
                col = client.get_collection(col_name)
                count = col.count()
                if count > 0:
                    record(f"collection_{col_name}", "passed", f"{count} documents found")
                else:
                    record(f"collection_{col_name}", "failed", "Collection is empty")
                    all_ok = False
            except Exception as e:
                record(f"collection_{col_name}", "failed", f"Error: {e}")
                all_ok = False

        return all_ok
    except ImportError:
        record("chromadb_collections", "skipped", "chromadb package not installed")
        return False


def test_chromadb_retrieval_all_stacks():
    """Test RAG retrieval for all stacks (java, python, node)"""
    try:
        import chromadb
        client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)

        dockerfile_col = client.get_collection("templates_dockerfile")
        gitlab_col = client.get_collection("templates_gitlab")

        stacks = ["java", "python", "node"]
        for stack in stacks:
            # Test Dockerfile retrieval
            df_results = dockerfile_col.query(
                query_texts=[f"{stack} application"],
                n_results=1,
                where={"stack": stack}
            )
            if df_results['ids'][0]:
                record(f"retrieval_dockerfile_{stack}", "passed",
                       f"Template ID: {df_results['ids'][0][0]}")
            else:
                record(f"retrieval_dockerfile_{stack}", "failed", "No template found")

            # Test GitLab CI retrieval
            gl_results = gitlab_col.query(
                query_texts=[f"{stack} pipeline"],
                n_results=1,
                where={"stack": stack}
            )
            if gl_results['ids'][0]:
                record(f"retrieval_gitlab_{stack}", "passed",
                       f"Template ID: {gl_results['ids'][0][0]}")
            else:
                record(f"retrieval_gitlab_{stack}", "failed", "No template found")

    except ImportError:
        record("chromadb_retrieval", "skipped", "chromadb package not installed")
    except Exception as e:
        record("chromadb_retrieval", "failed", f"Error: {e}")


# =============================================================================
# PHASE 3: API Generation Tests
# =============================================================================

def test_generate_dockerfile(stack, framework=None, port=8080, workdir="/app"):
    """Test Dockerfile generation via API"""
    test_name = f"generate_dockerfile_{stack}"
    try:
        payload = {"stack": stack, "port": port, "workdir": workdir}
        if framework:
            payload["framework"] = framework

        resp = requests.post(
            f"http://{API_HOST}:{API_PORT}/generate/dockerfile",
            json=payload,
            timeout=10
        )

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("content", "")
            audit = data.get("audit", {})

            # Save generated Dockerfile
            output_file = f"{OUTPUT_DIR}/dockerfiles/Dockerfile.{stack}"
            with open(output_file, 'w') as f:
                f.write(content)

            record(test_name, "passed",
                   f"Generated ({len(content)} chars), base: {audit.get('base_image', 'N/A')}")
            return content, audit
        else:
            error = resp.json().get("detail", resp.text)
            record(test_name, "failed", f"HTTP {resp.status_code}: {error}")
            return None, None

    except Exception as e:
        record(test_name, "failed", f"Error: {e}")
        return None, None


def test_generate_gitlab_ci(stack, build_tool=None):
    """Test GitLab CI generation via API"""
    test_name = f"generate_gitlabci_{stack}"
    try:
        payload = {"stack": stack}
        if build_tool:
            payload["build_tool"] = build_tool

        resp = requests.post(
            f"http://{API_HOST}:{API_PORT}/generate/gitlabci",
            json=payload,
            timeout=10
        )

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("content", "")
            audit = data.get("audit", {})

            # Save generated GitLab CI
            output_file = f"{OUTPUT_DIR}/gitlab-ci/.gitlab-ci.{stack}.yml"
            with open(output_file, 'w') as f:
                f.write(content)

            record(test_name, "passed",
                   f"Generated ({len(content)} chars), template: {audit.get('template_id', 'N/A')}")
            return content, audit
        else:
            error = resp.json().get("detail", resp.text)
            record(test_name, "failed", f"HTTP {resp.status_code}: {error}")
            return None, None

    except Exception as e:
        record(test_name, "failed", f"Error: {e}")
        return None, None


def test_generate_invalid_stack():
    """Test generation with invalid stack returns proper error"""
    try:
        resp = requests.post(
            f"http://{API_HOST}:{API_PORT}/generate/dockerfile",
            json={"stack": "cobol", "port": 8080},
            timeout=10
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "TEMPLATE_MISSING" in detail:
                record("generate_invalid_stack", "passed", "Correct TEMPLATE_MISSING error")
            else:
                record("generate_invalid_stack", "passed", f"400 returned: {detail}")
        else:
            record("generate_invalid_stack", "failed",
                   f"Expected 400, got {resp.status_code}")
    except Exception as e:
        record("generate_invalid_stack", "failed", f"Error: {e}")


# =============================================================================
# PHASE 4: Validation Tests
# =============================================================================

def validate_dockerfile(content, stack):
    """Validate generated Dockerfile against golden rules"""
    test_name = f"validate_dockerfile_{stack}"
    issues = []

    if not content:
        record(test_name, "skipped", "No content to validate")
        return

    # Rule 1: No public registries
    public_registries = ["docker.io", "FROM python:", "FROM node:", "FROM java:",
                         "FROM openjdk:", "ghcr.io", "quay.io"]
    for reg in public_registries:
        if reg in content:
            issues.append(f"Public registry detected: {reg}")

    # Rule 2: Must use private Nexus registry
    if "localhost:5001" not in content and "ai-nexus:5001" not in content:
        issues.append("No private registry reference found")

    # Rule 3: Must have FROM statement
    if "FROM" not in content:
        issues.append("Missing FROM statement")

    # Rule 4: Must have EXPOSE
    if "EXPOSE" not in content:
        issues.append("Missing EXPOSE statement")

    # Rule 5: Must have WORKDIR
    if "WORKDIR" not in content:
        issues.append("Missing WORKDIR statement")

    if issues:
        record(test_name, "failed", "; ".join(issues))
    else:
        record(test_name, "passed", "All validation rules passed")


def validate_gitlab_ci(content, stack):
    """Validate generated GitLab CI against golden rules"""
    test_name = f"validate_gitlabci_{stack}"
    issues = []

    if not content:
        record(test_name, "skipped", "No content to validate")
        return

    # Rule 1: Must have stages
    if "stages:" not in content:
        issues.append("Missing 'stages:' definition")

    # Rule 2: Must use private registry for images
    if "docker.io" in content or "FROM python:" in content:
        issues.append("Public registry detected")

    # Rule 3: Must have build stage
    if "build" not in content:
        issues.append("Missing build stage")

    # Rule 4: Should have security scanning
    if "trivy" not in content.lower() and "security" not in content.lower():
        issues.append("No security scanning stage found")

    # Rule 5: Validate YAML structure
    try:
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            issues.append("Invalid YAML structure")
        elif "stages" not in parsed:
            issues.append("YAML parsed but 'stages' key missing")
    except yaml.YAMLError as e:
        issues.append(f"YAML parse error: {e}")

    # Rule 6: Should reference Nexus registry
    if "NEXUS" not in content and "nexus" not in content and "localhost:5001" not in content:
        issues.append("No Nexus registry reference found")

    if issues:
        record(test_name, "failed", "; ".join(issues))
    else:
        record(test_name, "passed", "All validation rules passed")


# =============================================================================
# PHASE 5: Catalog Validation
# =============================================================================

def test_catalog_endpoint():
    """Test catalog endpoint returns valid data"""
    try:
        resp = requests.get(f"http://{API_HOST}:{API_PORT}/catalog", timeout=5)
        if resp.status_code == 200:
            catalog = resp.json()
            stacks = ["java", "python", "node"]
            missing = [s for s in stacks if s not in catalog]
            if missing:
                record("catalog_check", "failed", f"Missing stacks: {missing}")
            else:
                record("catalog_check", "passed",
                       f"{len(catalog)} images, all required stacks present")
        else:
            record("catalog_check", "failed", f"HTTP {resp.status_code}")
    except Exception as e:
        record("catalog_check", "failed", f"Error: {e}")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def print_summary():
    print("\n" + "=" * 70)
    print(f"  TEST RESULTS SUMMARY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"  PASSED: {results['passed']}")
    print(f"  FAILED: {results['failed']}")
    print(f"  SKIPPED: {results['skipped']}")
    print(f"  TOTAL:  {results['passed'] + results['failed'] + results['skipped']}")
    print("=" * 70)

    if results['failed'] > 0:
        print("\n  FAILED TESTS:")
        for t in results['tests']:
            if t['status'] == 'failed':
                print(f"    - {t['name']}: {t['detail']}")

    print("\n  OUTPUT FILES:")
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            filepath = os.path.join(root, f)
            size = os.path.getsize(filepath)
            print(f"    - {filepath} ({size} bytes)")

    # Save results JSON
    results_file = f"{OUTPUT_DIR}/test_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to: {results_file}")
    print("=" * 70)


def main():
    print("=" * 70)
    print("  AI Dockerfile & GitLab CI Generator - Test Suite")
    print("  Testing against ChromaDB data in Docker Desktop")
    print("=" * 70)

    ensure_output_dir()

    # Phase 1: Connectivity
    print("\n--- PHASE 1: Connectivity Tests ---")
    chromadb_ok = test_chromadb_connectivity()
    api_ok = test_api_connectivity()

    if not chromadb_ok:
        print("\n[FATAL] ChromaDB not reachable. Ensure container is running on port 8000.")
        print("  Try: docker ps | grep chroma")
        print_summary()
        sys.exit(1)

    # Phase 2: ChromaDB Collections
    print("\n--- PHASE 2: ChromaDB Collection Tests ---")
    test_chromadb_collections()
    test_chromadb_retrieval_all_stacks()

    if not api_ok:
        print("\n[WARN] Generator API not reachable on port 8080.")
        print("  Skipping API tests. Start API with:")
        print("  cd rag-ai && python generator_api.py")
        print_summary()
        sys.exit(0)

    # Phase 3: API Generation
    print("\n--- PHASE 3: API Generation Tests ---")

    # Java
    java_df, java_df_audit = test_generate_dockerfile("java", framework="spring-boot")
    java_ci, java_ci_audit = test_generate_gitlab_ci("java", build_tool="maven")

    # Python
    python_df, python_df_audit = test_generate_dockerfile("python", framework="fastapi", port=8000)
    python_ci, python_ci_audit = test_generate_gitlab_ci("python", build_tool="pip")

    # Node
    node_df, node_df_audit = test_generate_dockerfile("node", framework="express", port=3000)
    node_ci, node_ci_audit = test_generate_gitlab_ci("node", build_tool="npm")

    # Invalid stack
    test_generate_invalid_stack()

    # Phase 4: Validation
    print("\n--- PHASE 4: Output Validation Tests ---")
    validate_dockerfile(java_df, "java")
    validate_dockerfile(python_df, "python")
    validate_dockerfile(node_df, "node")
    validate_gitlab_ci(java_ci, "java")
    validate_gitlab_ci(python_ci, "python")
    validate_gitlab_ci(node_ci, "node")

    # Phase 5: Catalog
    print("\n--- PHASE 5: Catalog Validation ---")
    test_catalog_endpoint()

    # Summary
    print_summary()

    # Exit code
    sys.exit(1 if results['failed'] > 0 else 0)


if __name__ == "__main__":
    main()
