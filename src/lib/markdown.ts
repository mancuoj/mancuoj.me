import { createMarkdownProcessor } from '@astrojs/markdown-remark';

let renderer: Awaited<ReturnType<typeof createMarkdownProcessor>> | undefined;
let pending: Promise<Awaited<ReturnType<typeof createMarkdownProcessor>>> | undefined;

function getRenderer() {
  pending ??= createMarkdownProcessor({
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
