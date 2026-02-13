"""
Jenkins Pipeline LLM Fixer

Uses LLM to fix Jenkins pipeline errors based on validation results.
Implements iterative fix-and-validate cycle.
Mirrors gitlab_llm_fixer.py adapted for Jenkinsfile syntax.
"""
import re
from typing import Dict, Any, Optional, Tuple

from app.config import tools_manager
from app.integrations.llm_provider import get_llm_provider, get_active_provider_name


class JenkinsLLMFixer:
    """
    Uses LLM to fix Jenkins Declarative Pipeline errors.

    Flow:
    1. Receives Jenkinsfile with validation errors
    2. Constructs prompt with errors and best practices
    3. Gets LLM to fix the issues
    4. Returns corrected pipeline
    """

    FIX_MODEL = "pipeline-generator-v5"

    def __init__(self):
        self.ollama_config = tools_manager.get_tool("ollama")

    def _get_llm(self):
        """Get the configured LLM provider (Ollama or Claude Code)."""
        return get_llm_provider()

    async def fix_pipeline(
        self,
        jenkinsfile: str,
        dockerfile: str,
        errors: list,
        warnings: list,
        analysis: Dict[str, Any],
        model: str = None
    ) -> Dict[str, str]:
        """
        Fix Jenkinsfile using LLM based on validation errors.
        """
        model = model or self.FIX_MODEL

        error_context = ""
        if errors:
            error_context = "## CRITICAL ERRORS TO FIX:\n"
            for i, err in enumerate(errors, 1):
                error_context += f"{i}. {err}\n"

        warning_context = ""
        if warnings:
            warning_context = "\n## WARNINGS TO ADDRESS:\n"
            for i, warn in enumerate(warnings, 1):
                warning_context += f"{i}. {warn}\n"

        prompt = f"""
You must fix the following Jenkins Declarative Pipeline that has validation errors.

## PROJECT INFO:
- Language: {analysis.get('language', 'unknown')}
- Framework: {analysis.get('framework', 'generic')}
- Package Manager: {analysis.get('package_manager', 'unknown')}

{error_context}
{warning_context}

## CURRENT JENKINSFILE (WITH ERRORS):
```groovy
{jenkinsfile}
```

## CURRENT DOCKERFILE:
```dockerfile
{dockerfile}
```

## MANDATORY RULES FOR FIX:
1. ALL images MUST use Nexus registry: ${{NEXUS_REGISTRY}}/apm-repo/demo/<image>:<tag>
2. ALL Dockerfile FROM statements MUST use: ${{BASE_REGISTRY}}/apm-repo/demo/<image>:<tag>
3. Pipeline MUST have 9 stages: Compile, Build Image, Test Image, Static Analysis, SonarQube, Trivy Scan, Push Release, Notify, Learn
4. Use Jenkins Declarative Pipeline syntax (pipeline {{ agent {{ }} stages {{ }} post {{ }} }})
5. Use docker {{ }} agent blocks for compile stages with Nexus registry
6. Use docker.withRegistry("http://${{NEXUS_REGISTRY}}", 'nexus-credentials') for Build Image stage (HTTP only, NEVER https)
7. Notify and Learn MUST be explicit stages (NOT in post block). Post block only has failure (Splunk) + always (cleanWs)
8. Notify stage: curl to Splunk HEC with success event. Learn stage: curl to backend /api/v1/jenkins-pipeline/learn/record
8. Groovy syntax must be valid
9. Dockerfile MUST use ARG BASE_REGISTRY=localhost:5001 (NOT ai-nexus:5001)
10. docker.build() MUST include --build-arg: docker.build("...", "--build-arg BASE_REGISTRY=${{NEXUS_REGISTRY}} .")
11. Use agent {{ label 'docker' }} (NOT 'any')

## AVAILABLE NEXUS IMAGES:
- maven:3.9-eclipse-temurin-17 (Java/Maven/Scala builds)
- python:3.11-slim (Python)
- node:20-alpine (Node.js)
- golang:1.22-alpine (Go)
- rust:1.93-slim (Rust)
- ruby:3.3-alpine (Ruby)
- php:8.3-fpm-alpine (PHP)
- dotnet-sdk:8.0 (.NET build)
- dotnet-aspnet:8.0-alpine (.NET runtime)
- sonarsource-sonar-scanner-cli:5 (SonarQube)
- aquasec-trivy:latest (Trivy)
- alpine:3.18 (Minimal base)
- nginx:alpine (Static file serving)
- eclipse-temurin:17-jre (Java runtime)

## RESPONSE FORMAT:
Return ONLY the fixed files:

---JENKINSFILE---
(fixed Jenkinsfile content)
---DOCKERFILE---
(fixed Dockerfile content)
---END---
"""

        llm = self._get_llm()

        try:
            response = await llm.generate(
                prompt=prompt,
                model=model
            )

            response_text = response.get('response', '')
            jenkinsfile_fixed, dockerfile_fixed = self._parse_fix_response(
                response_text, jenkinsfile, dockerfile
            )

            return {
                'jenkinsfile': jenkinsfile_fixed,
                'dockerfile': dockerfile_fixed,
                'raw_response': response_text
            }

        except Exception as e:
            print(f"[Jenkins LLM Fixer] Error fixing pipeline: {e}")
            return {
                'jenkinsfile': jenkinsfile,
                'dockerfile': dockerfile,
                'error': str(e)
            }
        finally:
            await llm.close()

    def _parse_fix_response(
        self,
        response: str,
        original_jenkinsfile: str,
        original_dockerfile: str
    ) -> Tuple[str, str]:
        """Parse the LLM response to extract fixed files."""

        jenkinsfile = original_jenkinsfile
        dockerfile = original_dockerfile

        # Try marker-based extraction first
        jf_match = re.search(
            r'---JENKINSFILE---\s*(.*?)\s*(?:---DOCKERFILE---|---END---)',
            response, re.DOTALL
        )
        if jf_match:
            content = jf_match.group(1).strip()
            content = re.sub(r'^```\w*\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            if content and 'pipeline' in content:
                jenkinsfile = content

        df_match = re.search(
            r'---DOCKERFILE---\s*(.*?)\s*---END---',
            response, re.DOTALL
        )
        if df_match:
            content = df_match.group(1).strip()
            content = re.sub(r'^```\w*\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            if content and ('FROM' in content.upper() or 'ARG' in content.upper()):
                dockerfile = content

        # Fallback: try code block extraction
        if jenkinsfile == original_jenkinsfile:
            groovy_match = re.search(r'```groovy\s*(.*?)\s*```', response, re.DOTALL)
            if groovy_match:
                content = groovy_match.group(1).strip()
                if content and 'pipeline' in content:
                    jenkinsfile = content

        if dockerfile == original_dockerfile:
            docker_match = re.search(r'```dockerfile\s*(.*?)\s*```', response, re.DOTALL)
            if docker_match:
                content = docker_match.group(1).strip()
                if content and 'FROM' in content.upper():
                    dockerfile = content

        # Post-processing: fix common LLM mistakes
        jenkinsfile = jenkinsfile.replace('https://${NEXUS_REGISTRY}', 'http://${NEXUS_REGISTRY}')
        jenkinsfile = re.sub(r"agent\s*\{\s*label\s*'any'\s*\}", "agent { label 'docker' }", jenkinsfile)
        dockerfile = dockerfile.replace('ai-nexus:5001', 'localhost:5001')

        return jenkinsfile, dockerfile

    async def iterative_fix(
        self,
        jenkinsfile: str,
        dockerfile: str,
        analysis: Dict[str, Any],
        max_attempts: int = 10,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Iteratively fix pipeline until validation passes or max attempts reached.
        Uses text-based validation (no GitLab lint API for Jenkinsfile).
        """
        current_jenkinsfile = jenkinsfile
        current_dockerfile = dockerfile
        fix_history = []

        for attempt in range(1, max_attempts + 1):
            print(f"[Jenkins LLM Fixer] Attempt {attempt}/{max_attempts}")

            errors, warnings = self._validate_jenkinsfile(current_jenkinsfile, current_dockerfile)

            fix_history.append({
                'attempt': attempt,
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings
            })

            if not errors:
                print(f"[Jenkins LLM Fixer] Pipeline valid after {attempt} attempt(s)")
                return {
                    'success': True,
                    'jenkinsfile': current_jenkinsfile,
                    'dockerfile': current_dockerfile,
                    'attempts': attempt,
                    'fix_history': fix_history,
                    'has_warnings': len(warnings) > 0,
                    'fixer_model_used': get_active_provider_name()
                }

            if attempt < max_attempts:
                print(f"[Jenkins LLM Fixer] Fixing {len(errors)} errors...")
                fix_result = await self.fix_pipeline(
                    current_jenkinsfile,
                    current_dockerfile,
                    errors,
                    warnings,
                    analysis,
                    model
                )

                if 'error' not in fix_result:
                    current_jenkinsfile = fix_result['jenkinsfile']
                    current_dockerfile = fix_result['dockerfile']

        print(f"[Jenkins LLM Fixer] Max attempts ({max_attempts}) reached")
        return {
            'success': False,
            'jenkinsfile': current_jenkinsfile,
            'dockerfile': current_dockerfile,
            'attempts': max_attempts,
            'fix_history': fix_history,
            'final_errors': errors,
            'fixer_model_used': get_active_provider_name()
        }

    def _validate_jenkinsfile(self, jenkinsfile: str, dockerfile: str) -> Tuple[list, list]:
        """Basic text-based validation of Jenkinsfile and Dockerfile."""
        errors = []
        warnings = []

        if not jenkinsfile or not jenkinsfile.strip():
            errors.append("Jenkinsfile is empty")
            return errors, warnings

        if 'pipeline {' not in jenkinsfile and 'pipeline{' not in jenkinsfile:
            errors.append("Missing 'pipeline { }' block")
        if 'agent' not in jenkinsfile:
            errors.append("Missing 'agent' directive")
        if 'stages {' not in jenkinsfile and 'stages{' not in jenkinsfile:
            errors.append("Missing 'stages { }' block")
        if 'environment' not in jenkinsfile:
            warnings.append("Missing 'environment' block")
        if 'post {' not in jenkinsfile and 'post{' not in jenkinsfile:
            warnings.append("Missing 'post { }' block")

        public_registries = ['docker.io/', 'gcr.io/', 'quay.io/', 'ghcr.io/']
        for reg in public_registries:
            if reg in jenkinsfile:
                errors.append(f"Public registry reference found: {reg}")

        # Check for HTTPS (Nexus is HTTP-only)
        if 'https://${NEXUS_REGISTRY}' in jenkinsfile:
            errors.append("Jenkinsfile uses https:// for NEXUS_REGISTRY - must use http:// (Nexus is HTTP-only)")

        # Check for incorrect agent label
        if re.search(r"agent\s*\{\s*label\s*'any'\s*\}", jenkinsfile):
            errors.append("Agent label 'any' found - must use 'docker'")

        required = ['Compile', 'Build Image', 'Test Image', 'Static Analysis',
                     'SonarQube', 'Trivy Scan', 'Push Release', 'Notify', 'Learn']
        for stage in required:
            if f"stage('{stage}')" not in jenkinsfile and f'stage("{stage}")' not in jenkinsfile:
                warnings.append(f"Missing stage: {stage}")

        if dockerfile:
            if 'FROM' not in dockerfile.upper():
                errors.append("Dockerfile missing FROM statement")
            for reg in ['docker.io/', 'gcr.io/', 'quay.io/']:
                if reg in dockerfile:
                    errors.append(f"Dockerfile uses public registry: {reg}")
            if 'ai-nexus:5001' in dockerfile:
                errors.append("Dockerfile uses ai-nexus:5001 - must use localhost:5001")

        return errors, warnings


# Singleton instance
jenkins_llm_fixer = JenkinsLLMFixer()
