import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/index',
        'getting-started/installation',
        'getting-started/authentication',
        'getting-started/first-download',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      items: [
        'guides/downloading-books',
        'guides/playlists',
        'guides/docker',
        'guides/kindle-optimization',
        'guides/image-quality',
        'guides/environment-variables',
        'guides/session-resilience',
      ],
    },
    {
      type: 'category',
      label: 'Concepts',
      items: [
        'concepts/architecture',
        'concepts/api-migration',
        'concepts/epub-structure',
        'concepts/rate-limiting',
        'concepts/retry-logic',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: [
        'reference/cli-commands',
        'reference/configuration',
        'reference/models',
        'reference/exceptions',
      ],
    },
    {
      type: 'category',
      label: 'Examples',
      items: [
        'examples/single-book',
        'examples/multiple-books',
        'examples/playlist-download',
        'examples/docker-usage',
        'examples/custom-image-settings',
        'examples/title-search',
      ],
    },
    {
      type: 'category',
      label: 'Troubleshooting',
      items: [
        'troubleshooting/cookie-expiry',
        'troubleshooting/ssl-issues',
        'troubleshooting/common-errors',
        'troubleshooting/image-problems',
      ],
    },
  ],
};

export default sidebars;
