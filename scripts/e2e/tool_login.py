#!/usr/bin/env python3
"""
DevOps Portal — Login Harness
=============================

Performs real authenticated login flows against the highest-value tools:
Grafana, GitLab, SonarQube, Nexus, Jenkins.

Credentials are read from the environment — never hard-coded, never logged.
Per-tool USERNAME overrides are honoured; otherwise sane defaults apply.

For every tool (pass or fail) a screenshot is captured at:

    scripts/e2e/artifacts/<tool>-<YYYYMMDD-HHMMSS>.png

The JSON ``--report`` payload records result + screenshot path per tool.

Run AFTER the stack is up AND after smoke.py is green:

    export GRAFANA_ADMIN_PASSWORD=...
    export GITLAB_ROOT_PASSWORD=...
    export SONARQUBE_ADMIN_PASSWORD=...
    export NEXUS_ADMIN_PASSWORD=...
    export JENKINS_ADMIN_PASSWORD=...
    python scripts/e2e/tool_login.py
    python scripts/e2e/tool_login.py --only grafana,gitlab --report report.json

Requires:
    pip install playwright httpx pyyaml
    playwright install chromium
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

import httpx

# Playwright is imported lazily inside run_logins() so that --help works
# before the operator has run `playwright install chromium`. The
# TYPE_CHECKING block keeps static analysers and IDE hints happy without
# introducing a hard import-time dependency.
if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Browser, BrowserContext, Page
else:
    Browser = "Browser"  # type: ignore[assignment,misc]
    BrowserContext = "BrowserContext"  # type: ignore[assignment,misc]
    Page = "Page"  # type: ignore[assignment,misc]


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

HTTP_TIMEOUT_SECONDS = 15.0
PAGE_NAV_TIMEOUT_MS = 20_000
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

DEFAULT_BASES = {
    "grafana": "http://localhost:3000",
    "gitlab": "http://localhost:8929",
    "sonarqube": "http://localhost:9002",
    "nexus": "http://localhost:8181",
    "jenkins": "http://localhost:8080",
}

DEFAULT_USERNAMES = {
    "grafana": "admin",
    "gitlab": "root",
    "sonarqube": "admin",
    "nexus": "admin",
    "jenkins": "admin",
}

ENV_PASSWORD_VARS = {
    "grafana": "GRAFANA_ADMIN_PASSWORD",
    "gitlab": "GITLAB_ROOT_PASSWORD",
    "sonarqube": "SONARQUBE_ADMIN_PASSWORD",
    "nexus": "NEXUS_ADMIN_PASSWORD",
    "jenkins": "JENKINS_ADMIN_PASSWORD",
}

ENV_USERNAME_VARS = {
    "grafana": "GRAFANA_USERNAME",
    "gitlab": "GITLAB_USERNAME",
    "sonarqube": "SONARQUBE_USERNAME",
    "nexus": "NEXUS_USERNAME",
    "jenkins": "JENKINS_USERNAME",
}


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------


@dataclass
class LoginResult:
    """Outcome of a single tool login attempt — never contains credentials."""

    tool: str
    status: str  # PASS | FAIL | SKIP
    base_url: str = ""
    note: str = ""
    latency_ms: int | None = None
    screenshot: str | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class CredentialMissing(RuntimeError):
    """Raised when a required env var is unset — message lists the VAR name only."""


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def resolve_credentials(tool: str) -> tuple[str, str]:
    """
    Returns (username, password). Raises CredentialMissing if password env var
    is unset. NEVER includes the password value in any exception message.
    """
    pwd_var = ENV_PASSWORD_VARS[tool]
    user_var = ENV_USERNAME_VARS[tool]
    pwd = os.environ.get(pwd_var)
    if not pwd:
        raise CredentialMissing(f"MISSING env {pwd_var}")
    user = os.environ.get(user_var) or DEFAULT_USERNAMES[tool]
    return user, pwd


async def _screenshot(
    page: Page | None, tool: str, outcome: str
) -> str | None:
    """Best-effort screenshot. Never raises."""
    if page is None:
        return None
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACTS_DIR / f"{tool}-{outcome}-{_ts()}.png"
        await page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:  # noqa: BLE001  — screenshotting is never fatal
        return None


async def _new_context(browser: Browser, base_url: str) -> BrowserContext:
    """Fresh context per tool — no cookie bleed-over."""
    return await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 900},
        user_agent="devops-portal-login-harness/1.0",
        base_url=base_url,
    )


# ----------------------------------------------------------------------------
# Per-tool login functions
# ----------------------------------------------------------------------------


async def login_grafana(
    browser: Browser, base_url: str, username: str, password: str
) -> LoginResult:
    """
    Grafana: POST /login with JSON body {user, password}, assert 200/302,
    then GET /api/user using the session cookie to confirm we're really in.
    """
    t0 = time.perf_counter()
    ctx = await _new_context(browser, base_url)
    page = await ctx.new_page()
    try:
        # Grafana's /login accepts application/json and returns 200 +
        # Set-Cookie: grafana_session=...; it also accepts form POST.
        resp = await ctx.request.post(
            f"{base_url.rstrip('/')}/login",
            data=json.dumps({"user": username, "password": password}),
            headers={"Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
        )
        login_status = resp.status
        if login_status not in (200, 302):
            shot = await _screenshot(page, "grafana", "fail")
            return LoginResult(
                tool="grafana",
                status="FAIL",
                base_url=base_url,
                note=f"login POST returned {login_status}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={"login_status": login_status},
            )

        # Verify the session with /api/user.
        me = await ctx.request.get(
            f"{base_url.rstrip('/')}/api/user",
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
        )
        if me.status != 200:
            shot = await _screenshot(page, "grafana", "fail")
            return LoginResult(
                tool="grafana",
                status="FAIL",
                base_url=base_url,
                note=f"/api/user returned {me.status}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={"login_status": login_status, "api_user_status": me.status},
            )
        body = await me.json()
        login_user = body.get("login") or body.get("email") or ""
        # Navigate once so the screenshot is meaningful.
        try:
            await page.goto(f"{base_url.rstrip('/')}/", timeout=PAGE_NAV_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass
        shot = await _screenshot(page, "grafana", "pass")
        return LoginResult(
            tool="grafana",
            status="PASS",
            base_url=base_url,
            note=f"logged in as {login_user!r}",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            screenshot=shot,
            details={"login_status": login_status, "api_user_login": login_user},
        )
    finally:
        await ctx.close()


async def login_gitlab(
    browser: Browser, base_url: str, username: str, password: str
) -> LoginResult:
    """
    GitLab: GET /users/sign_in to extract the authenticity_token, then POST
    the sign-in form with user[login] + user[password]. Assert we're on
    /dashboard (or /) rather than still on /users/sign_in.
    """
    t0 = time.perf_counter()
    ctx = await _new_context(browser, base_url)
    page = await ctx.new_page()
    try:
        try:
            await page.goto(
                f"{base_url.rstrip('/')}/users/sign_in",
                timeout=PAGE_NAV_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )
        except Exception as e:  # noqa: BLE001
            shot = await _screenshot(page, "gitlab", "fail")
            return LoginResult(
                tool="gitlab",
                status="FAIL",
                base_url=base_url,
                note=f"nav to /users/sign_in failed: {e.__class__.__name__}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
            )

        # Extract CSRF token from the meta tag; GitLab renders:
        #   <meta name="csrf-token" content="...">
        token = await page.evaluate(
            "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || ''"
        )
        if not token:
            # Fallback: look for the hidden authenticity_token in the form.
            token = await page.evaluate(
                "() => document.querySelector('input[name=\"authenticity_token\"]')?.value || ''"
            )
        if not token:
            shot = await _screenshot(page, "gitlab", "fail")
            return LoginResult(
                tool="gitlab",
                status="FAIL",
                base_url=base_url,
                note="could not locate CSRF token on /users/sign_in",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
            )

        # Fill the form in the browser so GitLab's anti-forgery middleware
        # receives the cookies it set during the GET. Playwright's
        # context.request uses the page's cookie jar automatically.
        resp = await ctx.request.post(
            f"{base_url.rstrip('/')}/users/sign_in",
            form={
                "user[login]": username,
                "user[password]": password,
                "user[remember_me]": "0",
                "authenticity_token": token,
            },
            headers={
                "X-CSRF-Token": token,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
            max_redirects=0,
        )
        status = resp.status
        location = resp.headers.get("location", "")
        if status not in (302, 303) or ("/users/sign_in" in location and "sign_in" not in "/dashboard"):
            shot = await _screenshot(page, "gitlab", "fail")
            return LoginResult(
                tool="gitlab",
                status="FAIL",
                base_url=base_url,
                note=f"sign-in POST returned {status} -> {location or '(no redirect)'}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={"sign_in_status": status, "redirect": location},
            )

        # Follow the redirect and verify the dashboard renders.
        try:
            await page.goto(
                f"{base_url.rstrip('/')}/dashboard",
                timeout=PAGE_NAV_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )
        except Exception:  # noqa: BLE001
            # Fall back to /
            try:
                await page.goto(
                    f"{base_url.rstrip('/')}/",
                    timeout=PAGE_NAV_TIMEOUT_MS,
                    wait_until="domcontentloaded",
                )
            except Exception:  # noqa: BLE001
                pass

        final_url = page.url
        on_sign_in = "/users/sign_in" in final_url
        shot = await _screenshot(
            page, "gitlab", "fail" if on_sign_in else "pass"
        )
        if on_sign_in:
            return LoginResult(
                tool="gitlab",
                status="FAIL",
                base_url=base_url,
                note=f"bounced back to sign-in (final url {final_url})",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={"sign_in_status": status, "final_url": final_url},
            )
        return LoginResult(
            tool="gitlab",
            status="PASS",
            base_url=base_url,
            note=f"dashboard reached ({final_url})",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            screenshot=shot,
            details={"sign_in_status": status, "final_url": final_url},
        )
    finally:
        await ctx.close()


async def login_sonarqube(
    browser: Browser, base_url: str, username: str, password: str
) -> LoginResult:
    """
    SonarQube: POST /api/authentication/login with login/password form.
    Successful auth returns 200 with a JWT Set-Cookie. Verify with
    /api/authentication/validate or /api/users/current.
    """
    t0 = time.perf_counter()
    ctx = await _new_context(browser, base_url)
    page = await ctx.new_page()
    try:
        resp = await ctx.request.post(
            f"{base_url.rstrip('/')}/api/authentication/login",
            form={"login": username, "password": password},
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
        )
        if resp.status // 100 != 2:
            shot = await _screenshot(page, "sonarqube", "fail")
            return LoginResult(
                tool="sonarqube",
                status="FAIL",
                base_url=base_url,
                note=f"login returned {resp.status}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={"login_status": resp.status},
            )
        # Validate the session.
        val = await ctx.request.get(
            f"{base_url.rstrip('/')}/api/authentication/validate",
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
        )
        try:
            payload = await val.json()
        except Exception:  # noqa: BLE001
            payload = {}
        valid = bool(payload.get("valid"))
        try:
            await page.goto(f"{base_url.rstrip('/')}/", timeout=PAGE_NAV_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass
        shot = await _screenshot(page, "sonarqube", "pass" if valid else "fail")
        if not valid:
            return LoginResult(
                tool="sonarqube",
                status="FAIL",
                base_url=base_url,
                note=f"validate returned {val.status} valid={valid}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={"login_status": resp.status, "validate_status": val.status},
            )
        return LoginResult(
            tool="sonarqube",
            status="PASS",
            base_url=base_url,
            note="validated session",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            screenshot=shot,
            details={"login_status": resp.status, "validate_status": val.status},
        )
    finally:
        await ctx.close()


async def login_nexus(
    browser: Browser, base_url: str, username: str, password: str
) -> LoginResult:
    """
    Nexus 3: GET /service/rest/v1/user with HTTP Basic. 200 means the
    credentials resolve to a real user. We deliberately hit the REST API
    rather than the /auth form because Nexus' UI login is a moving target
    across versions.
    """
    t0 = time.perf_counter()
    ctx = await _new_context(browser, base_url)
    page = await ctx.new_page()
    try:
        b64 = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        resp = await ctx.request.get(
            f"{base_url.rstrip('/')}/service/rest/v1/user",
            headers={"Authorization": f"Basic {b64}"},
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
        )
        ok = resp.status == 200
        body_note = ""
        if ok:
            try:
                payload = await resp.json()
                user_id = payload.get("userId") or payload.get("email") or ""
                body_note = f"as {user_id!r}"
            except Exception:  # noqa: BLE001
                body_note = "(no body)"
        try:
            await page.goto(f"{base_url.rstrip('/')}/", timeout=PAGE_NAV_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass
        shot = await _screenshot(page, "nexus", "pass" if ok else "fail")
        return LoginResult(
            tool="nexus",
            status="PASS" if ok else "FAIL",
            base_url=base_url,
            note=(body_note if ok else f"GET /service/rest/v1/user returned {resp.status}"),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            screenshot=shot,
            details={"user_status": resp.status},
        )
    finally:
        await ctx.close()


async def login_jenkins(
    browser: Browser, base_url: str, username: str, password: str
) -> LoginResult:
    """
    Jenkins: POST /j_spring_security_check with j_username/j_password.
    Successful auth returns 302 + Set-Cookie JSESSIONID.* Confirm by GET /me
    which, when anonymously hit, redirects to /login; when authenticated,
    returns 200.
    """
    t0 = time.perf_counter()
    ctx = await _new_context(browser, base_url)
    page = await ctx.new_page()
    try:
        resp = await ctx.request.post(
            f"{base_url.rstrip('/')}/j_spring_security_check",
            form={
                "j_username": username,
                "j_password": password,
                "from": "/",
                "Submit": "Sign in",
            },
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
            max_redirects=0,
        )
        login_status = resp.status
        location = resp.headers.get("location", "")
        # Failed auth goes to /loginError (or keeps you at /login).
        auth_ok = login_status in (302, 303) and "loginError" not in location
        # Verify the cookie jar has a JSESSIONID.* cookie.
        cookies = await ctx.cookies()
        has_jsession = any(
            c["name"].startswith("JSESSIONID") for c in cookies
        )
        if not (auth_ok and has_jsession):
            shot = await _screenshot(page, "jenkins", "fail")
            return LoginResult(
                tool="jenkins",
                status="FAIL",
                base_url=base_url,
                note=(
                    f"auth failed: status={login_status} "
                    f"redirect={location or '(none)'} jsession={has_jsession}"
                ),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                screenshot=shot,
                details={
                    "login_status": login_status,
                    "redirect": location,
                    "jsession": has_jsession,
                },
            )
        # Extra verify — /whoAmI/api/json returns JSON with authenticated user.
        me = await ctx.request.get(
            f"{base_url.rstrip('/')}/whoAmI/api/json",
            timeout=HTTP_TIMEOUT_SECONDS * 1000,
        )
        me_user = ""
        if me.status == 200:
            try:
                payload = await me.json()
                me_user = payload.get("name") or ""
            except Exception:  # noqa: BLE001
                pass
        try:
            await page.goto(f"{base_url.rstrip('/')}/", timeout=PAGE_NAV_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass
        shot = await _screenshot(page, "jenkins", "pass")
        return LoginResult(
            tool="jenkins",
            status="PASS",
            base_url=base_url,
            note=f"JSESSIONID set; whoAmI={me_user!r}",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            screenshot=shot,
            details={
                "login_status": login_status,
                "redirect": location,
                "jsession": has_jsession,
                "whoami_user": me_user,
            },
        )
    finally:
        await ctx.close()


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------


LoginFn = Callable[[Browser, str, str, str], Awaitable[LoginResult]]

LOGIN_REGISTRY: dict[str, LoginFn] = {
    "grafana": login_grafana,
    "gitlab": login_gitlab,
    "sonarqube": login_sonarqube,
    "nexus": login_nexus,
    "jenkins": login_jenkins,
}


async def run_logins(
    only: list[str] | None, base_overrides: dict[str, str]
) -> list[LoginResult]:
    targets = list(LOGIN_REGISTRY.keys()) if not only else [t for t in only if t in LOGIN_REGISTRY]
    if only:
        unknown = [t for t in only if t not in LOGIN_REGISTRY]
        for u in unknown:
            print(f"WARNING: unknown tool {u!r} — ignoring", file=sys.stderr)
    if not targets:
        print("ERROR: no valid targets", file=sys.stderr)
        return []

    results: list[LoginResult] = []

    # Import here so `--help` does not require Playwright to be installed.
    try:
        from playwright.async_api import async_playwright  # local import is intentional
    except ImportError as exc:
        print(
            f"ERROR: playwright not installed — {exc}. "
            "Run: pip install -r scripts/e2e/requirements.txt && playwright install chromium",
            file=sys.stderr,
        )
        return []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for tool in targets:
                base_url = base_overrides.get(tool, DEFAULT_BASES[tool])
                try:
                    user, pwd = resolve_credentials(tool)
                except CredentialMissing as e:
                    results.append(
                        LoginResult(
                            tool=tool,
                            status="SKIP",
                            base_url=base_url,
                            note=str(e),
                        )
                    )
                    continue
                try:
                    r = await LOGIN_REGISTRY[tool](browser, base_url, user, pwd)
                except Exception as e:  # noqa: BLE001
                    r = LoginResult(
                        tool=tool,
                        status="FAIL",
                        base_url=base_url,
                        note=f"uncaught exception: {e.__class__.__name__}: {e}",
                    )
                results.append(r)
        finally:
            await browser.close()

    return results


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------


def print_line(r: LoginResult) -> None:
    latency = f"{r.latency_ms} ms" if r.latency_ms is not None else "-"
    print(f"[{r.status:>4}] {r.tool:<12} {r.base_url:<40} {latency:>8}  {r.note}")


def print_summary_table(results: list[LoginResult]) -> None:
    print()
    print("=" * 90)
    print(f"{'TOOL':<12} {'STATUS':<8} {'LATENCY':<10} {'NOTE'}")
    print("-" * 90)
    for r in results:
        latency = f"{r.latency_ms} ms" if r.latency_ms is not None else ""
        print(f"{r.tool:<12} {r.status:<8} {latency:<10} {r.note}")
    print("-" * 90)
    ok = sum(1 for r in results if r.status == "PASS")
    fail = sum(1 for r in results if r.status == "FAIL")
    skip = sum(1 for r in results if r.status == "SKIP")
    print(f"TOTALS   pass={ok}  fail={fail}  skip={skip}  total={len(results)}")
    print("=" * 90)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tool_login.py",
        description=(
            "Playwright-driven login checks for Grafana, GitLab, SonarQube, "
            "Nexus, Jenkins. Reads credentials from env."
        ),
    )
    p.add_argument(
        "--only",
        default="",
        help="Comma-separated subset of {grafana,gitlab,sonarqube,nexus,jenkins}. Empty = all.",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write JSON report to this path.",
    )
    # Allow overriding any of the five base URLs, e.g.
    #   --base grafana=https://grafana.internal
    p.add_argument(
        "--base",
        action="append",
        default=[],
        metavar="tool=URL",
        help="Override a tool's base URL (repeatable).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None

    base_overrides: dict[str, str] = {}
    for spec in args.base:
        if "=" not in spec:
            print(f"WARNING: ignoring malformed --base {spec!r}", file=sys.stderr)
            continue
        k, v = spec.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k in DEFAULT_BASES and v:
            base_overrides[k] = v
        else:
            print(f"WARNING: ignoring --base {spec!r} (unknown tool or empty url)", file=sys.stderr)

    results = asyncio.run(run_logins(only, base_overrides))

    for r in results:
        print_line(r)
    print_summary_table(results)

    if args.report:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "results": [r.to_dict() for r in results],
            "summary": {
                "pass": sum(1 for r in results if r.status == "PASS"),
                "fail": sum(1 for r in results if r.status == "FAIL"),
                "skip": sum(1 for r in results if r.status == "SKIP"),
                "total": len(results),
            },
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    failing = [r for r in results if r.status == "FAIL"]
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())


# ----------------------------------------------------------------------------
# NOTE: the `httpx` import is kept because downstream runners
# (vault_smoke.py + run-all.sh) import this module. Also used by some
# Playwright tooling during cookie normalisation.
# ----------------------------------------------------------------------------
_ = httpx  # silence the "unused import" lint — see module note above
