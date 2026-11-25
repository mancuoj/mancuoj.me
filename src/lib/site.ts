import { z } from 'zod';
import raw from '../../config.json';

export const ICON_NAMES = ['github', 'x', 'mail', 'bilibili'] as const;
export type IconName = (typeof ICON_NAMES)[number];

const schema = z.object({
  title: z.string(),
  subtitle: z.string(),
  description: z.string(),
  author: z.string(),
  avatar: z.string(),
  repo: z.string(),
  homeUrl: z.url(),
  lang: z.string(),
  timezone: z.number(),
  showRss: z.boolean(),
  sitemap: z.boolean(),
  excludeLabels: z.array(z.string()),
  pinLabel: z.string().nullable().optional(),
  social: z.array(
    z.object({
      label: z.string(),
      url: z.string(),
      icon: z.enum(ICON_NAMES),
    }),
  ),
});

export const site = schema.parse(raw);

export function canonicalPath(pathname: string): string {
  const cleaned = pathname.replace(/\/index\.html$/, '/').replace(/\.html$/, '');
  if (cleaned.length > 1 && cleaned.endsWith('/')) return cleaned.slice(0, -1);
  return cleaned || '/';
}
