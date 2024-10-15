import type { Config } from 'tailwindcss'
import { iconsPlugin, getIconCollections } from '@egoist/tailwindcss-icons'
import defaultTheme from 'tailwindcss/defaultTheme'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', ...defaultTheme.fontFamily.sans],
        serif: ['"Source Serif 4 Variable"', ...defaultTheme.fontFamily.serif],
      },
    },
  },
  plugins: [
    iconsPlugin({
      collections: getIconCollections(['lucide']),
    }),
  ],
} satisfies Config
