import type { MapEventSummary } from '@/lib/osekkai/types.generated';
import styles from '../osekkai.module.css';

function timeLabel(value: string) {
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

export default function EventClusterSheet({
  events,
  onSelect,
  onClose,
}: {
  events: MapEventSummary[];
  onSelect: (event: MapEventSummary) => void;
  onClose: () => void;
}) {
  return (
    <aside className={styles.mapSheet} aria-label={`この地点のEvent${events.length}件`}>
      <button className={styles.mapSheetClose} type="button" onClick={onClose} aria-label="Event一覧を閉じる">×</button>
      <div className={styles.mapFallbackList}>
        <div><h2>この地点のEvent</h2><span>{events.length}件</span></div>
        <ul>
          {events.map((event) => (
            <li key={event.id} data-status={event.status}>
              <button type="button" onClick={() => onSelect(event)}>
                <strong>{event.title}</strong>
                <span>{timeLabel(event.startsAt)} · {event.venueName || event.address || '場所未確認'} · {event.provider}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
