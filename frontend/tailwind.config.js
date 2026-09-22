/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        clinical: {
          950: "#070b12",
          900: "#0c1220",
          850: "#111827",
          800: "#151f33",
          700: "#1e293b",
          accent: "#06b6d4",
          accent2: "#22d3ee",
          muted: "#64748b",
          success: "#34d399",
          warn: "#fbbf24",
        },
      },
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        display: ["Outfit", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
