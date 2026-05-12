/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#f0f4ff',
          100: '#e0e9ff',
          400: '#6685ff',
          500: '#4f6ef7',
          600: '#3b55e6',
          700: '#2e42c4',
          900: '#1a2460',
        },
        surface: {
          900: '#0d0f1a',
          800: '#13162b',
          700: '#1c2040',
          600: '#242850',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
