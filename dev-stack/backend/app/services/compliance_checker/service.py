"""
Compliance Checker Service

Aggregates SonarQube quality gates and Trivy vulnerability scans
into a unified compliance dashboard per project.
"""
import asyncio
from typing import Dict, Any, List, Optional

from app.config import tools_manager
from app.integrations.sonarqube import SonarQubeIntegration
from app.integrations.trivy import TrivyIntegration
from app.integrations.nexus import NexusIntegration


class ComplianceCheckerService:
    """Service for checking compliance across SonarQube + Trivy."""

    def _get_sonarqube(self) -> SonarQubeIntegration:
        config = tools_manager.get_tool("sonarqube")
        if not config or not config.enabled:
            raise RuntimeError("SonarQube is not configured or disabled")
        return SonarQubeIntegration(config)

    def _get_trivy(self) -> TrivyIntegration:
        config = tools_manager.get_tool("trivy")
        if not config or not config.enabled:
            raise RuntimeError("Trivy is not configured or disabled")
        return TrivyIntegration(config)

    def _get_nexus(self) -> NexusIntegration:
        config = tools_manager.get_tool("nexus")
        if not config or not config.enabled:
            raise RuntimeError("Nexus is not configured or disabled")
        return NexusIntegration(config)

    # ------------------------------------------------------------------
    # List projects
    # ------------------------------------------------------------------

    async def list_projects(self, search: Optional[str] = None) -> Dict[str, Any]:
        """List SonarQube projects with quality gate status."""
        sonar = self._get_sonarqube()
        try:
            projects = await sonar.list_projects(search=search)
            result = []
            for p in projects:
                try:
                    qg = await sonar.get_quality_gate_status(p.key)
                    qg_status = qg.status
                except Exception:
                    qg_status = "UNKNOWN"

                result.append({
                    "key": p.key,
                    "name": p.name,
                    "quality_gate_status": qg_status,
                    "last_analysis": getattr(p, 'last_analysis_date', None),
                })

            return {"success": True, "projects": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await sonar.close()

    # ------------------------------------------------------------------
    # Full compliance report for one project
    # ------------------------------------------------------------------

    async def get_project_compliance(
        self,
        project_key: str,
        docker_image: Optional[str] = None,
        trivy_severity: str = "HIGH,CRITICAL",
    ) -> Dict[str, Any]:
        """Get comprehensive compliance report for a single project."""
        sonar = self._get_sonarqube()
        try:
            # Quality gate
            qg = await sonar.get_quality_gate_status(project_key)

            # Metrics
            metrics_list = await sonar.get_metrics(project_key)
            metrics = {}
            for m in metrics_list:
                metrics[m.metric] = m.value

            # Issue counts
            issue_counts = await sonar.get_issue_count(project_key)
        except Exception as e:
            return {"success": False, "error": f"SonarQube error: {e}"}
        finally:
            await sonar.close()

        # Trivy scan (optional)
        trivy_result = None
        if docker_image:
            trivy = self._get_trivy()
            try:
                scan = await trivy.scan_image(docker_image, trivy_severity)
                trivy_result = {
                    "image": docker_image,
                    "total_vulnerabilities": scan.total_count,
                    "critical": scan.critical_count,
                    "high": scan.high_count,
                    "medium": scan.medium_count,
                    "low": scan.low_count,
                    "vulnerabilities": [
                        {
                            "id": v.vulnerability_id,
                            "pkg_name": v.pkg_name,
                            "severity": v.severity,
                            "title": v.title,
                            "fixed_version": v.fixed_version,
                        }
                        for v in scan.vulnerabilities[:20]
                    ],
                }
            except Exception as e:
                trivy_result = {"image": docker_image, "error": str(e)}
            finally:
                await trivy.close()

        # Compute compliance score
        compliance_status = self._compute_compliance(qg.status, metrics, trivy_result)

        return {
            "success": True,
            "project_key": project_key,
            "compliance_status": compliance_status,
            "quality_gate": {
                "status": qg.status,
                "conditions": qg.conditions,
            },
            "metrics": metrics,
            "issues": issue_counts,
            "trivy": trivy_result,
        }

    def _compute_compliance(self, qg_status: str, metrics: dict, trivy_result: Optional[dict]) -> str:
        """Compute PASS/WARN/FAIL compliance score."""
        score = "PASS"

        # Quality gate
        if qg_status == "ERROR":
            score = "FAIL"

        # Metrics checks
        try:
            bugs = int(metrics.get("bugs", 0))
            code_smells = int(metrics.get("code_smells", 0))
            if (bugs > 0 or code_smells > 50) and score == "PASS":
                score = "WARN"
        except (ValueError, TypeError):
            pass

        # Trivy checks
        if trivy_result and not trivy_result.get("error"):
            critical = trivy_result.get("critical", 0)
            high = trivy_result.get("high", 0)
            if critical > 0:
                score = "FAIL"
            elif high > 5:
                score = "FAIL"
            elif high > 0 and score == "PASS":
                score = "WARN"

        return score

    # ------------------------------------------------------------------
    # Find Docker images for a project
    # ------------------------------------------------------------------

    async def find_docker_images(self, project_key: str) -> Dict[str, Any]:
        """Look up Docker images in Nexus that might match a project key."""
        nexus = self._get_nexus()
        try:
            raw_images = await nexus.list_docker_images("docker-hosted")
            matching = []
            search_key = project_key.lower().replace("-", "").replace("_", "")
            for img in raw_images:
                name = img.get("name", "")
                if search_key in name.lower().replace("-", "").replace("_", ""):
                    matching.append({"name": name, "version": img.get("version", "latest")})
            return {"success": True, "images": matching}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await nexus.close()

    # ------------------------------------------------------------------
    # Full dashboard
    # ------------------------------------------------------------------

    async def get_dashboard(self, search: Optional[str] = None) -> Dict[str, Any]:
        """Get compliance dashboard for all projects."""
        sonar = self._get_sonarqube()
        try:
            projects = await sonar.list_projects(search=search)

            results = []
            for p in projects:
                try:
                    qg = await sonar.get_quality_gate_status(p.key)
                    metrics_list = await sonar.get_metrics(p.key)
                    metrics = {m.metric: m.value for m in metrics_list}
                    issue_counts = await sonar.get_issue_count(p.key)

                    compliance_status = self._compute_compliance(qg.status, metrics, None)

                    results.append({
                        "key": p.key,
                        "name": p.name,
                        "compliance_status": compliance_status,
                        "quality_gate": {"status": qg.status, "conditions": qg.conditions},
                        "metrics": metrics,
                        "issues": issue_counts,
                        "last_analysis": getattr(p, 'last_analysis_date', None),
                    })
                except Exception:
                    results.append({
                        "key": p.key,
                        "name": p.name,
                        "compliance_status": "UNKNOWN",
                        "quality_gate": {"status": "UNKNOWN", "conditions": []},
                        "metrics": {},
                        "issues": {},
                    })

            pass_count = sum(1 for r in results if r["compliance_status"] == "PASS")
            warn_count = sum(1 for r in results if r["compliance_status"] == "WARN")
            fail_count = sum(1 for r in results if r["compliance_status"] == "FAIL")

            return {
                "success": True,
                "summary": {"total": len(results), "pass": pass_count, "warn": warn_count, "fail": fail_count},
                "projects": results,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await sonar.close()
