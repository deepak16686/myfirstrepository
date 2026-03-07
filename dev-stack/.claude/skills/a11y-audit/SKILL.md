---
name: a11y-audit
description: Run comprehensive accessibility audit on components or pages — checks WCAG 2.1 AA compliance, keyboard navigation, screen reader support, color contrast
---

# /a11y-audit — Accessibility Audit

## Arguments
- `target`: File path, component name, or `all` to audit everything
- `level`: `AA` (default) | `AAA` (stricter)

## Audit Process

### 1. Static Analysis
Scan source files for:

**HTML Semantics:**
- `<div>` used where `<button>`, `<a>`, `<nav>`, `<main>`, `<section>` should be
- Click handlers on non-interactive elements without `role` and `tabIndex`
- Missing `<main>` landmark
- Multiple `<h1>` per page
- Heading level skips (h1 → h3)
- Lists not using `<ul>`/`<ol>`/`<li>`
- Tables without `<thead>`, `<th>`, or `scope`

**ARIA:**
- `aria-label` on elements that already have visible text (redundant)
- `aria-hidden="true"` on focusable elements
- Missing `aria-live` on dynamic content regions
- `role="button"` without keyboard handler
- `aria-expanded` without toggle control
- `aria-describedby` / `aria-labelledby` pointing to nonexistent IDs

**Forms:**
- Inputs without associated `<label>`
- Missing `required` attribute or `aria-required`
- Error messages not linked via `aria-describedby`
- No `aria-invalid` on validation error
- Autocomplete attribute missing on login/address forms
- Submit buttons with vague text ("Submit" instead of "Create Account")

**Images & Media:**
- `<img>` without `alt` attribute
- Decorative images not using `alt=""`
- SVG icons without `aria-label` or `aria-hidden`
- Video/audio without captions or transcripts

### 2. Color Contrast Check
- Extract all text color + background color pairs from Tailwind classes
- Calculate contrast ratio using WCAG formula
- Flag violations: normal text < 4.5:1, large text < 3:1 (AA)
- Check focus indicator contrast (3:1 minimum)
- Verify information not conveyed by color alone

### 3. Keyboard Navigation
- All interactive elements reachable via Tab
- Logical tab order (matches visual order)
- Escape closes modals/dialogs
- Arrow keys navigate within composite widgets (tabs, menus, listboxes)
- Enter/Space activates buttons and links
- Focus trapped in modals
- Focus restored after modal close
- Skip navigation link present

### 4. Screen Reader Compatibility
- Page title is descriptive (`<title>` or `document.title`)
- Landmarks present: `<main>`, `<nav>`, `<header>`, `<footer>`
- Live regions for dynamic updates (`aria-live="polite"`)
- Status messages announced (toast notifications, form errors)
- Data tables have captions and proper headers
- Icons have screen reader text or are hidden

### 5. Motion & Preferences
- `prefers-reduced-motion` respected (disable animations)
- `prefers-color-scheme` respected (dark mode)
- `prefers-contrast` considered for high-contrast mode
- No auto-playing animations without user control

## Output Format

```
## Accessibility Audit Report

### Target: {component/page}
### Level: WCAG 2.1 {AA|AAA}
### Score: {X}/100

### Critical Issues ({count})
| # | Rule | Element | File:Line | Fix |
|---|------|---------|-----------|-----|
| 1 | {WCAG criterion} | {element} | {location} | {fix} |

### Warnings ({count})
| # | Rule | Element | File:Line | Fix |
|---|------|---------|-----------|-----|

### Passed Checks ({count})
- [x] Heading hierarchy
- [x] Alt text on images
- [x] Form labels
...

### Recommendations
1. {Prioritized improvement suggestion}
2. {Next improvement}
```
