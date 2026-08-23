import type { Metadata } from 'next';

import JudgeDemoClient from '@/components/osekkai/judge-demo-client';

export const metadata: Metadata = {
  title: 'Judge Demo | おっせかいおばさん',
  description: 'GoogleログインやBackendなしで、誘う・引く・続ける距離感を実Event snapshotとともに再現する3 Storyの審査用Demoです。',
};

export default function DemoPage() {
  return <JudgeDemoClient />;
}
