# Live Demo実装報告

更新日: 2026-08-23

## 結論

Plan2のLive Demoに必要なProvider、Event Mesh、Connection判定、Calendar、Routes、Scheduler、Next.js API、複数候補UI、全Event Mapはコード実装済みです。Credential不要の実Source同期、fixture統合テスト、PC/モバイルBrowser確認まで完了しました。

外部設定がない状態でLive成功を装わない設計です。現在はGoogle Cloud projectのBilling未紐付け、OAuth Client/Maps key未設定、Lu.ma iCal/Doorkeeper token未設定のため、実Google accountと3系統以上のLive Providerで最後までPUSHする最終Gateだけがblockedです。

## 実装範囲

| 領域 | 実装 | 状態 |
|---|---|---|
| Contract | Event、Series、Community、Source、Connection、Calendar callback、Event Routesを含む24 JSON Schema | 完了 |
| Provider | Tokyo CKAN、Lu.ma authorized iCal、Doorkeeper API、KCF official site | 完了。後二者のうちLu.ma/DoorkeeperはCredential待ち |
| Event Mesh | 正規化、同一開催回のdedup、各回保持、freshness、status、provenance | 完了 |
| Connection | 継続性、会話設計、共同活動、共食、solo evidence、sales risk、Level 0〜4 | 完了 |
| Calendar | OAuth state/PKCE/session binding、暗号化token、refresh/disconnect/delete、FreeBusyのみ | 実装完了・実account smoke待ち |
| Routes | WALK/TRANSIT、Geocoding、往復+滞在+buffer、quota/timeout/zero result | 実装完了・実API smoke待ち |
| Scheduler | interval、incremental cache、Source lock、retry/backoff、failure isolation、PUSH前再検証 | 完了 |
| API | Source sync/status、Events、Live opportunities/decision、Calendar、Event Route | 完了 |
| Judge UI | Live Source Strip、複数Recommendation、根拠/Source/CTA、具体的な接続エラー | 完了 |
| Event Map | 全169 Event、filter、状態、一覧fallback、marker clustering、選択時Routes、位置情報拒否fallback | 実装完了・実Maps描画待ち |

## 実データ確認

2026-08-23に、Credential不要Sourceをforce syncしました。

- 東京都Open Data CKAN: 5 dataset、health=`healthy`
- 江東区文化コミュニティ財団: 169開催回、health=`healthy`
- merged Event Mesh: 169 Event
- Connection/募集状態の一次条件を満たすEvent: 26
- Routes確認済みOpportunity: 0（origin/API key未設定のためfail closed）
- Lu.ma / Doorkeeper: `credential_missing`

Mapは推薦条件と掲載条件を分離しているため、推薦0件でも169件を状態付きで閲覧できます。registration closed、根拠未確認、推薦対象外を隠しません。

## 検証結果

- Python: `test_osekkai_*.py` 131件成功
- Contract: 24 schemas / 19 instances成功
- Frontend: typecheck、ESLint、Vitest 18 files / 88件成功
- Production build: 成功
- Browser desktop 1440×900: Demo/Map、page横overflowなし
- Browser mobile 390×844: navigation、Demo、全Event一覧、Event detail、close、CTA、位置情報拒否fallbackを確認
- Live error: Calendar未接続をHTTP 409 `CALENDAR_NOT_CONNECTED`として具体的な接続導線付きで表示
- Map API keyなし: 169件を一覧fallbackへ保持

最終実行時のcommand結果は`Plan2.md`の各Task完了記録にも記載しています。

## Privacy・障害時動作

- Calendarは`calendar.freebusy` scopeと`freeBusy` endpointのみ。title、description、location、attendeesをContractで拒否
- OAuth token/stateはFernet暗号化し、匿名sessionとstateを紐付け、one-time/TTLを検証
- Calendar disconnectとProfile全削除の両方でcredentialを削除
- Browser現在地はEvent Route requestの間だけ利用し、Profile、Episode、idempotency ledgerへ保存しない
- Source停止/timeout/429/parser破損をSource単位で隔離
- Routes credential/quota/timeout/zero resultを分類し、合成値へfallbackしない
- canceled、sold out、expired、stale、PUSH前再検証不能は推薦から除外
- Mapは状態を明示して残すが、架空Eventを補充しない

## 外部blockerと解除手順

1. Google Cloud projectへBilling Accountをリンクする
2. Calendar API、Routes API、Geocoding API、Maps JavaScript APIを有効化する
3. OAuth Web Clientを作成し、callback URIを登録する
4. server/browserで分離し制限したAPI keyを作る
5. `frontend/.env.local`へGoogle Credential、暗号化key、Live originを設定する
6. 許可された`LUMA_ICAL_URL`と`DOORKEEPER_API_TOKEN`を設定する
7. `sources-sync --force`、Calendar connect、Demo、Mapを実Credentialでsmokeする

具体的な値、command、一次資料は`README.md`の「Live Demo設定」を参照してください。課金を伴うBilling紐付けや、利用許諾のないProvider取得は自動化していません。

## Scope外

PV/Demo動画の制作・書き出しはユーザー側で進行しているため、このRepositoryの完了Gateに含めません。Telegram等の配信Channelも、今回のJudge主経路であるWeb PUSH表示・Feedback・Mapの完成条件には含めていません。
