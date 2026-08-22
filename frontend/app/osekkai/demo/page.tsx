import type { Metadata } from 'next';

import DemoClient from '@/components/osekkai/demo-client';

export const metadata: Metadata = {
  title: '12段階デモ | おっせかいおばさん',
  description: '声をかけない判断から、1件の提案、参加・再訪までを再現するオフラインデモです。',
};

export default function DemoPage() {
  return <DemoClient />;
}
