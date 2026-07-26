import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [".next/**", "next-env.d.ts", "node_modules/**"],
  },
  {
    rules: {
      // Next 16 / eslint-plugin-react-hooks is stricter; existing patterns need a
      // dedicated pass before re-enabling these compiler-oriented rules.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
    },
  },
];

export default eslintConfig;
