import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'おっせかいおばさん',
  description: '近づきすぎず、離れすぎず。あなたが一歩動ける瞬間だけ、東京がおっせかいする。',
};

export default function OsekkaiLayout({ children }: { children: ReactNode }) {
  return children;
}
