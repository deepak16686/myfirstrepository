"""
File: trivy.py
Purpose: Trivy security scanner REST API client for vulnerability scanning of Docker images,
         repositories, filesystems, and IaC configs. Also supports SBOM generation and license
         scanning via the Trivy server running in the dev-stack.
When Used: Called by the trivy router (REST proxy), the dependency_scanner service (on-demand image
           scanning), and the compliance_checker service (vulnerability aggregation for dashboards).
Why Created: Integrates container and code security scanning into the DevOps platform so pipeline-built
             images can be scanned for CVEs and the compliance dashboard can show vulnerability counts.
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import (
    ToolStatus, TrivyVulnerability, TrivyScanResult
)


class TrivyIntegration(BaseIntegration):
    """Trivy security scanner API integration"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "trivy"

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/healthz")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/version")
            if response.status_code == 200:
                data = response.json()
                return data.get("Version")
        except Exception:
            pass
        return None

    # ========================================================================
    # Scanning
    # ========================================================================

    async def scan_image(
        self,
        image: str,
        severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
        ignore_unfixed: bool = False
    ) -> TrivyScanResult:
        """
        Scan a container image for vulnerabilities using Trivy server.

        Args:
            image: Container image to scan (e.g., "nginx:latest")
            severity: Comma-separated severity levels to include
            ignore_unfixed: Skip vulnerabilities without fixes
        """
        params = {
            "image": image,
            "severity": severity,
            "ignoreUnfixed": str(ignore_unfixed).lower()
        }

        response = await self.get("/scan", params=params)
        response.raise_for_status()
        data = response.json()

        return self._parse_scan_result(image, data)

    async def scan_repo(
        self,
        repo_url: str,
        branch: str = "main",
        severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
    ) -> TrivyScanResult:
        """
        Scan a git repository for vulnerabilities.

        Args:
            repo_url: Git repository URL
            branch: Branch to scan
            severity: Comma-separated severity levels to include
        """
        params = {
            "repo": repo_url,
            "branch": branch,
            "severity": severity
        }

        response = await self.get("/scan/repo", params=params)
        response.raise_for_status()
        data = response.json()

        return self._parse_scan_result(repo_url, data)

    async def scan_filesystem(
        self,
        path: str,
        severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
    ) -> TrivyScanResult:
        """
        Scan a filesystem path for vulnerabilities.

        Args:
            path: Filesystem path to scan
            severity: Comma-separated severity levels to include
        """
        payload = {
            "path": path,
            "severity": severity
        }

        response = await self.post("/scan/fs", json=payload)
        response.raise_for_status()
        data = response.json()

        return self._parse_scan_result(path, data)

    def _parse_scan_result(self, target: str, data: Dict[str, Any]) -> TrivyScanResult:
        """Parse Trivy scan response into TrivyScanResult"""
        vulnerabilities = []
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        # Handle different response formats
        results = data.get("Results", []) or data.get("results", []) or []

        for result in results:
            vulns = result.get("Vulnerabilities", []) or result.get("vulnerabilities", []) or []
            for vuln in vulns:
                severity = vuln.get("Severity", vuln.get("severity", "UNKNOWN")).upper()

                vulnerability = TrivyVulnerability(
                    vulnerability_id=vuln.get("VulnerabilityID", vuln.get("vulnerabilityID", "")),
                    pkg_name=vuln.get("PkgName", vuln.get("pkgName", "")),
                    installed_version=vuln.get("InstalledVersion", vuln.get("installedVersion", "")),
                    fixed_version=vuln.get("FixedVersion", vuln.get("fixedVersion")),
                    severity=severity,
                    title=vuln.get("Title", vuln.get("title")),
                    description=vuln.get("Description", vuln.get("description"))
                )
                vulnerabilities.append(vulnerability)

                # Count by severity
                sev_key = severity.lower()
                if sev_key in counts:
                    counts[sev_key] += 1

        return TrivyScanResult(
            target=target,
            vulnerabilities=vulnerabilities,
            total_count=len(vulnerabilities),
            critical_count=counts["critical"],
            high_count=counts["high"],
            medium_count=counts["medium"],
            low_count=counts["low"]
        )

    # ========================================================================
    # Database
    # ========================================================================

    async def get_db_status(self) -> Dict[str, Any]:
        """Get vulnerability database status"""
        try:
            response = await self.get("/db/status")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {"status": "unknown"}

    async def update_db(self) -> bool:
        """Trigger vulnerability database update"""
        try:
            response = await self.post("/db/update")
            return response.status_code == 200
        except Exception:
            return False

    # ========================================================================
    # SBOM (Software Bill of Materials)
    # ========================================================================

    async def generate_sbom(
        self,
        image: str,
        format: str = "cyclonedx"
    ) -> Dict[str, Any]:
        """
        Generate SBOM for a container image.

        Args:
            image: Container image to analyze
            format: SBOM format (cyclonedx, spdx, spdx-json)
        """
        params = {
            "image": image,
            "format": format
        }

        response = await self.get("/sbom", params=params)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # License Scanning
    # ========================================================================

    async def scan_licenses(self, image: str) -> Dict[str, Any]:
        """Scan for license information in a container image"""
        params = {"image": image}
        response = await self.get("/scan/license", params=params)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Config Scanning
    # ========================================================================

    async def scan_config(
        self,
        config_type: str,
        content: str
    ) -> Dict[str, Any]:
        """
        Scan configuration files for misconfigurations.

        Args:
            config_type: Type of config (dockerfile, kubernetes, terraform, etc.)
            content: Configuration content to scan
        """
        payload = {
            "type": config_type,
            "content": content
        }

        response = await self.post("/scan/config", json=payload)
        response.raise_for_status()
        return response.json()
