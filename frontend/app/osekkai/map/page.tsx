import type { Metadata } from 'next';

import MapClient from '@/components/osekkai/map-client';

export const metadata: Metadata = {
  title: '東京の全Event地図 | おっせかいおばさん',
  description: '取得した東京の全Eventを、推薦可否や募集状態を隠さず地図と一覧で探せます。',
};

export default function MapPage() {
  return <MapClient />;
}
