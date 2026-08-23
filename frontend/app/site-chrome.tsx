'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import styles from './osekkai/osekkai.module.css';

type SiteChromeProps = {
  children: ReactNode;
};

const osekkaiLinks = [
  { href: '/osekkai', label: 'ホーム', exact: true },
  { href: '/osekkai/chat', label: '話す' },
  { href: '/osekkai/demo', label: 'デモ' },
  { href: '/osekkai/map', label: '地図' },
  { href: '/osekkai/settings', label: '設定' },
] as const;

function isNavActive(pathname: string, href: string) {
  return href === '/osekkai' ? pathname === href : pathname.startsWith(href);
}

export function SiteChromeFallback({ children }: SiteChromeProps) {
  return <OsekkaiChrome pathname="/osekkai">{children}</OsekkaiChrome>;
}

function OsekkaiChrome({ children, pathname }: SiteChromeProps & { pathname: string }) {
  return (
    <div className={styles.appShell}>
      <a className={styles.skipLink} href="#main-content">
        本文へ移動
      </a>
      <header className={styles.siteHeader}>
        <div className={styles.headerInner}>
          <Link className={styles.brand} href="/osekkai" aria-label="おっせかいおばさん ホーム">
            <span className={styles.brandMark} aria-hidden="true">
              <Image
                src="/osekkai/osekkai-place-chat-mark-v1.png"
                width={160}
                height={160}
                alt=""
              />
            </span>
            <span>
              <span className={styles.brandName}>おっせかいおばさん</span>
              <span className={styles.brandNote}>ちょうどいい距離を、いっしょに。</span>
            </span>
          </Link>
          <nav className={styles.nav} aria-label="おっせかいおばさんのメニュー">
            {osekkaiLinks.map((item) => {
              const active = isNavActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  className={active ? styles.navLinkActive : styles.navLink}
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main id="main-content" className={styles.pageFrame} tabIndex={-1}>
        {children}
      </main>
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <p>
            <strong>おっせかいおばさん</strong>
            <span>あなたの「今はそっとして」にも、ちゃんと耳をすませます。</span>
          </p>
          <div className={styles.footerLinks}>
            <Link href="/osekkai/settings">記憶と通知の設定</Link>
            <Link href="/osekkai/impact">判断の理由を見る</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default function SiteChrome({ children }: SiteChromeProps) {
  return <OsekkaiChrome pathname={usePathname()}>{children}</OsekkaiChrome>;
}
