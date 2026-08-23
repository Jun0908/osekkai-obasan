import type { Metadata } from 'next';

import LiveDemoClient from '@/components/osekkai/live-demo-client';

export const metadata: Metadata = {
  title: 'Live Demo | おっせかいおばさん',
  description: '東京都の最新Event、Google Calendar、Google Routesから複数候補を提案するLive Demoです。',
};

export default function DemoPage() {
  return <LiveDemoClient />;
}
