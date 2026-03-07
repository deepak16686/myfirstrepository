---
name: new-component
description: Scaffold a production-quality Next.js component with TypeScript, TailwindCSS, shadcn/ui, all states, accessibility, and tests
---

# /new-component — Scaffold a Frontend Component

## Arguments
- `name`: Component name in PascalCase (e.g., `UserCard`, `DataTable`, `StatsPanel`)
- `type`: Component type — `display` | `input` | `navigation` | `feedback` | `layout` (optional, inferred from name)
- `path`: Target directory relative to `src/components/` (optional, defaults to `features/`)

## Process

### 1. Analyze Requirements
- Parse component name to infer purpose
- Check existing components to avoid duplication
- Identify which shadcn/ui primitives to compose from

### 2. Generate Files
Create the following file structure:
```
src/components/{path}/{ComponentName}/
├── {ComponentName}.tsx           # Main component with all states
├── {ComponentName}.skeleton.tsx  # Loading skeleton with shimmer
├── {ComponentName}.test.tsx      # Unit + accessibility tests
├── use-{component-name}.ts      # Custom hook (if stateful)
└── index.ts                     # Barrel export
```

### 3. Component Implementation

**Must include:**
- TypeScript interface with JSDoc for every prop
- `forwardRef` for DOM element access
- `displayName` for React DevTools
- Loading state → renders skeleton
- Error state → friendly message + retry button
- Empty state → illustration + CTA
- Dark mode support via `dark:` Tailwind classes
- Responsive breakpoints (mobile-first)
- Framer Motion entry animation
- `aria-*` attributes for accessibility
- Keyboard navigation support
- `cn()` utility for class merging

**Template:**
```tsx
"use client";

import { forwardRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface {Name}Props extends React.HTMLAttributes<HTMLDivElement> {
  /** ... */
}

const {Name} = forwardRef<HTMLDivElement, {Name}Props>(
  ({ className, ...props }, ref) => {
    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className={cn("rounded-lg border bg-card text-card-foreground shadow-sm", className)}
        {...props}
      />
    );
  }
);

{Name}.displayName = "{Name}";
export { {Name} };
```

### 4. Test Generation

**Must cover:**
- Renders with default props
- Renders loading skeleton
- Renders error state with retry
- Renders empty state
- Handles user interactions
- Keyboard navigation
- Accessibility audit (jest-axe)
- Dark mode class application
- Responsive layout at mobile/desktop

### 5. Post-Scaffold
- Add export to parent `index.ts` barrel file
- Print usage example with sample props
- Suggest related shadcn/ui components to install if missing
