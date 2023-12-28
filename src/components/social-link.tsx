import type { SocialLinkItem } from '../types'

export function SocialLink({ name, url, icon }: SocialLinkItem) {
  return (
    <a
      key={name}
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center justify-center"
      data-cursor="block"
    >
      <i className={`${icon} ${name === 'x' ? 'size-5' : 'size-6'}`}></i>
    </a>
  )
}
