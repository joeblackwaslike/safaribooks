import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import FeatureCards from '@site/src/components/FeatureCards';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className="install-command">
          <code>uv tool install safaribooks</code>
        </div>
        <div className={styles.buttons}>
          <Link
            className="button button--primary button--lg"
            to="/docs/getting-started">
            Get Started
          </Link>
          <Link
            className="button button--secondary button--lg"
            to="/docs/reference/cli-commands"
            style={{marginLeft: '1rem'}}>
            CLI Reference
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Download O'Reilly books as EPUB"
      description="safaribooks downloads O'Reilly books as EPUB files. Async Python CLI with smart retries, rate limiting, and flexible authentication.">
      <HomepageHeader />
      <main>
        <FeatureCards />
      </main>
    </Layout>
  );
}
