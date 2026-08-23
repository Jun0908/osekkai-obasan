import Image from 'next/image';
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
            あんた、何が好きなのよ。
            <br />
            好きなことを、ひとつ話すだけ。
            <br />
            東京の“次も会える場所”を探すで。
          </p>
          <p className={styles.heroSubcopy}>
            ヨガ、ボルダリング、料理、音楽。話した好みと反応を覚えて、
            本人にはまりそうな交流Eventを複数提案します。
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.primaryButtonLarge} href="/osekkai/chat">
              好みを話す
              <span aria-hidden="true">→</span>
            </Link>
            <Link className={styles.secondaryButtonLarge} href="/osekkai/demo">
              Live Demoを見る
            </Link>
          </div>
        </div>

        <div className={styles.heroVisual} aria-label="好みを聞いて交流イベントへ背中を押す、おっせかいおばさん">
          <div className={styles.orbitOuter}>
            <span className={styles.orbitLabelTop}>好みを聞く</span>
            <span className={styles.orbitDotOne} />
            <span className={styles.orbitDotTwo} />
            <div className={styles.orbitMiddle}>
              <span className={styles.orbitLabelSide}>人と会える</span>
              <div className={styles.obasanLogoStage}>
                <Image
                  className={styles.obasanLogoHero}
                  src="/osekkai/osekkai-obasan-logo-v1.png"
                  width={1248}
                  height={1248}
                  alt=""
                  priority
                />
                <span className={styles.logoOSeal} aria-hidden="true">
                  <b>お</b>
                  <small>おせっかい</small>
                </span>
              </div>
            </div>
          </div>
          <p>話すたび、反応するたび、提案があなたに近づきます。</p>
        </div>
      </section>

      <section className={styles.trustStrip} aria-label="デモのデータについて">
        <div>
          <span className={styles.trustIcon} aria-hidden="true">↺</span>
          <p><strong>東京の最新Event</strong><span>OpenClawが複数Sourceを更新</span></p>
        </div>
        <div>
          <span className={styles.trustIcon} aria-hidden="true">◷</span>
          <p><strong>Calendarは空き時間だけ</strong><span>予定名や参加者は取得しません</span></p>
        </div>
        <div>
          <span className={styles.trustIcon} aria-hidden="true">◎</span>
          <p><strong>実際に行ける距離</strong><span>Google Routesで移動時間を確認</span></p>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>HOW RECOMMENDATIONS GET BETTER</p>
          <h2>好きなことから、次に会える場所へ。</h2>
          <p>検索条件を並べる代わりに、ひとつ話す。あとは最新Event、空き時間、実移動を裏で合わせます。</p>
        </div>
        <div className={styles.threeCards}>
          <article className={styles.featureCard}>
            <span className={styles.cardNumber}>01</span>
            <div className={styles.featureGlyph} aria-hidden="true">“</div>
            <h3>好みをひとつ聞く</h3>
            <p>ヨガ、料理、音楽など、好きなことや次にやってみたいことから探し始めます。</p>
            <Link href="/osekkai/chat">会話の画面へ <span aria-hidden="true">→</span></Link>
          </article>
          <article className={styles.featureCard}>
            <span className={styles.cardNumber}>02</span>
            <div className={styles.featureGlyph} aria-hidden="true">◷</div>
            <h3>東京の“今”と合わせる</h3>
            <p>最新Event、Calendarの空き、Google Routesの実移動時間を一度に確認します。</p>
            <Link href="/osekkai/demo">Live Demoを見る <span aria-hidden="true">→</span></Link>
          </article>
          <article className={styles.featureCard}>
            <span className={styles.cardNumber}>03</span>
            <div className={styles.featureGlyph} aria-hidden="true">◎</div>
            <h3>交流が続く候補を、複数提案</h3>
            <p>本人にはまりそうな候補を、継続性と交流の根拠が強い順に伝えます。</p>
            <Link href="/osekkai/map">東京の全Eventを見る <span aria-hidden="true">→</span></Link>
          </article>
        </div>
      </section>

      <section className={styles.demoInvitation}>
        <div>
          <p className={styles.eyebrow}>60 SECOND LIVE DEMO</p>
          <h2>いま東京にある、“次も会える場所”を。</h2>
          <p>
            OpenClawの最新Event、Google Calendarの空き、Google Routesの実移動時間をつなぎ、
            交流が続く根拠を持つ複数候補まで一気に進みます。
          </p>
        </div>
        <Link className={styles.inkButton} href="/osekkai/demo">
          デモを始める <span aria-hidden="true">↗</span>
        </Link>
      </section>
    </>
  );
}
