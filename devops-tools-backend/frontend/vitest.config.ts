/**
 * Standalone vitest config so the main vite.config.ts stays focused on dev
 * server + build output. Reuses the `@/` alias from tsconfig so imports
 * match runtime.
 *
 * NOTE on the type assertion: vitest bundles its own copy of `vite`, which
 * means the `Plugin` type from the project's top-level `vite` dependency
 * does not match the one vitest expects. Casting through `unknown` here is
 * the documented workaround (see vitest #5116) and is strictly confined to
 * the config plumbing — it never reaches runtime code.
 */
import { defineConfig as defineVitestConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineVitestConfig({
  // `react()` from @vitejs/plugin-react returns a plugin typed against the
  // project's hoisted `vite`; vitest's `defineConfig` resolves `Plugin`
  // against its own nested copy. The shapes are structurally identical so
  // the `unknown` hop is a type-only workaround.
  plugins: [react()] as unknown as import('vitest/config').UserConfig['plugins'],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
  },
});
