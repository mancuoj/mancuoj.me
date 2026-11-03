import { createMarkdownProcessor } from '@astrojs/markdown-remark';
import remarkLinkify from 'remark-linkify-regex';
import { visit } from 'unist-util-visit';

function rehypeAbsoluteLinks() {
  return (tree: any) => {
    visit(tree, 'element', (node: any) => {
      if (node.tagName !== 'a' || !node.properties?.href) return;
      const href = String(node.properties.href);
      if (!/^(https?:|mailto:|#|\/)/i.test(href)) {
        node.properties.href = `https://${href}`;
      }
      const child = node.children?.length === 1 ? node.children[0] : null;
      if (child?.type === 'text' && /^https?:\/\//i.test(child.value)) {
        child.value = child.value.replace(/^https?:\/\//i, '');
      }
    });
  };
}

let renderer: Awaited<ReturnType<typeof createMarkdownProcessor>> | undefined;
let pending: Promise<Awaited<ReturnType<typeof createMarkdownProcessor>>> | undefined;

function getRenderer() {
  pending ??= createMarkdownProcessor({
    remarkPlugins: [remarkLinkify(/(?:https?:\/\/|www\.)[^\s<]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/[^\s<]*)?/gi)],
    rehypePlugins: [rehypeAbsoluteLinks],
    shikiConfig: {
      themes: { light: 'github-light', dark: 'github-dark' },
      wrap: true,
    },
  });
  return pending;
}

export async function renderMarkdown(markdown: string): Promise<string> {
  renderer ??= await getRenderer();
  const { code } = await renderer.render(markdown);
  return code;
}
