---
name: screenshot-diff
description: Capture and compare screenshots for visual regression testing — supports multiple viewports, dark mode, and component-level snapshots
---

# /screenshot-diff — Visual Regression Testing

## Arguments
- `target`: URL, page route, or component name
- `baseline`: `capture` (save new baseline) | `compare` (diff against existing) | `update` (replace baseline)
- `viewports`: Comma-separated (default: `375x812,768x1024,1440x900`)
- `theme`: `light` | `dark` | `both` (default: `both`)

## Process

### 1. Capture Screenshots
Using Playwright MCP server:

**Page-level:**
```
- Navigate to target URL/route
- Wait for network idle + fonts loaded + animations complete
- Capture full-page screenshot at each viewport
- Capture above-the-fold screenshot at each viewport
- Repeat for light and dark themes
```

**Component-level:**
```
- Navigate to Storybook or component preview page
- Isolate component with different prop combinations
- Capture each variant: default, hover, focus, active, disabled
- Capture loading, error, empty states
```

### 2. Naming Convention
```
screenshots/
├── baselines/
│   ├── {page}-{viewport}-{theme}.png
│   └── {component}-{variant}-{viewport}-{theme}.png
├── current/
│   ├── {page}-{viewport}-{theme}.png
│   └── {component}-{variant}-{viewport}-{theme}.png
└── diffs/
    ├── {page}-{viewport}-{theme}.diff.png
    └── {component}-{variant}-{viewport}-{theme}.diff.png
```

### 3. Comparison
When `baseline: compare`:
- Load baseline and current screenshots
- Pixel-by-pixel comparison with configurable threshold
- Default threshold: 0.1% pixel difference tolerance
- Anti-aliasing tolerance: 2px
- Generate diff image highlighting changed regions in red

### 4. Report Output
```
## Visual Regression Report

### Target: {page/component}
### Date: {timestamp}
### Viewports: 375x812, 768x1024, 1440x900

| Screenshot | Viewport | Theme | Status | Diff % |
|------------|----------|-------|--------|--------|
| Homepage   | 375x812  | light | PASS   | 0.00%  |
| Homepage   | 375x812  | dark  | FAIL   | 2.31%  |
| Homepage   | 1440x900 | light | PASS   | 0.02%  |

### Failures
1. **Homepage (375x812, dark)**
   - Diff: 2.31% pixels changed
   - Region: Header area (0,0 to 375,64)
   - Likely cause: Font rendering difference
   - Diff image: screenshots/diffs/homepage-375x812-dark.diff.png
```

### 5. Integration with CI
Generate Playwright test file for automated visual regression:
```typescript
import { test, expect } from "@playwright/test";

test("visual regression: {page}", async ({ page }) => {
  await page.goto("{route}");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveScreenshot("{page}-{viewport}.png", {
    maxDiffPixelRatio: 0.001,
    animations: "disabled",
  });
});
```

## Prerequisites
- Playwright MCP server configured in `.mcp.json`
- Baseline screenshots captured (`/screenshot-diff target={page} baseline=capture`)
- Consistent font loading (use `next/font` to avoid CLS)
