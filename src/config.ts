import type { IpadCursorConfig } from 'ipad-cursor'
import type { SocialLinkItem } from './types'

export const intro = `Hi, I'm mancuoj`

export const socialLinks: SocialLinkItem[] = [
  {
    name: 'github',
    url: 'https://github.com/mancuoj',
    icon: 'i-simple-icons-github',
    color: '#C9D1D9',
  },
  {
    name: 'x',
    url: 'https://x.com/humancuoj',
    icon: 'i-simple-icons-x',
    color: '#E7E9EA',
  },
  {
    name: 'juejin',
    url: 'https://juejin.cn/user/3466105460624760',
    icon: 'i-simple-icons-juejin',
    color: '#007FFF',
  },
  {
    name: 'bilibili',
    url: 'https://space.bilibili.com/44805047',
    icon: 'i-simple-icons-bilibili',
    color: '#00A1D6',
  },
  {
    name: 'Blog',
    url: 'https://blog.mancuoj.me',
    icon: 'i-carbon-ai-status',
    color: '#E9DE62',
  },
  {
    name: 'Garden',
    url: 'https://garden.mancuoj.me',
    icon: 'i-fluent-emoji-potted-plant',
  },
]

export const cursorConfig: IpadCursorConfig = {
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
