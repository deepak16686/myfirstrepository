"""
Jenkins Pipeline Generator Service - Facade Class.

Main orchestration class that delegates to specialized modules.
Mirrors the GitLab pipeline generator pattern with full RL feedback,
image seeding, and LLM-based iterative fixing.
"""
import os
import re
from typing import Dict, Any, Optional, List

from app.config import settings
from app.integrations.llm_provider import get_llm_provider, get_active_provider_name

from app.services.jenkins_pipeline.analyzer import (
    parse_repo_url,
    analyze_repository,
    _detect_language,
    _detect_framework,
    _detect_package_manager,
)
from app.services.jenkins_pipeline.templates import (
    _ensure_learn_stage,
    get_reference_jenkinsfile,
    get_best_template_files,
)
from app.services.jenkins_pipeline.validator import (
    _validate_and_fix_jenkinsfile,
    _validate_and_fix_dockerfile,
)
from app.services.jenkins_pipeline.default_templates import (
    _get_default_jenkinsfile,
    _get_default_dockerfile,
    _get_java_jenkinsfile_template,
    _get_python_jenkinsfile_template,
    _get_nodejs_jenkinsfile_template,
    _get_go_jenkinsfile_template,
    _get_rust_jenkinsfile_template,
    _get_ruby_jenkinsfile_template,
    _get_php_jenkinsfile_template,
    _get_scala_jenkinsfile_template,
    _get_csharp_jenkinsfile_template,
)
from app.services.jenkins_pipeline.learning import (
    get_relevant_feedback,
    store_feedback,
    store_successful_pipeline,
    record_build_result as learning_record_build_result,
    compare_and_learn,
)
from app.services.jenkins_pipeline.image_seeder import ensure_images_in_nexus
from app.services.jenkins_pipeline.committer import commit_to_repo
from app.services.jenkins_pipeline.status import (
    get_build_status,
    get_build_stages,
    trigger_build,
    trigger_scan,
    record_build_result,
)
from app.services.jenkins_llm_fixer import jenkins_llm_fixer
from app.services.jenkins_pipeline.constants import (
    FEEDBACK_COLLECTION,
    TEMPLATES_COLLECTION,
    SUCCESSFUL_PIPELINES_COLLECTION,
    DEFAULT_MODEL,
)


class JenkinsPipelineGeneratorService:
    """
    Service for generating Jenkinsfile (Declarative Pipeline) with RL feedback.

    Supports:
    - Multiple languages: Java, Python, Node.js, Go, Rust, Ruby, PHP, Scala, C#
    - 7-stage pipeline + post block (notify + learn)
    - Nexus private registry integration
    - ChromaDB template storage for RL
    - Jenkins credentials store integration
    - Docker Pipeline plugin for image builds
    - Image seeding to Nexus registry
    - LLM-based iterative fixing
    - Reinforcement learning from successful builds
    """

    FEEDBACK_COLLECTION = FEEDBACK_COLLECTION
    TEMPLATES_COLLECTION = TEMPLATES_COLLECTION
    SUCCESSFUL_PIPELINES_COLLECTION = SUCCESSFUL_PIPELINES_COLLECTION
    DEFAULT_MODEL = DEFAULT_MODEL

    REQUIRED_STAGES = [
        'Compile', 'Build Image', 'Test Image', 'Static Analysis',
        'SonarQube', 'Trivy Scan', 'Push Release'
    ]

    def __init__(self):
        self.jenkins_url = settings.jenkins_url
        self.jenkins_username = settings.jenkins_username
        self.jenkins_password = settings.jenkins_password
        self.chromadb_url = settings.chromadb_url
        self.ollama_url = settings.ollama_url

    # --- Delegation to analyzer module ---

    def parse_repo_url(self, url: str) -> Dict[str, str]:
        """Parse repository URL to extract project info"""
        return parse_repo_url(url)

    async def analyze_repository(
        self,
        repo_url: str,
        git_token: str
    ) -> Dict[str, Any]:
        """Analyze repository to detect language, framework, and structure"""
        return await analyze_repository(repo_url, git_token)

    def _detect_language(self, files):
        return _detect_language(files)

    def _detect_framework(self, files):
        return _detect_framework(files)

    def _detect_package_manager(self, files):
        return _detect_package_manager(files)

    # --- Delegation to templates module ---

    def _ensure_learn_stage(self, jenkinsfile: str) -> str:
        """Ensure the learn-record curl exists in post block"""
        return _ensure_learn_stage(jenkinsfile)

    async def get_reference_jenkinsfile(
        self,
        language: str,
        framework: Optional[str] = None
    ) -> Optional[str]:
        """Get reference Jenkinsfile from ChromaDB"""
        return await get_reference_jenkinsfile(language, framework)

    async def get_best_template_files(
        self,
        language: str,
        framework: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """Get the best performing template from successful pipelines"""
        return await get_best_template_files(language, framework)

    # --- Delegation to validator module ---

    def _validate_and_fix_jenkinsfile(
        self,
        jenkinsfile: str,
        reference: Optional[str]
    ) -> str:
        return _validate_and_fix_jenkinsfile(jenkinsfile, reference)

    def _validate_and_fix_dockerfile(self, dockerfile: str, language: str) -> str:
        return _validate_and_fix_dockerfile(dockerfile, language)

    # --- Delegation to default_templates module ---

    def _get_default_jenkinsfile(self, analysis: Dict[str, Any], agent_label: str = "docker") -> str:
        return _get_default_jenkinsfile(analysis, agent_label)

    def _get_java_jenkinsfile_template(self, agent_label: str = "docker") -> str:
        return _get_java_jenkinsfile_template(agent_label)

    def _get_python_jenkinsfile_template(self, agent_label: str = "docker") -> str:
        return _get_python_jenkinsfile_template(agent_label)

    def _get_nodejs_jenkinsfile_template(self, agent_label: str = "docker") -> str:
        return _get_nodejs_jenkinsfile_template(agent_label)

    def _get_go_jenkinsfile_template(self, agent_label: str = "docker") -> str:
        return _get_go_jenkinsfile_template(agent_label)

    def _get_default_dockerfile(self, analysis: Dict[str, Any]) -> str:
        return _get_default_dockerfile(analysis)

    # --- Delegation to committer module ---

    async def commit_to_repo(
        self,
        repo_url: str,
        git_token: str,
        jenkinsfile: str,
        dockerfile: str,
        branch_name: Optional[str] = None,
        commit_message: str = "Add Jenkinsfile and Dockerfile [AI Generated]"
    ) -> Dict[str, Any]:
        """Commit Jenkinsfile and Dockerfile to Gitea repository"""
        return await commit_to_repo(
            repo_url, git_token, jenkinsfile, dockerfile,
            branch_name, commit_message
        )

    # --- Delegation to status module ---

    async def get_build_status(
        self,
        job_name: str,
        build_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get Jenkins build status"""
        return await get_build_status(job_name, build_number)

    async def trigger_build(self, job_name: str) -> Dict[str, Any]:
        """Trigger a Jenkins build"""
        return await trigger_build(job_name)

    async def trigger_scan(self, project_name: str) -> Dict[str, Any]:
        """Trigger a multibranch pipeline branch scan"""
        return await trigger_scan(project_name)

    async def get_build_stages(
        self, job_name: str, build_number: Optional[int] = None
    ) -> list:
        """Get build stage details from workflow API"""
        return await get_build_stages(job_name, build_number)

    async def record_build_result(
        self,
        job_name: str,
        build_number: int,
        status: str = "success"
    ) -> Dict[str, Any]:
        """Record build result for RL (basic - status module)"""
        return await record_build_result(job_name, build_number, status)

    # --- Delegation to learning module ---

    async def get_relevant_feedback(
        self, language: str, framework: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get relevant RL feedback from ChromaDB"""
        return await get_relevant_feedback(language, framework, limit)

    async def store_feedback(
        self,
        original_jenkinsfile: str,
        corrected_jenkinsfile: str,
        original_dockerfile: str,
        corrected_dockerfile: str,
        language: str,
        framework: str,
        error_type: str,
        fix_description: str
    ) -> bool:
        """Store correction feedback for RL"""
        return await store_feedback(
            original_jenkinsfile, corrected_jenkinsfile,
            original_dockerfile, corrected_dockerfile,
            language, framework, error_type, fix_description
        )

    async def learning_record_build(
        self,
        repo_url: str,
        git_token: str,
        branch: str,
        job_name: str,
        build_number: int
    ) -> Dict[str, Any]:
        """Record build result with actual file fetching for RL"""
        return await learning_record_build_result(
            repo_url, git_token, branch, job_name, build_number
        )

    async def store_successful_pipeline(
        self,
        job_name: str,
        build_number: int,
        jenkinsfile_content: str,
        dockerfile_content: str,
        language: str,
        framework: str,
        duration: Optional[int] = None,
        stages_passed: Optional[List[str]] = None
    ) -> bool:
        """Store a successful pipeline config in ChromaDB for RL"""
        return await store_successful_pipeline(
            job_name, build_number, jenkinsfile_content, dockerfile_content,
            language, framework, duration, stages_passed
        )

    async def compare_and_learn(
        self,
        repo_url: str,
        git_token: str,
        branch: str,
        generated_files: Dict[str, str]
    ) -> Dict[str, Any]:
        """Compare current files with generated and learn from differences"""
        return await compare_and_learn(repo_url, git_token, branch, generated_files)

    # --- Core generation methods ---

    async def generate_pipeline_files(
        self,
        repo_url: str,
        git_token: str,
        additional_context: str = "",
        model: str = None,
        use_template_only: bool = False,
        agent_label: str = "docker"
    ) -> Dict[str, Any]:
        """
        Generate Jenkinsfile and Dockerfile for a repository.

        Priority:
        1. Use proven successful template from ChromaDB (if exists)
        2. Use default template if template_only requested
        3. Use LLM to generate with reference template
        4. Fall back to default templates
        """
        # Analyze repository
        analysis = await self.analyze_repository(repo_url, git_token)
        language = analysis["language"]
        framework = analysis["framework"]

        print(f"[Jenkins Pipeline] Analyzing {repo_url}: {language}/{framework}")

        # Priority 1: Check for proven successful template
        best_template = await self.get_best_template_files(language, framework)
        if best_template and best_template.get("jenkinsfile"):
            print(f"[Jenkins Pipeline] Using proven template from ChromaDB")
            jenkinsfile = self._ensure_learn_stage(best_template["jenkinsfile"])

            # Auto-seed any missing images into Nexus
            await self._seed_images(jenkinsfile)

            return {
                "success": True,
                "jenkinsfile": jenkinsfile,
                "dockerfile": best_template.get("dockerfile", self._get_default_dockerfile(analysis)),
                "analysis": analysis,
                "model_used": "chromadb-successful",
                "feedback_used": 0,
                "template_source": "reinforcement_learning"
            }

        # Priority 2: Use template only if requested
        if use_template_only:
            jenkinsfile = self._get_default_jenkinsfile(analysis, agent_label)
            dockerfile = self._get_default_dockerfile(analysis)
            return {
                "success": True,
                "jenkinsfile": self._ensure_learn_stage(jenkinsfile),
                "dockerfile": dockerfile,
                "analysis": analysis,
                "model_used": "default-template",
                "feedback_used": 0
            }

        # Priority 3: Try LLM generation with RL feedback
        try:
            reference = await self.get_reference_jenkinsfile(language, framework)

            # Get relevant RL feedback from previous corrections
            feedback = await self.get_relevant_feedback(language, framework)

            generated = await self._generate_with_llm(
                analysis, reference, additional_context,
                model or self.DEFAULT_MODEL, feedback
            )

            if generated:
                jenkinsfile = self._validate_and_fix_jenkinsfile(
                    generated.get("jenkinsfile", ""), reference
                )
                dockerfile = self._validate_and_fix_dockerfile(
                    generated.get("dockerfile", ""), language
                )

                # Auto-seed any missing images into Nexus
                jenkinsfile = self._ensure_learn_stage(jenkinsfile)
                await self._seed_images(jenkinsfile)

                return {
                    "success": True,
                    "jenkinsfile": jenkinsfile,
                    "dockerfile": dockerfile,
                    "analysis": analysis,
                    "model_used": get_active_provider_name(),
                    "feedback_used": len(feedback)
                }
        except Exception as e:
            print(f"[Jenkins Pipeline] LLM generation failed: {e}")

        # Fallback: Use default templates
        jenkinsfile = self._get_default_jenkinsfile(analysis, agent_label)
        dockerfile = self._get_default_dockerfile(analysis)
        jenkinsfile = self._ensure_learn_stage(jenkinsfile)

        # Auto-seed images for default templates too
        await self._seed_images(jenkinsfile)

        return {
            "success": True,
            "jenkinsfile": jenkinsfile,
            "dockerfile": dockerfile,
            "analysis": analysis,
            "model_used": "default-template",
            "feedback_used": 0
        }

    async def _generate_with_llm(
        self,
        analysis: Dict[str, Any],
        reference: Optional[str],
        additional_context: str,
        model: str,
        feedback: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, str]]:
        """Generate Jenkinsfile using configured LLM provider"""
        prompt = self._build_generation_prompt(
            analysis, reference, additional_context, feedback
        )

        try:
            llm = get_llm_provider()
            response = await llm.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 6000
                }
            )
            await llm.close()

            generated_text = response.get("response", "")
            return self._parse_llm_output(generated_text)

        except Exception as e:
            print(f"[LLM] Error: {e}")

        return None

    def _build_generation_prompt(
        self,
        analysis: Dict[str, Any],
        reference: Optional[str],
        additional_context: str,
        feedback: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build prompt for LLM generation with RL feedback context"""
        # Try to load system prompt from file
        system_prompt = ""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "prompts", "jenkins_system_prompt.txt"
        )
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r') as f:
                system_prompt = f.read()

        prompt = f"""{system_prompt}

Generate a Jenkinsfile (Declarative Pipeline) and Dockerfile for a {analysis['language']} project.

Project Analysis:
- Language: {analysis['language']}
- Framework: {analysis['framework']}
- Package Manager: {analysis['package_manager']}

Requirements:
- Use Nexus private registry for ALL images: ${{NEXUS_REGISTRY}}/apm-repo/demo/<image>
- Use Jenkins Declarative Pipeline syntax
- IMPORTANT: Use "agent {{ label 'docker' }}" at the pipeline level (NOT "agent any" or "agent {{ label 'any' }}")
- For per-stage Docker image agents use: agent {{ docker {{ image "${{NEXUS_REGISTRY}}/apm-repo/demo/<image>:<tag>"; registryUrl "http://${{NEXUS_REGISTRY}}"; registryCredentialsId 'nexus-credentials'; reuseNode true }} }}
- IMPORTANT: Nexus registry is HTTP-ONLY. Use "http://${{NEXUS_REGISTRY}}" everywhere (NEVER "https://")
- IMPORTANT: docker.build() MUST pass --build-arg: docker.build("${{NEXUS_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}}", "--build-arg BASE_REGISTRY=${{NEXUS_REGISTRY}} .")
- IMPORTANT: Dockerfile must use ARG BASE_REGISTRY=localhost:5001 (NOT ai-nexus:5001)
- Include ALL 9 stages: Compile, Build Image, Test Image, Static Analysis, SonarQube, Trivy Scan, Push Release, Notify, Learn
- Notify stage: curl to Splunk HEC with success event (message, pipeline, project, status, image, sourcetype, source)
- Learn stage: curl to devops backend /api/v1/jenkins-pipeline/learn/record with job_name, build_number, status, image, tag
- Post block: failure (Splunk notify failure as safety net) + always (cleanWs()). Do NOT put notify/learn in post block
- Use Docker Pipeline plugin for building images (docker.withRegistry / docker.build)
- Use credentials() for all secrets in environment block
"""

        if reference:
            prompt += f"""
## MANDATORY REFERENCE TEMPLATE - USE THIS EXACT STRUCTURE
The following is a PROVEN, WORKING Jenkinsfile template. You MUST use this as your base
and ONLY modify language-specific parts.

```groovy
{reference}
```
"""

        # Include RL feedback from previous corrections
        if feedback:
            prompt += "\n## LEARNED CORRECTIONS (Apply these fixes):\n"
            for i, fb in enumerate(feedback, 1):
                prompt += f"""
### Fix {i}: {fb.get('error_type', 'N/A')}
- Problem: {fb.get('feedback', 'N/A')}
- Solution: {fb.get('fix_description', 'N/A')}
"""

        if additional_context:
            prompt += f"\nAdditional context: {additional_context}\n"

        prompt += """
Output format:
---JENKINSFILE---
(complete Jenkinsfile content)
---DOCKERFILE---
(complete Dockerfile content)
---END---
"""
        return prompt

    def _parse_llm_output(self, text: str) -> Optional[Dict[str, str]]:
        """Parse LLM output to extract Jenkinsfile and Dockerfile"""
        result = {}

        # Extract Jenkinsfile between markers
        jenkinsfile_match = re.search(
            r'---JENKINSFILE---\s*(.*?)\s*(?:---DOCKERFILE---|---END---)',
            text, re.DOTALL
        )
        if jenkinsfile_match:
            jf = self._strip_code_block(jenkinsfile_match.group(1).strip())
            # Fix incorrect agent label - LLM sometimes generates 'any' instead of 'docker'
            jf = re.sub(r"agent\s*\{\s*label\s*'any'\s*\}", "agent { label 'docker' }", jf)
            # Fix HTTPS → HTTP for Nexus (HTTP-only registry)
            jf = jf.replace('https://${NEXUS_REGISTRY}', 'http://${NEXUS_REGISTRY}')
            result["jenkinsfile"] = jf

        # Extract Dockerfile between markers
        dockerfile_match = re.search(
            r'---DOCKERFILE---\s*(.*?)\s*---END---',
            text, re.DOTALL
        )
        if dockerfile_match:
            df = self._strip_code_block(dockerfile_match.group(1).strip())
            # Fix container DNS → localhost for host Docker daemon
            df = df.replace('ai-nexus:5001', 'localhost:5001')
            result["dockerfile"] = df

        # Fallback: try code block extraction
        if not result.get("jenkinsfile"):
            groovy_match = re.search(r'```groovy\s*(.*?)\s*```', text, re.DOTALL)
            if groovy_match:
                jf = groovy_match.group(1).strip()
                jf = re.sub(r"agent\s*\{\s*label\s*'any'\s*\}", "agent { label 'docker' }", jf)
                jf = jf.replace('https://${NEXUS_REGISTRY}', 'http://${NEXUS_REGISTRY}')
                result["jenkinsfile"] = jf

        if not result.get("dockerfile"):
            docker_match = re.search(r'```dockerfile\s*(.*?)\s*```', text, re.DOTALL)
            if docker_match:
                df = docker_match.group(1).strip()
                df = df.replace('ai-nexus:5001', 'localhost:5001')
                result["dockerfile"] = df

        return result if result else None

    @staticmethod
    def _strip_code_block(content: str) -> str:
        """Strip markdown code block markers from extracted content."""
        content = re.sub(r'^```\w*\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        return content.strip()

    async def _seed_images(self, jenkinsfile: str) -> None:
        """Auto-seed any missing Docker images into Nexus. Best-effort."""
        try:
            print("[Jenkins ImageSeeder] Running image seeder...")
            seed_result = await ensure_images_in_nexus(jenkinsfile)
            if seed_result.get('seeded'):
                print(f"[Jenkins ImageSeeder] Seeded {len(seed_result['seeded'])} images: {seed_result['seeded']}")
            if seed_result.get('failed'):
                print(f"[Jenkins ImageSeeder] Failed to seed: {seed_result['failed']}")
        except Exception as e:
            print(f"[Jenkins ImageSeeder] Warning: {e}")

    async def generate_with_validation(
        self,
        repo_url: str,
        git_token: str,
        additional_context: str = "",
        model: str = None,
        max_fix_attempts: int = 10,
        agent_label: str = "docker"
    ) -> Dict[str, Any]:
        """
        Generate pipeline files with validation and automatic LLM fixing.

        Flow:
        1. Generate Jenkinsfile + Dockerfile
        2. If from proven template, skip validation
        3. Validate using text-based checks
        4. If validation fails, use LLM fixer iteratively
        5. Auto-seed images into Nexus

        Returns dict with pipeline files, validation results, and metadata.
        """
        model = model or self.DEFAULT_MODEL

        # Step 1: Generate initial pipeline
        print(f"[Jenkins Validation Flow] Generating pipeline for {repo_url}...")
        result = await self.generate_pipeline_files(
            repo_url=repo_url,
            git_token=git_token,
            additional_context=additional_context,
            model=model,
            use_template_only=False,
            agent_label=agent_label
        )

        jenkinsfile = result.get('jenkinsfile', '')
        dockerfile = result.get('dockerfile', '')
        analysis = result.get('analysis', {})

        # If template was used directly from ChromaDB, skip validation
        if result.get('template_source') == 'reinforcement_learning':
            print("[Jenkins Validation Flow] Using proven template from RL - skipping validation")
            return {
                **result,
                'validation_skipped': True,
                'validation_reason': 'Template from reinforcement learning (already validated)'
            }

        # Step 2: Run LLM fixer iterative validation
        print("[Jenkins Validation Flow] Running iterative validation and fixing...")
        fix_result = await jenkins_llm_fixer.iterative_fix(
            jenkinsfile=jenkinsfile,
            dockerfile=dockerfile,
            analysis=analysis,
            max_attempts=max_fix_attempts,
            model=model
        )

        if fix_result.get('success'):
            final_jenkinsfile = fix_result.get('jenkinsfile', jenkinsfile)
            final_dockerfile = fix_result.get('dockerfile', dockerfile)

            print(f"[Jenkins Validation Flow] Pipeline valid after {fix_result.get('attempts', 1)} attempt(s)")

            # Auto-seed images
            await self._seed_images(final_jenkinsfile)

            return {
                'success': True,
                'jenkinsfile': final_jenkinsfile,
                'dockerfile': final_dockerfile,
                'analysis': analysis,
                'model_used': get_active_provider_name(),
                'feedback_used': result.get('feedback_used', 0),
                'validation_passed': True,
                'fix_attempts': fix_result.get('attempts', 1),
                'fix_history': fix_result.get('fix_history', []),
                'has_warnings': fix_result.get('has_warnings', False)
            }
        else:
            # Could not fix - return best effort
            print(f"[Jenkins Validation Flow] Could not fix after {max_fix_attempts} attempts")
            final_jenkinsfile = fix_result.get('jenkinsfile', jenkinsfile)

            # Still seed images for the best-effort result
            await self._seed_images(final_jenkinsfile)

            return {
                'success': False,
                'jenkinsfile': final_jenkinsfile,
                'dockerfile': fix_result.get('dockerfile', dockerfile),
                'analysis': analysis,
                'model_used': get_active_provider_name(),
                'feedback_used': result.get('feedback_used', 0),
                'validation_passed': False,
                'validation_errors': fix_result.get('final_errors', []),
                'fix_attempts': fix_result.get('attempts', max_fix_attempts),
                'fix_history': fix_result.get('fix_history', [])
            }
