import type { Metadata } from 'next';

import ImpactClient from '@/components/osekkai/impact-client';

export const metadata: Metadata = {
  title: 'Impact | おっせかいおばさん',
  description: 'PUSHとno-PUSHの理由、距離評価、分類付きKPIを確認します。',
};

export default function ImpactPage() {
  return <ImpactClient />;
}
