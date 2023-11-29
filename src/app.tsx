import type { IpadCursorConfig } from 'ipad-cursor'
import { IPadCursorProvider, useIPadCursor } from 'ipad-cursor/react'
import { ThemeProvider } from '@/components/theme-provider'

export default function App() {
  const config: IpadCursorConfig = {
    adsorptionStrength: 0.5,
    enableLighting: true,
    normalStyle: {
      backdropBlur: '20px',
    },
    blockStyle: {
      scale: 1.1,
      backdropBlur: '0px',
      durationBackdropFilter: '1s',
    },
  }
  useIPadCursor()

  return (
    <ThemeProvider>
      <IPadCursorProvider config={config}>
        <div className="h-screen flex justify-center items-center gap-4 bg-slate-50 text-blue-950 dark:bg-gray-950 dark:text-blue-50">
          <div className="h-12 w-12 rounded-full" data-cursor="block" data-cursor-style="radius: 50%">
            <img src="/avatar.png" alt="avatar" />
          </div>
          <h1 className="font-bold font-serif text-3xl" data-cursor="text">
            Hi, I'm&nbsp;
            <span data-cursor="block">
              mancuoj
            </span>
          </h1>
        </div>
      </IPadCursorProvider>
    </ThemeProvider>
  )
}
