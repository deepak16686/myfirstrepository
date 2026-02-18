"""
File: service.py
Purpose: Converts pipeline configurations between GitLab CI, Jenkins (Jenkinsfile), and GitHub Actions formats, using built-in templates for known languages (Java, Python, Node.js, Go, Ruby, .NET, Rust) and falling back to LLM-based conversion for custom or unrecognized pipelines.
When Used: Called by the migration assistant router when users paste a pipeline file and request conversion to a different CI/CD format.
Why Created: Enables teams migrating between CI/CD platforms to automatically translate their pipeline definitions, reducing the manual effort of rewriting build configurations when switching from GitLab to Jenkins or GitHub Actions (and vice versa).
"""
import re
from typing import Dict, Any, Optional

from app.integrations.llm_provider import get_llm_provider


MIGRATION_SYSTEM_PROMPT = """You are a CI/CD pipeline migration expert. Convert pipeline configurations between GitLab CI (.gitlab-ci.yml), Jenkins (Declarative Jenkinsfile), and GitHub Actions (workflow YAML) formats.

Rules:
- Preserve all pipeline stages and their order
- Map equivalent concepts between formats (e.g., GitLab stages -> Jenkins stages -> GitHub Actions jobs)
- Use idiomatic syntax for the target format
- Preserve environment variables, secrets references, and Docker image references
- Add comments explaining any non-trivial mappings
- Output ONLY the converted pipeline content, no explanations before or after
- Use proper indentation and formatting for the target format
"""

FORMATS = {"gitlab", "jenkins", "github-actions"}

# Languages supported by all 3 template systems
COMMON_LANGUAGES = {"java", "python", "javascript", "go"}

ALL_TEMPLATE_LANGUAGES = {
    "java", "python", "javascript", "go", "rust", "ruby", "php",
    "scala", "kotlin", "csharp", "dotnet", "typescript",
    "django", "flask", "fastapi", "golang",
}


class MigrationAssistantService:
    """Service for converting pipeline configurations between formats."""

    def detect_format(self, pipeline_content: str) -> Dict[str, Any]:
        """Detect the source format of a pipeline configuration."""
        content = pipeline_content.strip()

        # Jenkins Declarative Pipeline
        if re.search(r'\bpipeline\s*\{', content) and re.search(r'\bagent\b', content):
            return {"format": "jenkins", "confidence": "high"}

        # GitHub Actions
        if re.search(r'\bon:', content) and re.search(r'\bjobs:', content) and re.search(r'\bruns-on:', content):
            return {"format": "github-actions", "confidence": "high"}

        # GitLab CI
        if re.search(r'\bstages:', content) and (re.search(r'\bimage:', content) or re.search(r'\btags:', content)):
            return {"format": "gitlab", "confidence": "high"}

        # Lower confidence checks
        if 'Jenkinsfile' in content or 'sh ' in content and 'stage(' in content:
            return {"format": "jenkins", "confidence": "medium"}
        if 'uses:' in content and 'steps:' in content:
            return {"format": "github-actions", "confidence": "medium"}
        if 'script:' in content and 'stage:' in content:
            return {"format": "gitlab", "confidence": "medium"}

        return {"format": "unknown", "confidence": "low"}

    def detect_language(self, pipeline_content: str) -> Optional[str]:
        """Try to detect the project language from pipeline content."""
        content = pipeline_content.lower()
        patterns = {
            "java": [r'\bmaven\b', r'\bgradle\b', r'\bpom\.xml\b', r'\bjava\b', r'\bopenjdk\b', r'\bspringboot\b'],
            "python": [r'\bpip\b', r'\bpython\b', r'\buvicorn\b', r'\bpytest\b', r'\bflask\b', r'\bdjango\b', r'\bfastapi\b'],
            "javascript": [r'\bnpm\b', r'\bnode\b', r'\byarn\b', r'\bpackage\.json\b'],
            "go": [r'\bgo\s+build\b', r'\bgo\s+test\b', r'\bgo\s+mod\b', r'\bgolang\b'],
            "rust": [r'\bcargo\b', r'\brustc\b'],
            "ruby": [r'\bbundle\b', r'\bgem\b', r'\bruby\b'],
            "php": [r'\bcomposer\b', r'\bphp\b'],
            "scala": [r'\bsbt\b', r'\bscala\b'],
            "csharp": [r'\bdotnet\b', r'\bnuget\b'],
            "typescript": [r'\btsc\b', r'\btypescript\b'],
        }
        for lang, pats in patterns.items():
            for pat in pats:
                if re.search(pat, content):
                    return lang
        return None

    async def convert(
        self,
        pipeline_content: str,
        source_format: str,
        target_format: str,
        language: Optional[str] = None,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """Convert pipeline content from source to target format."""
        if source_format not in FORMATS:
            return {"success": False, "error": f"Unknown source format: {source_format}"}
        if target_format not in FORMATS:
            return {"success": False, "error": f"Unknown target format: {target_format}"}
        if source_format == target_format:
            return {"success": False, "error": "Source and target formats are the same"}

        if not language:
            language = self.detect_language(pipeline_content)

        # Template path: use default templates for known languages
        if language and language in ALL_TEMPLATE_LANGUAGES and not use_llm:
            try:
                return self._convert_via_template(language, source_format, target_format)
            except Exception:
                # Fall through to LLM if template fails
                pass

        # LLM path
        return await self._convert_via_llm(pipeline_content, source_format, target_format, language)

    def _convert_via_template(self, language: str, source_format: str, target_format: str) -> Dict[str, Any]:
        """Convert using built-in default templates."""
        analysis = {"language": language}
        converted = ""
        dockerfile = ""

        if target_format == "gitlab":
            from app.services.pipeline.default_templates import _get_default_gitlab_ci, _get_default_dockerfile
            converted = _get_default_gitlab_ci(analysis)
            dockerfile = _get_default_dockerfile(analysis)
        elif target_format == "jenkins":
            from app.services.jenkins_pipeline.default_templates import _get_default_jenkinsfile, _get_default_dockerfile
            converted = _get_default_jenkinsfile(analysis)
            dockerfile = _get_default_dockerfile(analysis)
        elif target_format == "github-actions":
            from app.services.github_pipeline.default_templates import _get_default_workflow, _get_default_dockerfile
            converted = _get_default_workflow(analysis)
            dockerfile = _get_default_dockerfile(analysis)

        if not converted:
            raise ValueError(f"No template available for {language} in {target_format}")

        result = {
            "success": True,
            "method": "template",
            "converted": converted,
            "language": language,
            "source_format": source_format,
            "target_format": target_format,
        }
        if dockerfile:
            result["dockerfile"] = dockerfile
        return result

    async def _convert_via_llm(
        self, pipeline_content: str, source_format: str, target_format: str, language: Optional[str]
    ) -> Dict[str, Any]:
        """Convert using LLM."""
        format_names = {"gitlab": "GitLab CI (.gitlab-ci.yml)", "jenkins": "Jenkins (Declarative Jenkinsfile)", "github-actions": "GitHub Actions (workflow YAML)"}

        prompt = f"""Convert the following {format_names.get(source_format, source_format)} pipeline to {format_names.get(target_format, target_format)} format.

{f"Detected language: {language}" if language else "Language: unknown (infer from content)"}

Source pipeline:
```
{pipeline_content}
```

Output only the converted pipeline configuration."""

        provider = get_llm_provider()
        try:
            result = await provider.generate(
                model=None,
                prompt=prompt,
                system=MIGRATION_SYSTEM_PROMPT,
                context=None,
                options={"temperature": 0.2, "num_predict": 5000},
            )
            converted = result.get("response", "")

            # Strip code fences if present
            converted = re.sub(r'^```\w*\n', '', converted)
            converted = re.sub(r'\n```\s*$', '', converted)

            return {
                "success": True,
                "method": "llm",
                "converted": converted.strip(),
                "language": language,
                "source_format": source_format,
                "target_format": target_format,
            }
        except Exception as e:
            return {"success": False, "error": f"LLM conversion failed: {e}"}
        finally:
            await provider.close()

    def get_supported_languages(self) -> Dict[str, Any]:
        """Return which languages each format supports via templates."""
        return {
            "success": True,
            "formats": {
                "gitlab": ["java", "python", "javascript", "go", "scala", "php", "rust"],
                "jenkins": ["java", "kotlin", "scala", "python", "django", "flask", "fastapi",
                            "javascript", "typescript", "go", "rust", "ruby", "php", "csharp", "dotnet"],
                "github-actions": ["java", "python", "javascript", "go"],
            },
        }
