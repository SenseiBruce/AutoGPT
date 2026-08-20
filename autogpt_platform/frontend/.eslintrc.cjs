module.exports = {
  extends: [
    "next/core-web-vitals",
    "next/typescript",
    "plugin:storybook/recommended",
    "plugin:@tanstack/query/recommended",
  ],
  rules: {
    "react-hooks/exhaustive-deps": "off",
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-unused-vars": [
      "error",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
      },
    ],
  },
};
