/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        accent: {
          green:  "#10b981",  // normal cells
          yellow: "#fbbf24",  // stressed
          orange: "#f97316",  // senescent
          red:    "#7f1d1d",  // dead
          pink:   "#ec4899",  // alerts
        },
      },
    },
  },
  plugins: [],
};
