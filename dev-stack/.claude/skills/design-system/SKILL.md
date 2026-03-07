---
name: design-system
description: Manage design tokens, theme configuration, color palettes, typography, spacing, and component theming
---

# /design-system — Design Token & Theme Management

## Arguments
- `action`: `init` | `add-color` | `add-token` | `preview` | `audit` | `export`
- `name`: Token name (for add actions)
- `value`: Token value (for add actions)

## Actions

### `init` — Initialize Design System
Create the full design token infrastructure:

```
src/
├── styles/
│   ├── globals.css              # CSS custom properties (tokens)
│   ├── design-tokens.ts         # TypeScript token constants
│   └── animations.ts            # Framer Motion variants
├── lib/
│   └── utils.ts                 # cn() helper, color utilities
└── components/
    └── theme-provider.tsx       # Dark mode + system preference
```

**globals.css template:**
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;

    /* Extended palette */
    --success: 142.1 76.2% 36.3%;
    --success-foreground: 355.7 100% 97.3%;
    --warning: 38 92% 50%;
    --warning-foreground: 48 96% 89%;
    --info: 217.2 91.2% 59.8%;
    --info-foreground: 210 40% 98%;

    /* Chart colors */
    --chart-1: 12 76% 61%;
    --chart-2: 173 58% 39%;
    --chart-3: 197 37% 24%;
    --chart-4: 43 74% 66%;
    --chart-5: 27 87% 67%;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }
}
```

### `add-color` — Add New Color Token
- Add to both `:root` and `.dark` in globals.css
- Add to design-tokens.ts
- Update Tailwind config to include new color

### `add-token` — Add Spacing/Typography/Shadow Token
- Add CSS custom property
- Add to TypeScript constants
- Update Tailwind config

### `preview` — Preview Design Tokens
- Generate a visual preview page at `/design-system`
- Show all colors, typography, spacing, shadows, and component variants
- Side-by-side light/dark mode comparison

### `audit` — Audit Token Usage
- Scan codebase for hardcoded colors (hex, rgb, hsl not using tokens)
- Find hardcoded spacing values not on the scale
- Identify inconsistent border-radius usage
- Report shadcn/ui components not using project tokens

### `export` — Export Design Tokens
- Export as CSS custom properties
- Export as Tailwind config
- Export as TypeScript constants
- Export as Figma-compatible JSON
