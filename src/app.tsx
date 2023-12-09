import type { IpadCursorConfig } from 'ipad-cursor'
import { IPadCursorProvider, useIPadCursor } from 'ipad-cursor/react'
import { ThemeProvider } from '@/components/theme-provider'

interface SocialLink {
  name: string
  url: string
  icon: string
  color?: string
}

const socialLinks: SocialLink[] = [
  {
    name: 'GitHub',
    url: 'https://github.com/mancuoj',
    icon: 'i-simple-icons-github',
    color: '##333333',
  },
  {
    name: 'x',
    url: 'https://x.com/humancuoj',
    icon: 'i-simple-icons-x',
    color: '#000000',
  },
  {
    name: 'Juejin',
    url: 'https://juejin.cn/user/3466105460624760',
    icon: 'i-simple-icons-juejin',
    color: '#0284c7',
  },
  {
    name: 'Bilibili',
    url: 'https://space.bilibili.com/44805047',
    icon: 'i-simple-icons-bilibili',
    color: '#db2777',
  },
  {
    name: 'Blog',
    url: 'https://blog.mancuoj.me',
    icon: 'i-carbon-ai-status',
  },
  {
    name: 'Garden',
    url: 'https://garden.mancuoj.me',
    icon: 'i-fluent-emoji-potted-plant',
  },
]

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
        <div className="h-screen flex items-center bg-slate-50 text-blue-950 dark:bg-gray-950 dark:text-blue-50">
          <div className="flex gap-8 max-w-3xl mx-auto">
            <div className="h-20 w-20 rounded-full" data-cursor="block" data-cursor-style="radius: 50%">
              <img src="/avatar.png" alt="avatar" />
            </div>
            <div className="flex flex-col content-between gap-4">
              <h1 className="font-bold font-serif text-3xl" data-cursor="text">
                Hi, I'm
                {' '}
                mancuoj
              </h1>
              <div className="flex gap-3 justify-end">
                {
                  socialLinks.map((item, index) => (
                    <a
                      key={index}
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-center filter grayscale hover:filter-none"
                      data-cursor="block"
                    >
                      <i className={`w-6 h-6 ${item.icon}`}></i>
                    </a>
                  ))
                }
              </div>
            </div>
          </div>
        </div>
      </IPadCursorProvider>
    </ThemeProvider>
  )
}
