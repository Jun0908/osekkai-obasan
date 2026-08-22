import Link from 'next/link';

import HubStatus from '@/components/osekkai/hub-status';
import styles from './osekkai.module.css';

export default function OsekkaiHomePage() {
  return (
    <>
      <section className={styles.hero}>
        <div className={styles.heroGlow} aria-hidden="true" />
        <div className={styles.heroContent}>
          <div className={styles.heroMeta}>
            <span className={styles.eyebrow}>Proactive AI Agent</span>
            <HubStatus />
          </div>
          <h1>おっせかいおばさん</h1>
          <p className={styles.heroCopy}>
            近づきすぎず、離れすぎず。
            <br />
            あなたが一歩動ける瞬間だけ、
            <br />
            東京がおっせかいする。
          </p>
          <p className={styles.heroSubcopy}>
            何かをさせるためではなく、あなたに合う距離を覚えるための会話から始めます。
            「今日はそっとして」も、たいせつな答えです。
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.primaryButtonLarge} href="/osekkai/chat">
              話してみる
              <span aria-hidden="true">→</span>
            </Link>
            <Link className={styles.secondaryButtonLarge} href="/osekkai/demo">
              デモの空き時間を使う
            </Link>
          </div>
          <button className={styles.disabledCalendarButton} type="button" disabled>
            <span className={styles.calendarGlyph} aria-hidden="true">□</span>
            Google Calendarをつなぐ
            <span className={styles.comingSoon}>P1で対応</span>
          </button>
        </div>

        <div className={styles.heroVisual} aria-label="近づきすぎない、ちょうどいい距離のイメージ">
          <div className={styles.orbitOuter}>
            <span className={styles.orbitLabelTop}>そっと見守る</span>
            <span className={styles.orbitDotOne} />
            <span className={styles.orbitDotTwo} />
            <div className={styles.orbitMiddle}>
              <span className={styles.orbitLabelSide}>いまだけ一歩</span>
              <div className={styles.orbitCenter}>
                <span aria-hidden="true">お</span>
                <small>あなたのペース</small>
              </div>
            </div>
          </div>
          <p>声をかけない判断も、記録して学びます。</p>
        </div>
      </section>

      <section className={styles.trustStrip} aria-label="デモのデータについて">
        <div>
          <span className={styles.trustIcon} aria-hidden="true">◷</span>
          <p><strong>予定の中身は見ません</strong><span>使うのは空いている時間だけ</span></p>
        </div>
        <div>
          <span className={styles.trustIcon} aria-hidden="true">◇</span>
          <p><strong>候補を作りません</strong><span>出典を確認できるものだけ</span></p>
        </div>
        <div>
          <span className={styles.trustIcon} aria-hidden="true">↺</span>
          <p><strong>いつでも変えられます</strong><span>記憶の閲覧・削除・休止に対応</span></p>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>HOW IT KEEPS ITS DISTANCE</p>
          <h2>急がない、決めつけない、追いかけない。</h2>
          <p>会話と本人の設定を優先し、提案する前に「今日は何もしない」を選べます。</p>
        </div>
        <div className={styles.threeCards}>
          <article className={styles.featureCard}>
            <span className={styles.cardNumber}>01</span>
            <div className={styles.featureGlyph} aria-hidden="true">“</div>
            <h3>ことばから距離を知る</h3>
            <p>疲れ具合や、話したい・話したくない気持ちを、本人が直せる仮説として扱います。</p>
            <Link href="/osekkai/chat">会話の画面へ <span aria-hidden="true">→</span></Link>
          </article>
          <article className={styles.featureCard}>
            <span className={styles.cardNumber}>02</span>
            <div className={styles.featureGlyph} aria-hidden="true">◷</div>
            <h3>動ける余白だけを見る</h3>
            <p>CalendarではFree/Busyだけを使い、予定のタイトル・場所・参加者は取得しません。</p>
            <Link href="/osekkai/demo">オフラインデモを見る <span aria-hidden="true">→</span></Link>
          </article>
          <article className={styles.featureCard}>
            <span className={styles.cardNumber}>03</span>
            <div className={styles.featureGlyph} aria-hidden="true">◎</div>
            <h3>理由ごと、1件だけ伝える</h3>
            <p>時間・移動・予算・人との関わり方を確かめ、合わなければ何も提案しません。</p>
            <Link href="/osekkai/impact">判断の理由を見る <span aria-hidden="true">→</span></Link>
          </article>
        </div>
      </section>

      <section className={styles.demoInvitation}>
        <div>
          <p className={styles.eyebrow}>2 MINUTE DEMO</p>
          <h2>「疲れた」から始まる、12の小さな場面。</h2>
          <p>
            最初は提案せず、後日、会話不要の候補をひとつだけ。承諾・距離評価・再訪までを、
            外部APIなしで何度でも再現できます。
          </p>
        </div>
        <Link className={styles.inkButton} href="/osekkai/demo">
          デモを始める <span aria-hidden="true">↗</span>
        </Link>
      </section>
    </>
  );
}
