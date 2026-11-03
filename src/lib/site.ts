import { z } from 'zod';
import raw from '../../config.json';

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
      icon: z.string(),
    }),
  ),
});

export const site = schema.parse(raw);
export const baseUrl = site.homeUrl.replace(/\/$/, '');

export function absoluteUrl(path: string): string {
  return new URL(path, `${baseUrl}/`).toString();
}
