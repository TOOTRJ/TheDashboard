import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Next 16.4 enables additional compiler diagnostics. Keep the observed
  // legacy findings visible while QA-01C reviews them; new files still use
  // upstream error severities. Existing Hooks and type checks stay unchanged.
  {
    files: [
      "scripts/browser-fixtures/paper-page.tsx",
      "src/app/(auth)/login/page.tsx",
      "src/app/(dashboard)/portfolio/page.tsx",
      "src/app/(dashboard)/probes/page.tsx",
      "src/components/dashboard/ActivityTable.tsx",
      "src/components/dashboard/Charts.tsx",
      "src/components/dashboard/KpiCards.tsx",
      "src/components/layout/Header.tsx",
      "src/components/nestegg/NesteggSavedPlanTabsToolbar.tsx",
      "src/components/nestegg/NesteggWalkthrough.tsx",
      "src/components/probes/TradeLog.tsx",
      "src/components/theme/ThemeToggle.tsx",
    ],
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  {
    files: ["src/app/(dashboard)/nestegg/page.tsx"],
    rules: {
      "react-hooks/immutability": "warn",
    },
  },
  {
    files: ["src/components/probes/PaperDashboard.tsx"],
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
