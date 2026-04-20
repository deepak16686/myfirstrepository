import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'coverage', '.vite'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended, prettier],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Allow the shadcn-style colocation of CVA variants next to the
      // component export, and the common `router`/`loader` colocation in
      // router.tsx — both are baseline patterns in this codebase.
      'react-refresh/only-export-components': [
        'warn',
        {
          allowConstantExport: true,
          allowExportNames: [
            'badgeVariants',
            'buttonVariants',
            'router',
            'loader',
            'action',
            'meta',
            'links',
            'headers',
          ],
        },
      ],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  // The codebase uses a `_PascalCase` naming convention for the inner
  // implementation of `memo()`-wrapped components. This is a deliberate
  // style choice (the outer name is the exported component), but the
  // react-hooks plugin only recognises plain PascalCase. Relax the
  // rules-of-hooks rule for that pattern inside files that use it.
  {
    files: [
      'src/components/common/StatusRail.tsx',
      'src/components/layout/Sidebar.tsx',
      'src/components/layout/CategoryChips.tsx',
      'src/components/layout/StatsStrip.tsx',
      'src/components/tools/ToolsCompactView.tsx',
      'src/components/cards/ToolCard.tsx',
    ],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
    },
  },
  // Test setup + test files allow a few additional patterns (node globals,
  // no react-refresh enforcement on mocks).
  {
    files: ['src/test/**/*.{ts,tsx}', 'src/**/__tests__/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  // router.tsx intentionally co-locates the `router` constant with two
  // private helper components (`PageFallback`, `Suspended`). That's a
  // load-bearing layout decision — moving them to their own files would
  // make the router harder to read — so the Fast Refresh warning is
  // acknowledged and suppressed only for this file.
  {
    files: ['src/router.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  // CredentialsPopover exports `hasCredentials` alongside the component
  // because the predicate is a trivial one-liner that's tightly coupled
  // to the popover's rendering logic (both short-circuit on "no credentials
  // pointer"). Splitting it into its own file would add ceremony without
  // improving clarity.
  {
    files: ['src/components/panels/CredentialsPopover.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
);
