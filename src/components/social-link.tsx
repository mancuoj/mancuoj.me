import type { SocialLinkItem } from '../types'

export function SocialLink({ name, url, color, icon }: SocialLinkItem) {
  return (
    <a
      key={name}
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center justify-center filter grayscale hover:grayscale-0"
      data-cursor="block"
      style={{ color }}
    >
      <i className={`${icon} ${name === 'x' ? 'size-5' : 'size-6'}`}></i>
    </a>
  )
}
