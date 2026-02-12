"""
Terraform LLM Fixer

Iterative fix loop for Terraform HCL configurations.
Validates using text-based checks and optionally terraform CLI,
then uses LLM to fix errors and retries.
"""
import os
import re
from typing import Dict, Any, Optional, List, Tuple

from app.config import settings
from app.integrations.llm_provider import get_llm_provider
from app.services.terraform.validator import validate_terraform_files
from app.services.terraform.workspace import workspace_manager
from app.services.terraform.executor import terraform_executor
from app.services.terraform.constants import DEFAULT_MODEL


class TerraformLLMFixer:
    """LLM-based iterative fixer for Terraform configurations."""

    FIX_MODEL = DEFAULT_MODEL

    async def fix_terraform(
        self,
        files: Dict[str, str],
        errors: List[str],
        warnings: List[str],
        provider: str,
        resource_type: str,
        sub_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Single LLM fix pass. Builds prompt with errors, calls LLM, parses response."""
        model = model or self.FIX_MODEL

        # Build fix prompt
        prompt = self._build_fix_prompt(files, errors, warnings, provider, resource_type, sub_type)

        # Load system prompt
        system_prompt = self._load_system_prompt()

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

        # Parse fixed files from response
        fixed_files = self._parse_fix_response(llm_output)
        if not fixed_files or not fixed_files.get("main.tf"):
            return {"success": False, "error": "Could not parse LLM fix output"}

        # Merge: only replace files that were in the fix response
        merged = dict(files)
        merged.update(fixed_files)

        return {"success": True, "files": merged}

    async def iterative_fix(
        self,
        files: Dict[str, str],
        provider: str,
        resource_type: str,
        sub_type: Optional[str] = None,
        max_attempts: int = 10,
        model: Optional[str] = None,
        terraform_tfvars: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Iterative fix loop:
        1. Text-validate files
        2. If errors, call LLM fix
        3. Optionally run terraform validate
        4. Repeat until success or max_attempts
        """
        current_files = dict(files)
        fix_history = []

        for attempt in range(1, max_attempts + 1):
            print(f"[Terraform Fixer] Attempt {attempt}/{max_attempts}")

            # Step 1: Text-based validation
            errors, warnings = validate_terraform_files(
                current_files, provider, resource_type, sub_type,
            )

            if errors:
                fix_history.append({
                    "attempt": attempt,
                    "stage": "text_validation",
                    "errors": errors,
                    "warnings": warnings,
                })

                fix_result = await self.fix_terraform(
                    current_files, errors, warnings,
                    provider, resource_type, sub_type, model,
                )
                if fix_result.get("success"):
                    current_files = fix_result["files"]
                continue

            # Step 2: Try terraform validate if available
            workspace_id = None
            try:
                workspace_id = workspace_manager.create(
                    provider, resource_type, current_files,
                )
                workspace_path = workspace_manager.get_path(workspace_id)

                if terraform_tfvars:
                    tfvars_path = os.path.join(workspace_path, "terraform.tfvars")
                    with open(tfvars_path, "w") as f:
                        f.write(terraform_tfvars)

                # terraform init
                init_result = await terraform_executor.init(workspace_path)
                if not init_result["success"]:
                    fix_history.append({
                        "attempt": attempt,
                        "stage": "terraform_init",
                        "errors": init_result["errors"],
                    })
                    fix_result = await self.fix_terraform(
                        current_files, init_result["errors"], [],
                        provider, resource_type, sub_type, model,
                    )
                    if fix_result.get("success"):
                        current_files = fix_result["files"]
                    continue

                # terraform validate
                validate_result = await terraform_executor.validate(workspace_path)
                if not validate_result["success"]:
                    fix_history.append({
                        "attempt": attempt,
                        "stage": "terraform_validate",
                        "errors": validate_result["errors"],
                    })
                    fix_result = await self.fix_terraform(
                        current_files, validate_result["errors"], validate_result.get("warnings", []),
                        provider, resource_type, sub_type, model,
                    )
                    if fix_result.get("success"):
                        current_files = fix_result["files"]
                    continue

                # Success!
                print(f"[Terraform Fixer] Validation passed on attempt {attempt}")
                return {
                    "success": True,
                    "files": current_files,
                    "attempts": attempt,
                    "fix_history": fix_history,
                }

            except Exception as e:
                print(f"[Terraform Fixer] Terraform CLI not available or error: {e}")
                # If terraform CLI is not available, text validation passing is good enough
                if not errors:
                    return {
                        "success": True,
                        "files": current_files,
                        "attempts": attempt,
                        "fix_history": fix_history,
                        "note": "Terraform CLI not available, text validation passed",
                    }
            finally:
                if workspace_id:
                    workspace_manager.cleanup(workspace_id)

        # Max attempts reached
        return {
            "success": False,
            "files": current_files,
            "attempts": max_attempts,
            "fix_history": fix_history,
            "error": f"Could not fix after {max_attempts} attempts",
        }

    def _build_fix_prompt(
        self,
        files: Dict[str, str],
        errors: List[str],
        warnings: List[str],
        provider: str,
        resource_type: str,
        sub_type: Optional[str],
    ) -> str:
        """Build the fix prompt with current files and errors."""
        parts = []
        parts.append(f"## FIX TERRAFORM CONFIGURATION")
        parts.append(f"Provider: {provider}, Resource: {resource_type}" + (f", SubType: {sub_type}" if sub_type else ""))
        parts.append("")

        parts.append("## CRITICAL ERRORS TO FIX:")
        for err in errors:
            parts.append(f"- ERROR: {err}")

        if warnings:
            parts.append("\n## WARNINGS:")
            for warn in warnings:
                parts.append(f"- WARNING: {warn}")

        parts.append("\n## CURRENT FILES:")
        for filename, content in files.items():
            if content.strip():
                parts.append(f"\n### {filename}:")
                parts.append(f"```hcl\n{content}\n```")

        parts.append("\n## INSTRUCTIONS:")
        parts.append("Fix ALL errors listed above. Keep the same structure and resources.")
        parts.append("Output the corrected files using the marker format from the system prompt.")
        parts.append("Do NOT remove any resources - only fix the errors.")

        return "\n".join(parts)

    def _load_system_prompt(self) -> str:
        """Load the Terraform system prompt."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "terraform_system_prompt.txt",
        )
        try:
            with open(prompt_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "You are an expert Terraform engineer. Fix the HCL configuration errors."

    def _parse_fix_response(self, text: str) -> Optional[Dict[str, str]]:
        """Parse LLM fix response into .tf files."""
        files = {}
        marker_map = {
            "---PROVIDER_TF---": "provider.tf",
            "---MAIN_TF---": "main.tf",
            "---VARIABLES_TF---": "variables.tf",
            "---OUTPUTS_TF---": "outputs.tf",
            "---TFVARS_EXAMPLE---": "terraform.tfvars.example",
        }

        markers = list(marker_map.keys()) + ["---END---"]

        for marker, filename in marker_map.items():
            if marker in text:
                start = text.index(marker) + len(marker)
                end = len(text)
                for next_marker in markers:
                    if next_marker != marker and next_marker in text:
                        pos = text.index(next_marker)
                        if pos > start and pos < end:
                            end = pos
                content = text[start:end].strip()
                content = self._clean_code_block(content)
                if content:
                    files[filename] = content

        if files:
            return files

        # Fallback: code block extraction
        code_blocks = re.findall(r'```(?:hcl|terraform)?\n(.*?)```', text, re.DOTALL)
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

        return files if files else None

    def _clean_code_block(self, content: str) -> str:
        """Remove markdown code block markers."""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else ""
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        return content.strip()


# Singleton instance
terraform_llm_fixer = TerraformLLMFixer()
