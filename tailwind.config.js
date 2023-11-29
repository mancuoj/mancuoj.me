const { iconsPlugin, getIconCollections } = require('@egoist/tailwindcss-icons')

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [
    iconsPlugin({
      // https://github.com/egoist/tailwindcss-icons
      collections: getIconCollections(['lucide', 'carbon', 'fluent-emoji', 'simple-icons']),
    }),
  ],
}
