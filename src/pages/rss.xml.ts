import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getPosts } from '../lib/posts';
import { site } from '../lib/site';

export async function GET(context: APIContext) {
  const posts = await getPosts();
  return rss({
    title: site.title,
    description: site.description,
    site: context.site ?? site.homeUrl,
    customData: `<language>${site.lang}</language>`,
    items: posts.map((post) => ({
      title: post.title,
      link: post.url,
      guid: post.url,
      pubDate: new Date(post.created.getTime() - site.timezone * 3600 * 1000),
      description: post.excerpt,
    })),
  });
}
