---
name: gen-test
description: Generate comprehensive test suites for any source file — supports React components (Vitest + RTL), Python services (pytest), and E2E flows (Playwright)
---

# /gen-test — Generate Tests

## Arguments
- `target`: File path or function/component name to test
- `type`: `unit` | `integration` | `e2e` | `a11y` | `visual` (optional, auto-detected)
- `coverage`: `basic` | `thorough` | `exhaustive` (default: `thorough`)

## Process

### 1. Analyze Target
- Read the source file
- Identify all exports (functions, components, hooks, classes)
- Detect framework (React, FastAPI, vanilla JS)
- Check existing test patterns in project

### 2. Generate Tests by Type

**React Component (Vitest + React Testing Library):**
```tsx
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { vi, describe, it, expect, beforeEach } from "vitest";

expect.extend(toHaveNoViolations);

describe("{ComponentName}", () => {
  // Rendering
  it("renders with required props", () => {});
  it("renders with all optional props", () => {});
  it("applies custom className", () => {});
  it("forwards ref to DOM element", () => {});

  // States
  it("renders loading skeleton when isLoading", () => {});
  it("renders error state with retry button", () => {});
  it("renders empty state when data is empty", () => {});

  // Interactions
  it("calls onClick when clicked", () => {});
  it("handles form submission", () => {});
  it("debounces search input", () => {});

  // Keyboard
  it("is focusable via Tab", () => {});
  it("activates on Enter and Space", () => {});
  it("closes on Escape", () => {});

  // Accessibility
  it("has no accessibility violations", async () => {
    const { container } = render(<Component {...defaultProps} />);
    expect(await axe(container)).toHaveNoViolations();
  });
  it("has correct ARIA attributes", () => {});
  it("announces status changes to screen readers", () => {});

  // Responsive (if applicable)
  it("renders mobile layout at small viewport", () => {});
  it("renders desktop layout at large viewport", () => {});
});
```

**Python FastAPI (pytest + httpx):**
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

@pytest.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

class TestEndpoint:
    async def test_success(self, client):
        response = await client.get("/api/v1/resource")
        assert response.status_code == 200

    async def test_validation_error(self, client):
        response = await client.post("/api/v1/resource", json={})
        assert response.status_code == 422

    async def test_not_found(self, client):
        response = await client.get("/api/v1/resource/nonexistent")
        assert response.status_code == 404

    async def test_unauthorized(self, client):
        response = await client.get("/api/v1/protected")
        assert response.status_code == 401
```

**E2E (Playwright):**
```typescript
import { test, expect } from "@playwright/test";

test.describe("{Feature} Flow", () => {
  test("completes happy path", async ({ page }) => {
    await page.goto("/feature");
    await expect(page.getByRole("heading")).toBeVisible();
    await page.getByRole("button", { name: "Action" }).click();
    await expect(page.getByText("Success")).toBeVisible();
  });

  test("handles error gracefully", async ({ page }) => {
    // Mock API failure
    await page.route("**/api/**", route => route.fulfill({ status: 500 }));
    await page.goto("/feature");
    await expect(page.getByText("Something went wrong")).toBeVisible();
    await page.getByRole("button", { name: "Retry" }).click();
  });

  test("is accessible", async ({ page }) => {
    await page.goto("/feature");
    // axe-core accessibility check
  });
});
```

### 3. Coverage Levels

**basic** — Happy path + one error case per function
**thorough** — Happy path + edge cases + errors + accessibility
**exhaustive** — All of thorough + boundary values + race conditions + visual regression + responsive

### 4. Post-Generation
- Place test file alongside source (or in `__tests__/` following project convention)
- Print coverage summary estimate
- Suggest missing mocks or fixtures
