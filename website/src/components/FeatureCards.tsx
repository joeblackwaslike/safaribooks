import type {ReactNode} from 'react';
import Heading from '@theme/Heading';

type Feature = {
  icon: string;
  title: string;
  description: string;
};

const features: Feature[] = [
  {
    icon: '⚡',
    title: 'Async Downloads',
    description:
      'Built on httpx and asyncio for parallel fetching of chapters, images, CSS, and fonts.',
  },
  {
    icon: '🔄',
    title: 'Smart Retries',
    description:
      'Tenacity-powered exponential backoff with jitter and Retry-After header awareness.',
  },
  {
    icon: '🔑',
    title: 'Flexible Auth',
    description:
      '5 different cookie extraction methods: browser export, DevTools, HTTP header, file import, and JS console.',
  },
  {
    icon: '📱',
    title: 'Kindle Ready',
    description:
      'CSS optimization for e-readers with the --kindle flag. Convert to AZW3/MOBI with Calibre.',
  },
  {
    icon: '📚',
    title: 'Playlist Support',
    description:
      'Download entire O\'Reilly playlists in a single command with --playlist.',
  },
  {
    icon: '🐳',
    title: 'Docker Support',
    description:
      'Containerized execution with the included Dockerfile. No local Python install needed.',
  },
];

function FeatureCard({icon, title, description}: Feature) {
  return (
    <div className="col col--4" style={{marginBottom: '1.5rem'}}>
      <div className="feature-card">
        <div className="feature-card__icon">{icon}</div>
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function FeatureCards(): ReactNode {
  return (
    <section style={{padding: '2rem 0'}}>
      <div className="container">
        <div className="row">
          {features.map((feature, idx) => (
            <FeatureCard key={idx} {...feature} />
          ))}
        </div>
      </div>
    </section>
  );
}
