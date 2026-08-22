import type { Metadata } from 'next';

import SettingsClient from '@/components/osekkai/settings-client';

export const metadata: Metadata = {
  title: '距離と記憶の設定 | おっせかいおばさん',
  description: '通知、Quiet Hours、記憶、移動時間や予算を設定します。',
};

export default function SettingsPage() {
  return <SettingsClient />;
}
