import type { ConnectionEvidence, EventRouteResult, LiveEvent, RankedOpportunity } from '@/lib/osekkai/types.generated';
import ConnectionEvidenceView from './connection-evidence';
import styles from '../osekkai.module.css';

function dateLabel(value: string) {
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

export default function MapEventSheet({
  event,
  evidence,
  ranking,
  route,
  routeBusy,
  canRoute,
  onRoute,
  onClose,
}: {
  event: LiveEvent;
  evidence?: ConnectionEvidence;
  ranking?: RankedOpportunity;
  route?: EventRouteResult;
  routeBusy: boolean;
  canRoute: boolean;
  onRoute: () => void;
  onClose: () => void;
}) {
  const disabled = event.status !== 'scheduled' || !['open', 'not_required', 'waitlist'].includes(event.registrationStatus);
  return (
    <aside className={styles.mapSheet} aria-label={`${event.title}の詳細`}>
      <button className={styles.mapSheetClose} type="button" onClick={onClose} aria-label="Event詳細を閉じる">×</button>
      <div className={styles.mapSheetLabels}>
        {ranking ? <span className={styles.mapRank}>おすすめ #{ranking.rank}</span> : null}
        <span data-status={event.status}>{event.status}</span>
        <span>{event.sourceClassification === 'raw_open_data' ? 'Open Data' : 'Live Source'}</span>
      </div>
      <h2>{event.title}</h2>
      <p className={styles.mapSheetWhen}>{dateLabel(event.startsAt)}〜 · {event.venueName || event.address || '場所確認中'}</p>
      <div className={styles.mapSheetFacts}>
        <span>{event.priceYen === null ? '料金未確認' : event.priceYen === 0 ? '無料' : `${event.priceYen.toLocaleString()}円`}</span>
        <span>{event.registrationStatus}</span>
        {event.capacity !== null ? <span>定員 {event.capacity}人</span> : null}
        {event.participants !== null ? <span>参加 {event.participants}人</span> : null}
      </div>
      {ranking ? (
        <div className={styles.mapRecommendationReason}>
          <strong>おばさんのおすすめ理由</strong>
          {ranking.recommendationReasons.map((reason) => <p key={reason.code}>{reason.text}</p>)}
        </div>
      ) : null}
      <ConnectionEvidenceView evidence={evidence} />
      <div className={styles.mapRouteResult} aria-live="polite">
        {route ? (
          <><strong>Google Routes {route.minutes}分</strong><span>{route.mode === 'walk' ? '徒歩' : '公共交通'} · {route.distanceMeters.toLocaleString()}m</span></>
        ) : (
          <button type="button" disabled={!canRoute || routeBusy} onClick={onRoute}>
            {routeBusy ? '実移動時間を取得中…' : canRoute ? '現在地から実移動時間を見る' : '現在地または地域を指定してください'}
          </button>
        )}
      </div>
      <div className={styles.mapSheetSources}>
        <strong>Source</strong>
        <a href={event.sourceUrl} target="_blank" rel="noreferrer">{event.provider} ↗</a>
        {(event.sourceLinks ?? []).map((source) => (
          <a href={source.sourceUrl} target="_blank" rel="noreferrer" key={`${source.provider}-${source.sourceRecordId}`}>{source.provider} ↗</a>
        ))}
        <time dateTime={event.revalidatedAt}>最終確認 {dateLabel(event.revalidatedAt)}</time>
      </div>
      {disabled ? <button className={styles.mapDisabledCta} type="button" disabled>現在は申込できません</button> : <a className={styles.primaryCardAction} href={event.sourceUrl} target="_blank" rel="noreferrer">公式ページで確認 ↗</a>}
    </aside>
  );
}
