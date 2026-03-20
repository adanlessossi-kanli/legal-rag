import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        surface: "var(--surface)",
        "surface-hover": "var(--surface-hover)",
        border: "var(--border)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "accent-light": "var(--accent-light)",
        "accent-muted": "var(--accent-muted)",
        success: "var(--success)",
        "success-light": "var(--success-light)",
        danger: "var(--danger)",
        "danger-light": "var(--danger-light)",
        warning: "var(--warning)",
        "warning-light": "var(--warning-light)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow)",
        md: "var(--shadow-md)",
      },
      animation: {
        "typing-dot": "typing-dot 1.4s infinite",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;
