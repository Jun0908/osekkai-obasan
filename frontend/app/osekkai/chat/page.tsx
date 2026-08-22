import type { Metadata } from 'next';

import ChatClient from '@/components/osekkai/chat-client';

export const metadata: Metadata = {
  title: '話す | おっせかいおばさん',
  description: '気分や、望む距離感を話す画面です。',
};

export default function ChatPage() {
  return <ChatClient />;
}
