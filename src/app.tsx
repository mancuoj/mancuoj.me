import { IPadCursorProvider, useIPadCursor } from 'ipad-cursor/react'
import { cursorConfig, intro, socialLinks } from './config'
import { SocialLink } from './components/social-link'
import { ThemeProvider } from './components/theme-provider'

export default function App() {
  useIPadCursor()

  return (
    <ThemeProvider>
      <IPadCursorProvider config={cursorConfig}>
        <div className="h-screen flex items-center bg-slate-50 text-blue-950 dark:bg-gray-950 dark:text-blue-50">
          <div className="flex gap-8 max-w-3xl mx-auto">
            <div className="size-20 rounded-full" data-cursor="block" data-cursor-style="radius: 50%">
              <img src="/avatar.png" alt="avatar" />
            </div>
            <div className="flex flex-col content-between gap-4">
              <h1 className="font-bold font-serif text-3xl" data-cursor="text">
                {intro}
              </h1>
              <div className="flex gap-3 justify-end">
                {socialLinks.map(item => <SocialLink {...item} />)}
              </div>
            </div>
          </div>
        </div>
      </IPadCursorProvider>
    </ThemeProvider>
  )
}
