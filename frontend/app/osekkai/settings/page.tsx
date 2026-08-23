import type { Metadata } from 'next';

import SettingsClient from '@/components/osekkai/settings-client';

export const metadata: Metadata = {
  title: '設定 | おっせかいおばさん',
  description: '標準設定で始め、通知、記憶、移動時間や予算を必要なときだけ変更できます。',
};

export default function SettingsPage() {
  return <SettingsClient />;
}
