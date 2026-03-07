---
name: responsive-check
description: Verify responsive design across breakpoints — checks layout, touch targets, text readability, image sizing, and mobile UX patterns
---

# /responsive-check — Responsive Design Verification

## Arguments
- `target`: File path, component name, page route, or URL
- `breakpoints`: Comma-separated list (default: `320,375,768,1024,1280,1536`)

## Check Process

### 1. Static Code Analysis
Scan Tailwind classes for responsive patterns:

**Layout:**
- Base styles are mobile-first (no breakpoint prefix = mobile)
- Responsive variants used correctly (`sm:`, `md:`, `lg:`, `xl:`, `2xl:`)
- Grid columns adjust per breakpoint (e.g., `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`)
- Sidebar collapses to drawer on mobile
- Stack layouts switch to horizontal on desktop

**Typography:**
- Font sizes scale up at breakpoints (not fixed px)
- Line lengths limited (max-w-prose or ~65ch) on wide screens
- Body text minimum 16px on mobile (prevents iOS zoom)
- Headings scale proportionally

**Touch & Interaction:**
- Touch targets minimum 44x44px on mobile (`min-h-[44px] min-w-[44px]`)
- Adequate spacing between touch targets (8px minimum)
- No hover-only interactions (hover states paired with focus/active)
- Swipe gestures have button alternatives

**Images & Media:**
- Using `next/image` with responsive sizes prop
- `sizes` attribute set correctly for different viewports
- No fixed-width images that overflow on mobile
- Hero images have different aspect ratios per breakpoint

**Navigation:**
- Desktop nav → hamburger/drawer on mobile
- Breadcrumbs truncate or collapse on mobile
- Bottom sheet or action sheet pattern on mobile
- Tab bars for primary nav on mobile

**Tables:**
- Wide tables horizontally scrollable on mobile with `-webkit-overflow-scrolling: touch`
- OR switch to card layout on mobile
- Column prioritization (hide non-essential columns on mobile)
- Sticky first column for wide tables

### 2. Visual Verification (via Playwright MCP)
If Playwright MCP server is available:
- Capture screenshots at each breakpoint
- Compare layout structure across sizes
- Identify overflow issues (horizontal scroll)
- Check that no content is clipped or hidden unintentionally

### 3. Common Issues to Flag

**Critical:**
- Horizontal scrollbar at any viewport width
- Text smaller than 16px on mobile
- Touch targets smaller than 44px
- Content hidden without alternative access
- Fixed-width containers that don't shrink

**Warning:**
- Missing responsive breakpoint (jumps from mobile to desktop)
- Images not responsive (fixed dimensions)
- Long unbroken text strings (URLs, email addresses) overflowing
- Tables without mobile strategy
- Modals too wide for mobile viewport

**Suggestion:**
- Could use `container` for max-width management
- Could add intermediate breakpoint for tablet
- Could use `aspect-ratio` for responsive media containers

## Output Format

```
## Responsive Design Report

### Target: {component/page}
### Breakpoints Tested: 320, 375, 768, 1024, 1280, 1536

### Results by Breakpoint

| Breakpoint | Width | Status | Issues |
|------------|-------|--------|--------|
| Mobile S   | 320px | PASS/FAIL | {count} |
| Mobile M   | 375px | PASS/FAIL | {count} |
| Tablet     | 768px | PASS/FAIL | {count} |
| Desktop    | 1024px| PASS/FAIL | {count} |
| Desktop L  | 1280px| PASS/FAIL | {count} |
| Desktop XL | 1536px| PASS/FAIL | {count} |

### Issues Found
| # | Breakpoint | Severity | Description | File:Line | Fix |
|---|------------|----------|-------------|-----------|-----|

### Overall: {PASS | NEEDS WORK}
```
