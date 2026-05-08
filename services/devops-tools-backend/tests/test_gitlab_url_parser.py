import pytest

from app.config import settings
from app.services.pipeline.analyzer import parse_gitlab_url


@pytest.fixture(autouse=True)
def local_gitlab_settings(monkeypatch):
    monkeypatch.setattr(settings, "gitlab_url", "http://gitlab-server/gitlab")
    monkeypatch.setattr(settings, "public_base_url", "https://deepaksharma.live")
    monkeypatch.setattr(settings, "public_base_domain", "deepaksharma.live")
    monkeypatch.setattr(settings, "tailscale_base_url", "https://deepaksharma.live")


def test_parse_legacy_tailscale_gitlab_url_uses_internal_api_base():
    parsed = parse_gitlab_url(
        "https://deepak-desktop.tailac51e7.ts.net/gitlab/root/java-spring.git"
    )

    assert parsed == {
        "host": "http://gitlab-server/gitlab",
        "path": "root/java-spring",
        "project_path": "root%2Fjava-spring",
    }


def test_parse_cloudflare_apex_gitlab_url_uses_internal_api_base():
    parsed = parse_gitlab_url(
        "https://deepaksharma.live/gitlab/root/java-spring.git"
    )

    assert parsed["host"] == "http://gitlab-server/gitlab"
    assert parsed["path"] == "root/java-spring"


def test_parse_cloudflare_gitlab_subdomain_uses_internal_api_base():
    parsed = parse_gitlab_url(
        "https://gitlab.deepaksharma.live/gitlab/root/java-spring.git"
    )

    assert parsed["host"] == "http://gitlab-server/gitlab"
    assert parsed["path"] == "root/java-spring"


def test_parse_external_gitlab_relative_root_preserves_external_api_base():
    parsed = parse_gitlab_url("https://example.com/gitlab/group/project.git")

    assert parsed == {
        "host": "https://example.com/gitlab",
        "path": "group/project",
        "project_path": "group%2Fproject",
    }
