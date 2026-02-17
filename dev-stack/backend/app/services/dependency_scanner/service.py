"""
Dependency Scanner Service

Scan Docker images for vulnerabilities via Trivy,
with Nexus image listing for convenient selection.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import deque

from app.config import tools_manager
from app.integrations.trivy import TrivyIntegration
from app.integrations.nexus import NexusIntegration


class DependencyScannerService:
    """Service for scanning Docker images for vulnerabilities."""

    MAX_HISTORY = 20

    def __init__(self):
        self._scan_history: deque = deque(maxlen=self.MAX_HISTORY)

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
    # List images from Nexus
    # ------------------------------------------------------------------

    async def list_images(self, repository: str = "docker-hosted") -> Dict[str, Any]:
        """List Docker images from Nexus with their tags."""
        nexus = self._get_nexus()
        try:
            raw_images = await nexus.list_docker_images(repository)

            image_map: Dict[str, List[str]] = {}
            for img in raw_images:
                name = img.get("name", "unknown")
                version = img.get("version", "latest")
                if name not in image_map:
                    image_map[name] = []
                if version not in image_map[name]:
                    image_map[name].append(version)

            images = []
            for name, tags in sorted(image_map.items()):
                images.append({
                    "name": name,
                    "tags": sorted(tags),
                    "full_names": [f"{name}:{tag}" for tag in sorted(tags)],
                })

            return {"success": True, "repository": repository, "images": images, "total": len(images)}
        except Exception as e:
            return {"success": False, "error": str(e), "images": []}
        finally:
            await nexus.close()

    # ------------------------------------------------------------------
    # Scan an image
    # ------------------------------------------------------------------

    async def scan_image(
        self,
        image: str,
        severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
        ignore_unfixed: bool = False,
    ) -> Dict[str, Any]:
        """Scan a Docker image and return structured results."""
        trivy = self._get_trivy()
        try:
            scan_result = await trivy.scan_image(image, severity, ignore_unfixed)

            result = {
                "success": True,
                "target": scan_result.target,
                "summary": {
                    "total": scan_result.total_count,
                    "critical": scan_result.critical_count,
                    "high": scan_result.high_count,
                    "medium": scan_result.medium_count,
                    "low": scan_result.low_count,
                },
                "vulnerabilities": [
                    {
                        "id": v.vulnerability_id,
                        "pkg_name": v.pkg_name,
                        "installed_version": v.installed_version,
                        "fixed_version": v.fixed_version,
                        "severity": v.severity,
                        "title": v.title,
                        "description": v.description,
                    }
                    for v in scan_result.vulnerabilities
                ],
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            }

            self._scan_history.appendleft({
                "image": image,
                "summary": result["summary"],
                "scanned_at": result["scanned_at"],
                "severity_filter": severity,
                "ignore_unfixed": ignore_unfixed,
            })

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await trivy.close()

    # ------------------------------------------------------------------
    # Scan history
    # ------------------------------------------------------------------

    def get_history(self) -> Dict[str, Any]:
        return {"success": True, "scans": list(self._scan_history), "total": len(self._scan_history)}

    def clear_history(self) -> Dict[str, Any]:
        self._scan_history.clear()
        return {"success": True, "message": "Scan history cleared"}
