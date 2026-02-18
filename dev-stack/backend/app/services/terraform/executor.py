"""
File: executor.py
Purpose: Executes Terraform CLI commands (init, validate, plan, apply, destroy) as async subprocesses, parsing their output for errors, warnings, and resource change summaries.
When Used: Called by the TerraformLLMFixer during iterative validation, and by the Terraform router when users run plan/apply/destroy operations on a workspace.
Why Created: Wraps the terraform binary with async subprocess execution, timeout handling, and structured output parsing so that other modules can interact with Terraform CLI without dealing with raw process management.
"""
import asyncio
import json
import re
from typing import Dict, Any, Optional


class TerraformExecutor:
    """Execute terraform CLI commands in workspace directories."""

    def __init__(self, terraform_binary: str = "terraform"):
        self.binary = terraform_binary

    async def init(self, workspace_path: str) -> Dict[str, Any]:
        """Run terraform init in workspace."""
        result = await self._run_command(
            [self.binary, "init", "-no-color", "-input=false"],
            cwd=workspace_path,
            timeout=120,
        )
        return {
            "success": result["returncode"] == 0,
            "output": result["stdout"],
            "errors": self._extract_errors(result["stderr"] + result["stdout"]) if result["returncode"] != 0 else [],
        }

    async def validate(self, workspace_path: str) -> Dict[str, Any]:
        """Run terraform validate in workspace."""
        result = await self._run_command(
            [self.binary, "validate", "-no-color"],
            cwd=workspace_path,
            timeout=60,
        )
        return {
            "success": result["returncode"] == 0,
            "output": result["stdout"],
            "errors": self._extract_errors(result["stderr"] + result["stdout"]) if result["returncode"] != 0 else [],
            "warnings": self._extract_warnings(result["stdout"]),
        }

    async def plan(self, workspace_path: str, var_file: Optional[str] = None,
                   env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run terraform plan in workspace."""
        cmd = [self.binary, "plan", "-no-color", "-input=false", "-detailed-exitcode"]
        if var_file:
            cmd.extend(["-var-file", var_file])

        result = await self._run_command(cmd, cwd=workspace_path, timeout=300, env_vars=env_vars)

        # Exit codes: 0=no changes, 1=error, 2=changes present
        success = result["returncode"] in (0, 2)
        has_changes = result["returncode"] == 2

        return {
            "success": success,
            "has_changes": has_changes,
            "output": result["stdout"],
            "errors": self._extract_errors(result["stderr"] + result["stdout"]) if not success else [],
            "warnings": self._extract_warnings(result["stdout"]),
            "resource_changes": self._parse_plan_changes(result["stdout"]) if success else None,
        }

    async def apply(self, workspace_path: str, auto_approve: bool = False,
                    env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run terraform apply in workspace."""
        cmd = [self.binary, "apply", "-no-color", "-input=false"]
        if auto_approve:
            cmd.append("-auto-approve")

        result = await self._run_command(cmd, cwd=workspace_path, timeout=600, env_vars=env_vars)
        return {
            "success": result["returncode"] == 0,
            "output": result["stdout"],
            "errors": self._extract_errors(result["stderr"] + result["stdout"]) if result["returncode"] != 0 else [],
        }

    async def destroy(self, workspace_path: str, auto_approve: bool = True,
                      env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run terraform destroy in workspace."""
        cmd = [self.binary, "destroy", "-no-color", "-input=false"]
        if auto_approve:
            cmd.append("-auto-approve")

        result = await self._run_command(cmd, cwd=workspace_path, timeout=600, env_vars=env_vars)
        return {
            "success": result["returncode"] == 0,
            "output": result["stdout"],
            "errors": self._extract_errors(result["stderr"] + result["stdout"]) if result["returncode"] != 0 else [],
        }

    async def _run_command(self, cmd: list, cwd: str, timeout: int = 300,
                           env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute a terraform command as subprocess."""
        import os
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            }

    def _extract_errors(self, output: str) -> list:
        """Extract error messages from terraform output."""
        errors = []
        # Match terraform error blocks
        error_pattern = re.compile(r'Error:\s*(.+?)(?:\n\n|\Z)', re.DOTALL)
        for match in error_pattern.finditer(output):
            errors.append(match.group(1).strip())

        # Also capture single-line errors
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Error:") and line[6:].strip() not in [e[:50] for e in errors]:
                errors.append(line[6:].strip())

        return errors if errors else ([output.strip()] if output.strip() else [])

    def _extract_warnings(self, output: str) -> list:
        """Extract warning messages from terraform output."""
        warnings = []
        warning_pattern = re.compile(r'Warning:\s*(.+?)(?:\n\n|\Z)', re.DOTALL)
        for match in warning_pattern.finditer(output):
            warnings.append(match.group(1).strip())
        return warnings

    def _parse_plan_changes(self, output: str) -> Optional[dict]:
        """Parse plan output for resource change summary."""
        # Match: Plan: X to add, Y to change, Z to destroy.
        match = re.search(
            r'Plan:\s*(\d+)\s*to add,\s*(\d+)\s*to change,\s*(\d+)\s*to destroy',
            output,
        )
        if match:
            return {
                "add": int(match.group(1)),
                "change": int(match.group(2)),
                "destroy": int(match.group(3)),
            }

        # No changes
        if "No changes" in output:
            return {"add": 0, "change": 0, "destroy": 0}

        return None


# Singleton instance
terraform_executor = TerraformExecutor()
