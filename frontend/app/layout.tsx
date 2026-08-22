import type { Metadata } from 'next';
import { Suspense } from 'react';

import './globals.css';
import SiteChrome, { SiteChromeFallback } from './site-chrome';

export const metadata: Metadata = {
  title: {
    default: 'おっせかいおばさん',
    template: '%s',
  },
  description: '孤独を抱える人に、本人らしい半歩先の外出を提案するプロアクティブAI。',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <Suspense fallback={<SiteChromeFallback>{children}</SiteChromeFallback>}>
          <SiteChrome>{children}</SiteChrome>
        </Suspense>
      </body>
    </html>
  );
}
