import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'おっせかいおばさん',
  description: '好きなことをひとつ話すだけ。東京に今ある、人とつながり続けられるEventを提案します。',
};

export default function OsekkaiLayout({ children }: { children: ReactNode }) {
  return children;
}
