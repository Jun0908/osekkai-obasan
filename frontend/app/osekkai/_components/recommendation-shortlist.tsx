import type { Opportunity, RankedOpportunity } from '@/lib/osekkai/types.generated';
import ConnectionEvidenceView from './connection-evidence';
import styles from '../osekkai.module.css';

type Action = 'accepted' | 'declined' | 'pause_one_week' | 'revisit';

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

function classificationLabel(value?: string): string {
  return ({
    raw_open_data: 'Open Data', live_provider: 'Live Provider', ai_derived: 'AI Derived',
    organizer_verified: 'Organizer Verified', private_user_data: 'Private', synthetic_demo: 'Demo',
  } as Record<string, string>)[value ?? ''] ?? 'Source Verified';
}

export default function RecommendationShortlist({
  opportunities,
  ranking,
  onAction,
  busy,
}: {
  opportunities: Opportunity[];
  ranking: RankedOpportunity[];
  onAction?: (action: Action, opportunity: Opportunity) => void;
  busy?: string;
}) {
  const byId = new Map(opportunities.map((opportunity) => [opportunity.id, opportunity]));
  const ranked = ranking.flatMap((item) => {
    const opportunity = byId.get(item.opportunityId);
    return opportunity ? [{ item, opportunity }] : [];
  });
  if (!ranked.length) {
    return (
      <div className={styles.emptyRecommendation}>
        <strong>いまPUSHできる候補はありません。</strong>
        <p>架空のEventは作りません。Sourceの接続・現在の募集状態・Calendar・Routesを確認してください。</p>
      </div>
    );
  }
  return (
    <div className={styles.recommendationGrid}>
      {ranked.map(({ item, opportunity }) => (
        <article className={styles.recommendationCard} key={opportunity.id}>
          <div className={styles.rankFlag}><span>#{item.rank}</span> おばさんの推し</div>
          <div className={styles.cardSourceRow}>
            <span>{classificationLabel(opportunity.sourceClassification)}</span>
            <span>{opportunity.provider}</span>
            <time dateTime={opportunity.revalidatedAt ?? opportunity.capturedAt}>
              確認 {dateLabel(opportunity.revalidatedAt ?? opportunity.capturedAt)}
            </time>
          </div>
          <h3>{opportunity.title}</h3>
          <p className={styles.eventWhen}>{dateLabel(opportunity.startsAt)} · {opportunity.address}</p>
          <div className={styles.eventFacts}>
            <span>Google Routes {opportunity.travelEstimate.minutes}分</span>
            <span>{opportunity.priceYen === null ? '料金未確認' : opportunity.priceYen === 0 ? '無料' : `${opportunity.priceYen.toLocaleString()}円`}</span>
            <span>{opportunity.registrationStatus === 'open' ? '募集中' : opportunity.registrationStatus}</span>
            {opportunity.capacity !== null && opportunity.capacity !== undefined ? <span>定員 {opportunity.capacity}人</span> : null}
          </div>
          <div className={styles.obasanReason}>
            <span aria-hidden="true">お</span>
            <div>
              <strong>{item.recommendationReasons[0]?.text}</strong>
              <ul>
                {item.recommendationReasons.slice(1, 4).map((reason) => <li key={reason.code}>{reason.text}</li>)}
              </ul>
            </div>
          </div>
          <ConnectionEvidenceView evidence={opportunity.connectionEvidence} />
          <div className={styles.recommendationActions}>
            <a className={styles.primaryCardAction} href={opportunity.sourceUrl} target="_blank" rel="noreferrer">行ってみる ↗</a>
            {onAction ? (
              <>
                <button type="button" disabled={Boolean(busy)} onClick={() => onAction('declined', opportunity)}>これは違う</button>
                <button type="button" disabled={Boolean(busy)} onClick={() => onAction('pause_one_week', opportunity)}>今回は無理</button>
                <button type="button" disabled={Boolean(busy)} onClick={() => onAction('revisit', opportunity)}>次回も知らせて</button>
              </>
            ) : null}
          </div>
          <a className={styles.sourceLink} href={opportunity.sourceUrl} target="_blank" rel="noreferrer">公式Sourceを確認 ↗</a>
        </article>
      ))}
    </div>
  );
}
