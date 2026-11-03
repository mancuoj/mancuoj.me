declare module 'remark-linkify-regex' {
  import type { Plugin } from 'unified';

  const linkifyRegex: (regex: RegExp) => Plugin;
  export default linkifyRegex;
}
