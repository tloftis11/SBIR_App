/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Segoe UI"',
          'system-ui', 'sans-serif',
        ],
      },
      colors: {
        apple: {
          bg:        '#f5f5f7',
          surface:   '#ffffff',
          text:      '#1d1d1f',
          secondary: '#6e6e73',
          tertiary:  '#aeaeb2',
          blue:      '#0071e3',
          bluehover: '#0077ed',
          border:    'rgba(0,0,0,0.08)',
          divider:   'rgba(0,0,0,0.06)',
        },
      },
      boxShadow: {
        card:  '0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
        'card-hover': '0 4px 12px rgba(0,0,0,0.10), 0 2px 4px rgba(0,0,0,0.06)',
        input: 'inset 0 1px 2px rgba(0,0,0,0.06)',
      },
      borderRadius: {
        card: '12px',
        input: '10px',
        btn:  '980px',
      },
    },
  },
  plugins: [],
}
