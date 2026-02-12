"""
Terraform Generator Service - Facade Class.

Main orchestration class that delegates to specialized modules.
Mirrors the Jenkins pipeline generator pattern with full RL feedback,
template storage, and LLM-based generation.
"""
import os
import re
from typing import Dict, Any, Optional, List

from app.config import settings
from app.integrations.llm_provider import get_llm_provider

from app.services.terraform.analyzer import (
    build_context_description,
    get_provider_config,
    get_resource_requirements,
)
from app.services.terraform.templates import (
    get_reference_terraform,
    get_best_template_files,
)
from app.services.terraform.validator import validate_terraform_files
from app.services.terraform.default_templates import get_default_terraform_files
from app.services.terraform.learning import (
    get_relevant_feedback,
    store_feedback,
    store_successful_config,
)
from app.services.terraform.constants import DEFAULT_MODEL


class TerraformGeneratorService:
    """
    Service for generating Terraform HCL configurations with RL feedback.

    Supports:
    - 4 cloud providers: vSphere, Azure, AWS, GCP
    - 4 resource types: VMs, Kubernetes, Containers, Networking
    - VM sub-types: Linux, Windows
    - ChromaDB template storage for RL
    - LLM-based generation with iterative fixing
    """

    async def generate_terraform_files(
        self,
        provider: str,
        resource_type: str,
        sub_type: Optional[str] = None,
        additional_requirements: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        use_template_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate Terraform configuration files.

        Priority:
        1. Proven successful template from ChromaDB
        2. LLM generation with reference template + RL feedback
        3. Default hardcoded template fallback
        """
        context_desc = build_context_description(provider, resource_type, sub_type)
        print(f"[Terraform] Generating config for: {context_desc}")

        # Priority 1: Check ChromaDB for proven successful config
        try:
            best_template = await get_best_template_files(provider, resource_type, sub_type)
            if best_template and best_template.get("main.tf"):
                print(f"[Terraform] Found proven template in ChromaDB for {provider}/{resource_type}")
                return {
                    "success": True,
                    "files": {
                        "provider.tf": best_template.get("provider.tf", ""),
                        "main.tf": best_template.get("main.tf", ""),
                        "variables.tf": best_template.get("variables.tf", ""),
                        "outputs.tf": best_template.get("outputs.tf", ""),
                        "terraform.tfvars.example": best_template.get("terraform.tfvars.example", ""),
                    },
                    "model_used": "chromadb-successful",
                    "feedback_used": 0,
                    "context": context_desc,
                }
        except Exception as e:
            print(f"[Terraform] ChromaDB lookup failed: {e}")

        # Priority 2: Use default template only (if requested)
        if use_template_only:
            try:
                files = get_default_terraform_files(provider, resource_type, sub_type)
                return {
                    "success": True,
                    "files": files,
                    "model_used": "default-template",
                    "feedback_used": 0,
                    "context": context_desc,
                }
            except Exception as e:
                return {"success": False, "error": f"Default template error: {e}"}

        # Priority 3: LLM generation with reference
        try:
            result = await self._generate_with_llm(
                provider, resource_type, sub_type,
                additional_requirements, model,
            )
            if result.get("success"):
                return result
        except Exception as e:
            print(f"[Terraform] LLM generation failed: {e}")

        # Priority 4: Fallback to default template
        try:
            files = get_default_terraform_files(provider, resource_type, sub_type)
            return {
                "success": True,
                "files": files,
                "model_used": "default-template",
                "feedback_used": 0,
                "context": context_desc,
            }
        except Exception as e:
            return {"success": False, "error": f"All generation methods failed: {e}"}

    async def generate_with_validation(
        self,
        provider: str,
        resource_type: str,
        sub_type: Optional[str] = None,
        additional_requirements: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_fix_attempts: int = 5,
    ) -> Dict[str, Any]:
        """Generate Terraform files with validation and optional fix loop."""
        # Generate initial files
        result = await self.generate_terraform_files(
            provider, resource_type, sub_type,
            additional_requirements, model,
        )

        if not result.get("success"):
            return result

        files = result["files"]

        # If from proven ChromaDB template, skip validation
        if result.get("model_used") == "chromadb-successful":
            result["validation_passed"] = True
            result["validation_skipped"] = True
            return result

        # Run text-based validation
        errors, warnings = validate_terraform_files(
            files, provider, resource_type, sub_type,
        )

        result["validation_errors"] = errors
        result["validation_warnings"] = warnings
        result["validation_passed"] = len(errors) == 0

        if errors and max_fix_attempts > 0:
            # Import here to avoid circular dependency
            from app.services.terraform_llm_fixer import terraform_llm_fixer
            fix_result = await terraform_llm_fixer.iterative_fix(
                files=files,
                provider=provider,
                resource_type=resource_type,
                sub_type=sub_type,
                max_attempts=max_fix_attempts,
                model=model,
            )
            if fix_result.get("success"):
                result["files"] = fix_result["files"]
                result["validation_passed"] = True
                result["fix_attempts"] = fix_result.get("attempts", 0)
                result["validation_errors"] = []

        return result

    async def _generate_with_llm(
        self,
        provider: str,
        resource_type: str,
        sub_type: Optional[str] = None,
        additional_requirements: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:
        """Generate Terraform files using LLM."""
        context_desc = build_context_description(provider, resource_type, sub_type)

        # Get reference template and RL feedback
        reference = await get_reference_terraform(provider, resource_type, sub_type)
        feedback = await get_relevant_feedback(provider, resource_type, limit=3)

        # Get resource-specific requirements
        requirements = get_resource_requirements(provider, resource_type, sub_type)
        provider_config = get_provider_config(provider)

        # Get default template as additional reference
        try:
            default_files = get_default_terraform_files(provider, resource_type, sub_type)
            default_ref = f"\n\n## DEFAULT TEMPLATE REFERENCE (use as starting point):\n"
            for fname, content in default_files.items():
                default_ref += f"\n### {fname}:\n```hcl\n{content}\n```\n"
        except Exception:
            default_ref = ""

        # Build prompt
        prompt = self._build_generation_prompt(
            provider, resource_type, sub_type,
            additional_requirements, reference, feedback,
            requirements, provider_config, default_ref,
        )

        # Load system prompt
        system_prompt = self._load_system_prompt()

        # Call LLM
        llm = get_llm_provider()
        try:
            response = await llm.generate(
                model=model,
                prompt=prompt,
                system=system_prompt,
                options={"temperature": 0.1, "num_predict": 8000},
            )
        finally:
            await llm.close()

        llm_output = response.get("response", "")
        if not llm_output:
            return {"success": False, "error": "Empty LLM response"}

        # Parse output
        files = self._parse_llm_output(llm_output)
        if not files or not files.get("main.tf"):
            return {"success": False, "error": "Could not parse LLM output into .tf files"}

        return {
            "success": True,
            "files": files,
            "model_used": model,
            "feedback_used": len(feedback),
            "context": context_desc,
        }

    def _build_generation_prompt(
        self,
        provider: str,
        resource_type: str,
        sub_type: Optional[str],
        additional_requirements: Optional[str],
        reference: Optional[str],
        feedback: List[Dict[str, Any]],
        requirements: Dict[str, Any],
        provider_config: Dict[str, Any],
        default_ref: str,
    ) -> str:
        """Build the full generation prompt for the LLM."""
        parts = []

        parts.append(f"## TASK: Generate Terraform configuration for {requirements['description']}")
        parts.append(f"\nProvider: {provider_config['name']} ({provider_config['source']} {provider_config['version']})")
        parts.append(f"Resource Type: {resource_type}")
        if sub_type:
            parts.append(f"Sub Type: {sub_type}")

        # Requirements/hints
        if requirements.get("notes"):
            parts.append("\n## REQUIREMENTS:")
            for note in requirements["notes"]:
                parts.append(f"- {note}")

        # Additional user requirements
        if additional_requirements:
            parts.append(f"\n## ADDITIONAL USER REQUIREMENTS:\n{additional_requirements}")

        # RL feedback
        if feedback:
            parts.append("\n## LEARNED CORRECTIONS (apply these fixes):")
            for fb in feedback:
                parts.append(f"- Error: {fb.get('error_type', 'N/A')} | Fix: {fb.get('fix_description', fb.get('feedback', '')[:200])}")

        # Reference template
        if reference:
            parts.append(f"\n## REFERENCE TEMPLATE (use as guidance):\n{reference[:2000]}")

        # Default template reference
        if default_ref:
            parts.append(default_ref)

        parts.append("\n## OUTPUT: Generate all 5 files using the marker format specified in the system prompt.")

        return "\n".join(parts)

    def _load_system_prompt(self) -> str:
        """Load the Terraform system prompt from file."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "prompts",
            "terraform_system_prompt.txt",
        )
        try:
            with open(prompt_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "You are an expert Terraform engineer. Generate valid HCL configurations."

    def _parse_llm_output(self, text: str) -> Optional[Dict[str, str]]:
        """Extract .tf files from LLM output using markers."""
        files = {}

        marker_map = {
            "---PROVIDER_TF---": "provider.tf",
            "---MAIN_TF---": "main.tf",
            "---VARIABLES_TF---": "variables.tf",
            "---OUTPUTS_TF---": "outputs.tf",
            "---TFVARS_EXAMPLE---": "terraform.tfvars.example",
        }

        markers = list(marker_map.keys()) + ["---END---"]

        # Strategy 1: Marker-based extraction
        for i, (marker, filename) in enumerate(marker_map.items()):
            if marker in text:
                start = text.index(marker) + len(marker)
                # Find next marker
                end = len(text)
                for next_marker in markers:
                    if next_marker != marker and next_marker in text:
                        pos = text.index(next_marker)
                        if pos > start and pos < end:
                            end = pos
                content = text[start:end].strip()
                # Clean up markdown code blocks
                content = self._clean_code_block(content)
                if content:
                    files[filename] = content

        if files and files.get("main.tf"):
            return files

        # Strategy 2: Code block extraction
        code_blocks = re.findall(r'```(?:hcl|terraform)?\n(.*?)```', text, re.DOTALL)
        if len(code_blocks) >= 2:
            # Try to match blocks to files by content
            for block in code_blocks:
                block = block.strip()
                if 'terraform {' in block and 'required_providers' in block:
                    files["provider.tf"] = block
                elif 'resource ' in block or 'data ' in block:
                    if "main.tf" not in files:
                        files["main.tf"] = block
                elif 'variable ' in block:
                    files["variables.tf"] = block
                elif 'output ' in block:
                    files["outputs.tf"] = block

        return files if files.get("main.tf") else None

    def _clean_code_block(self, content: str) -> str:
        """Remove markdown code block markers."""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else ""
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        return content.strip()
