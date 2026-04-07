import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0f172a',
          muted: '#111827',
          soft: '#1f2937',
          card: '#182235',
        },
        accent: {
          DEFAULT: '#38bdf8',
          strong: '#0ea5e9',
        },
        state: {
          ok: '#22c55e',
          ng: '#ef4444',
          recheck: '#f59e0b',
          warn: '#fb7185',
        },
      },
      boxShadow: {
        panel: '0 10px 30px rgba(15, 23, 42, 0.35)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
