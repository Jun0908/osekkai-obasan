'use client';

import Link from 'next/link';
import { type FormEvent, useEffect, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import {
  clearOsekkaiSession,
  friendlyApiError,
  getOsekkaiSession,
  newIdempotencyKey,
  osekkaiRequest,
} from './api-client';
import {
  formatDateTime,
  normalizeProfile,
  type PreferenceMemory,
  type ProfileView,
} from './models';
import { InlineNotice, LoadingBlock, ModeBadge, PageIntro } from './ui';

type SettingsForm = Pick<
  ProfileView,
  | 'memoryConsent'
  | 'pushConsent'
  | 'quietStart'
  | 'quietEnd'
  | 'maxPushesPerWeek'
  | 'preferredTone'
  | 'maxTravelMinutes'
  | 'maxBudgetYen'
  | 'maxSocialIntensity'
>;

const defaultForm: SettingsForm = {
  memoryConsent: false,
  pushConsent: false,
  quietStart: '21:00',
  quietEnd: '08:00',
  maxPushesPerWeek: 2,
  preferredTone: 'gentle',
  maxTravelMinutes: 40,
  maxBudgetYen: 2000,
  maxSocialIntensity: 2,
};

function profileToForm(profile: ProfileView): SettingsForm {
  return {
    memoryConsent: profile.memoryConsent,
    pushConsent: profile.pushConsent,
    quietStart: profile.quietStart,
    quietEnd: profile.quietEnd,
    maxPushesPerWeek: profile.maxPushesPerWeek,
    preferredTone: profile.preferredTone,
    maxTravelMinutes: profile.maxTravelMinutes,
    maxBudgetYen: profile.maxBudgetYen,
    maxSocialIntensity: profile.maxSocialIntensity,
  };
}

const tones = [
  { value: 'gentle', label: 'やさしく', sample: '無理のない範囲で、どう？' },
  { value: 'casual', label: '気軽に', sample: 'ちょっと寄ってみる？' },
  { value: 'direct', label: 'はっきり', sample: 'この候補が条件に合います。' },
  { value: 'quiet', label: '短く静かに', sample: '近くで、30分だけ。' },
] as const;

function MemorySettingsItem({ item, onDeleteEvidence, onDeletePreference, deletingKey }: {
  item: PreferenceMemory;
  onDeleteEvidence: (id: string) => void;
  onDeletePreference: (key: string) => void;
  deletingKey: string;
}) {
  return (
    <li className={styles.memoryItem}>
      <div>
        <div className={styles.memoryTitleRow}>
          <strong>{item.label}</strong>
          {typeof item.confidence === 'number' ? (
            <span>確からしさ {Math.round(item.confidence * 100)}%</span>
          ) : null}
        </div>
        <p>{item.value}</p>
        {item.evidence.length ? (
          <ul className={styles.memoryEvidenceList} aria-label={`${item.label}の保存根拠`}>
            {item.evidence.map((evidence) => (
              <li key={evidence.id}>
                <small>
                  きっかけ: 「{evidence.text}」
                  {evidence.createdAt ? (
                    <>・<time dateTime={evidence.createdAt}>{formatDateTime(evidence.createdAt)}</time></>
                  ) : null}
                </small>
                <button
                  className={styles.ghostDangerButton}
                  type="button"
                  onClick={() => onDeleteEvidence(evidence.id)}
                  disabled={Boolean(deletingKey)}
                  aria-label={`${item.label}の根拠「${evidence.text}」を削除`}
                >
                  {deletingKey === `evidence:${evidence.id}` ? '削除中…' : 'この根拠を削除'}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <button
        className={styles.ghostDangerButton}
        type="button"
        onClick={() => onDeletePreference(item.key)}
        disabled={Boolean(deletingKey)}
        aria-label={`${item.label}の推定項目をすべて削除`}
      >
        {deletingKey === `preference:${item.key}` ? '削除中…' : '項目を削除'}
      </button>
    </li>
  );
}

async function fetchSettingsSnapshot() {
  const [raw, session] = await Promise.all([
    osekkaiRequest('/profile'),
    getOsekkaiSession(),
  ]);
  return { profile: normalizeProfile(raw), mode: session.dataMode };
}

export default function SettingsClient() {
  const [form, setForm] = useState<SettingsForm>(defaultForm);
  const [profile, setProfile] = useState<ProfileView>();
  const [mode, setMode] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [deletingKey, setDeletingKey] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [calendarMessage, setCalendarMessage] = useState('予定名・説明・場所・参加者は取得しません。');
  const [deleteText, setDeleteText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void fetchSettingsSnapshot()
      .then(({ profile: next, mode: nextMode }) => {
        if (!active) return;
        setProfile(next);
        setForm(profileToForm(next));
        setMode(nextMode);
        setError('');
      })
      .catch((reason: unknown) => {
        if (active) setError(friendlyApiError(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const update = <K extends keyof SettingsForm>(key: K, value: SettingsForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setNotice('');
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          operation: 'update_settings',
          updates: {
            memoryConsent: form.memoryConsent,
            pushConsent: form.pushConsent,
            quietHours: { start: form.quietStart, end: form.quietEnd, timezone: 'Asia/Tokyo' },
            maxPushesPerWeek: form.maxPushesPerWeek,
            preferredTone: form.preferredTone,
            maxTravelMinutes: form.maxTravelMinutes,
            maxBudgetYen: form.maxBudgetYen,
            maxSocialIntensity: form.maxSocialIntensity,
          },
          idempotencyKey: newIdempotencyKey('settings'),
        },
      });
      const next = normalizeProfile(raw);
      setProfile(next);
      setForm(profileToForm(next));
      setNotice('設定を保存しました。次の判断から反映します。');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setSaving(false);
    }
  };

  const pauseOneWeek = async () => {
    setPausing(true);
    setError('');
    setNotice('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          operation: 'pause_one_week',
          pauseOneWeek: true,
          idempotencyKey: newIdempotencyKey('pause'),
        },
      });
      const next = normalizeProfile(raw);
      setProfile(next);
      setNotice('1週間、こちらから声をかけません。7日後に自動解除されます。');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setPausing(false);
    }
  };

  const deletePreference = async (key: string) => {
    setDeletingKey(`preference:${key}`);
    setError('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          operation: 'remove_inferred_preference',
          inferredPreferenceKey: key,
          idempotencyKey: newIdempotencyKey('memory-delete'),
        },
      });
      setProfile(normalizeProfile(raw));
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setDeletingKey('');
    }
  };

  const deleteEvidence = async (evidenceId: string) => {
    setDeletingKey(`evidence:${evidenceId}`);
    setError('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          removeEvidenceId: evidenceId,
          idempotencyKey: newIdempotencyKey('evidence-delete'),
        },
      });
      setProfile(normalizeProfile(raw));
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setDeletingKey('');
    }
  };

  const deleteProfile = async () => {
    if (deleteText !== '削除') return;
    setDeleting(true);
    setError('');
    try {
      await osekkaiRequest('/profile', {
        method: 'DELETE',
        mutation: true,
        body: { confirm: true, idempotencyKey: newIdempotencyKey('profile-delete') },
      });
      clearOsekkaiSession();
      setDeleted(true);
      setDeleteOpen(false);
      setDeleteText('');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <LoadingBlock label="あなたの設定を読み込んでいます" />;
  }

  if (deleted) {
    return (
      <section className={styles.deletedState}>
        <span aria-hidden="true">✓</span>
        <p className={styles.eyebrow}>DELETED</p>
        <h1>記憶と履歴を削除しました。</h1>
        <p>
          この匿名セッションに結びついたプロフィール、会話、判断、フィードバックは削除されました。
          共有の公開データには影響しません。
        </p>
        <Link className={styles.primaryButton} href="/osekkai">ホームへ戻る</Link>
      </section>
    );
  }

  return (
    <>
      <PageIntro
        eyebrow="SETTINGS"
        title="設定"
        aside={<ModeBadge mode={mode} />}
      >
        <p>標準設定で始めています。必要なところだけ、あとから変更できます。</p>
      </PageIntro>

      {error ? <InlineNotice tone="error"><p>{error}</p></InlineNotice> : null}
      {notice ? <InlineNotice tone="success"><p>{notice}</p></InlineNotice> : null}

      <form className={styles.settingsForm} onSubmit={save}>
        <section className={styles.settingsSection} aria-labelledby="consent-heading">
          <div className={styles.settingsSectionHeader}>
            <span className={styles.settingsIcon} aria-hidden="true">◎</span>
            <div>
              <p className={styles.eyebrow}>CONSENT</p>
              <h2 id="consent-heading">覚えること、声をかけること</h2>
              <p>この2つは別々に選べます。</p>
            </div>
          </div>
          <div className={styles.toggleList}>
            <label className={styles.toggleRow}>
              <span>
                <strong>会話から距離感を学んでよい</strong>
                <small>会話の短い根拠と推定を、30日を目安に保存します。</small>
              </span>
              <input
                type="checkbox"
                role="switch"
                checked={form.memoryConsent}
                onChange={(event) => update('memoryConsent', event.target.checked)}
              />
            </label>
            <label className={styles.toggleRow}>
              <span>
                <strong>条件が合うとき、声をかけてよい</strong>
                <small>オフの間は、候補があってもPUSHしません。</small>
              </span>
              <input
                type="checkbox"
                role="switch"
                checked={form.pushConsent}
                onChange={(event) => update('pushConsent', event.target.checked)}
              />
            </label>
          </div>
        </section>

        <details className={styles.settingsAdvanced}>
          <summary>
            <span>
              <strong>詳細設定を変更する</strong>
              <small>通知時間・移動時間・予算・おっせかいの強さ</small>
            </span>
            <span aria-hidden="true">＋</span>
          </summary>

          <section className={styles.settingsSection} aria-labelledby="timing-heading">
          <div className={styles.settingsSectionHeader}>
            <span className={styles.settingsIcon} aria-hidden="true">◷</span>
            <div>
              <p className={styles.eyebrow}>WHEN</p>
              <h2 id="timing-heading">いつ、どのくらい</h2>
              <p>Quiet Hoursは日をまたいでも使えます。時刻は日本時間です。</p>
            </div>
          </div>
          <div className={styles.fieldGrid}>
            <label className={styles.field}>
              <span>静かにしてほしい時間・開始</span>
              <input
                type="time"
                value={form.quietStart}
                onChange={(event) => update('quietStart', event.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>静かにしてほしい時間・終了</span>
              <input
                type="time"
                value={form.quietEnd}
                onChange={(event) => update('quietEnd', event.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>1週間の声かけ上限</span>
              <select
                value={form.maxPushesPerWeek}
                onChange={(event) => update('maxPushesPerWeek', Number(event.target.value))}
              >
                <option value={0}>0回（声をかけない）</option>
                <option value={1}>1回まで</option>
                <option value={2}>2回まで</option>
                <option value={3}>3回まで</option>
                <option value={4}>4回まで</option>
              </select>
            </label>
          </div>
          <div className={styles.pauseRow}>
            <div>
              <strong>今週は、そっとしてほしい</strong>
              <p>
                {profile?.pauseUntil
                  ? `休止中です（${new Date(profile.pauseUntil).toLocaleDateString('ja-JP')}ごろまで）`
                  : '押すと、7日間こちらから声をかけません。'}
              </p>
            </div>
            <button className={styles.secondaryButton} type="button" onClick={pauseOneWeek} disabled={pausing}>
              {pausing ? '設定中…' : '今週は休む'}
            </button>
          </div>
          </section>

          <section className={styles.settingsSection} aria-labelledby="distance-heading">
          <div className={styles.settingsSectionHeader}>
            <span className={styles.settingsIcon} aria-hidden="true">↔</span>
            <div>
              <p className={styles.eyebrow}>HOW MUCH</p>
              <h2 id="distance-heading">おっせかいの強さ</h2>
              <p>本人設定より強い候補は出しません。</p>
            </div>
          </div>
          <label className={styles.rangeField}>
            <span>
              <strong>人との関わりの強さ</strong>
              <output htmlFor="social-intensity">{form.maxSocialIntensity} / 5</output>
            </span>
            <input
              id="social-intensity"
              type="range"
              min={0}
              max={5}
              step={1}
              value={form.maxSocialIntensity}
              onChange={(event) => update('maxSocialIntensity', Number(event.target.value))}
            />
            <span className={styles.rangeLabels}><small>0 ひとりで静かに</small><small>5 人と関わる</small></span>
          </label>
          <fieldset className={styles.toneFieldset}>
            <legend>声のかけ方</legend>
            <div className={styles.toneGrid}>
              {tones.map((tone) => (
                <label key={tone.value} className={styles.toneOption}>
                  <input
                    type="radio"
                    name="preferredTone"
                    value={tone.value}
                    checked={form.preferredTone === tone.value}
                    onChange={() => update('preferredTone', tone.value)}
                  />
                  <span><strong>{tone.label}</strong><small>「{tone.sample}」</small></span>
                </label>
              ))}
            </div>
          </fieldset>
          </section>

          <section className={styles.settingsSection} aria-labelledby="feasible-heading">
          <div className={styles.settingsSectionHeader}>
            <span className={styles.settingsIcon} aria-hidden="true">⌖</span>
            <div>
              <p className={styles.eyebrow}>FEASIBLE</p>
              <h2 id="feasible-heading">無理なく行ける範囲</h2>
              <p>条件を超える候補は、最初から除外します。</p>
            </div>
          </div>
          <div className={styles.fieldGrid}>
            <label className={styles.field}>
              <span>片道の移動時間</span>
              <span className={styles.inputWithSuffix}>
                <input
                  type="number"
                  min={0}
                  max={180}
                  step={5}
                  value={form.maxTravelMinutes}
                  onChange={(event) => update('maxTravelMinutes', Number(event.target.value))}
                />
                <span>分まで</span>
              </span>
            </label>
            <label className={styles.field}>
              <span>1回に使う予算</span>
              <span className={styles.inputWithSuffix}>
                <span>¥</span>
                <input
                  type="number"
                  min={0}
                  max={100000}
                  step={500}
                  value={form.maxBudgetYen}
                  onChange={(event) => update('maxBudgetYen', Number(event.target.value))}
                />
                <span>まで</span>
              </span>
            </label>
          </div>
          </section>
        </details>

        <div className={styles.saveBar}>
          <p>変更内容は、保存するまで反映されません。</p>
          <button className={styles.primaryButton} type="submit" disabled={saving}>
            {saving ? '保存しています…' : '設定を保存'}
          </button>
        </div>
      </form>

      <section className={styles.settingsSection} aria-labelledby="calendar-heading">
        <div className={styles.settingsSectionHeader}>
          <span className={styles.settingsIcon} aria-hidden="true">□</span>
          <div>
            <p className={styles.eyebrow}>GOOGLE FREE/BUSY</p>
            <h2 id="calendar-heading">動ける空き時間をつなぐ</h2>
            <p>{calendarMessage}</p>
          </div>
        </div>
        <div className={styles.privacyActions}>
          <a className={styles.primaryButton} href="/api/osekkai/calendar/connect">Google Calendarを接続</a>
          <button className={styles.secondaryButton} type="button" onClick={async () => {
            try {
              await osekkaiRequest('/calendar/disconnect', { method: 'POST', mutation: true, body: {} });
              setCalendarMessage('Google Calendarとの接続を削除しました。');
            } catch (reason) {
              setCalendarMessage(friendlyApiError(reason));
            }
          }}>接続を解除</button>
        </div>
      </section>

      <section className={styles.privacySection}>
        <div>
          <p className={styles.eyebrow}>YOUR DATA</p>
          <h2>覚えている内容は、あなたが決める。</h2>
          <p>
            会話と推定根拠の保存期間はP0では30日です。予定のタイトル、説明、参加者、場所は保存しません。
          </p>
        </div>
        <div className={styles.privacyActions}>
          <Link className={styles.secondaryButton} href="/osekkai/chat">好みを追加する</Link>
          <button className={styles.dangerButton} type="button" onClick={() => setDeleteOpen((current) => !current)}>
            すべての記憶と履歴を削除
          </button>
        </div>
        <details className={styles.memorySettingsDisclosure}>
          <summary>保存された好みを確認・削除</summary>
          {profile?.inferred.length ? (
            <ul className={styles.memoryList}>
              {profile.inferred.map((item) => (
                <MemorySettingsItem
                  key={item.key}
                  item={item}
                  onDeleteEvidence={(id) => void deleteEvidence(id)}
                  onDeletePreference={(key) => void deletePreference(key)}
                  deletingKey={deletingKey}
                />
              ))}
            </ul>
          ) : (
            <p className={styles.mutedPlaceholder}>保存された好みはまだありません。</p>
          )}
        </details>
        {deleteOpen ? (
          <div className={styles.deleteConfirmation} role="group" aria-labelledby="delete-title">
            <div>
              <strong id="delete-title">この操作は元に戻せません</strong>
              <p>
                この匿名セッションのProfile、会話、介入履歴、フィードバック、KPIを連鎖削除します。
                他のユーザーや共有の公開データは削除しません。
              </p>
            </div>
            <label className={styles.field}>
              <span>確認のため「削除」と入力</span>
              <input value={deleteText} onChange={(event) => setDeleteText(event.target.value)} autoComplete="off" />
            </label>
            <div className={styles.confirmActions}>
              <button className={styles.textButton} type="button" onClick={() => { setDeleteOpen(false); setDeleteText(''); }}>
                やめる
              </button>
              <button
                className={styles.dangerButtonSolid}
                type="button"
                disabled={deleteText !== '削除' || deleting}
                onClick={deleteProfile}
              >
                {deleting ? '削除しています…' : '完全に削除する'}
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </>
  );
}
