import type { Metadata } from 'next';

import MapClient from '@/components/osekkai/map-client';

export const metadata: Metadata = {
  title: 'Event地図 | おっせかいおばさん',
  description: '取得したEventを募集状態とともに地図と一覧で探せます。自分でも気になる場所を探せます。',
};

export default function MapPage() {
  return <MapClient />;
}
