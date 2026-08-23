# Frontend 実行方法（Next.js）

Next.jsアプリケーションは「おっせかいおばさん」専用です。UIは`/osekkai`、APIは`/api/osekkai`に集約し、`/`は`/osekkai`へredirectします。旧Tomo-san、市民相談、スタッフ画面はActive treeから`archive/tomo-san/`へ退避しています。

## セットアップ

Node.js 20.9 以上、npm、Python 3.11 以上を用意します。リポジトリ直下から PowerShell で次を実行します。

```powershell
python -m pip install -r agents-OpenClaw\requirements.txt
Set-Location frontend
Copy-Item .env.example .env
npm.cmd ci
npm.cmd run dev
```

ブラウザで `http://localhost:3000/osekkai` を開きます。開発時は `OSEKKAI_DEMO_MODE=true` のローカルデモで、外部APIや外部LLMを必要としません。

## 画面

| URL | 内容 |
|---|---|
| `/osekkai` | 概要と開始導線 |
| `/osekkai/chat` | 会話、推定差分、ターン単位の「これは覚えないで」、記憶管理 |
| `/osekkai/settings` | 記憶・PUSH同意、距離感、Quiet Hours、休止、データ全削除 |
| `/osekkai/demo` | Live時はSource同期→Calendar→Routes→複数候補、P0時は再現可能なオフラインデモ |
| `/osekkai/map` | 推薦外・満席・中止を含む取得済み全EventのMapと一覧fallback |
| `/osekkai/impact` | PUSH/no-PUSH の理由、Episode、分類付き KPI |

`/osekkai/demo` の初回表示では、Python のユーザー単位lock内で、Profileが未変更の初期値であり、会話とEpisodeがまだないことを確認してから、デモProfileを原子的にseedします。すでに設定や進捗がある場合は何も変更しません。手動の「デモをリセット」は別の破壊的操作で、確認欄へ「リセット」と入力した場合だけ、現在の匿名sessionのProfile、会話、判断、feedback、KPIを削除して固定fixtureの初期状態へ戻します。

P0では、合成した4時間のFree Window、出典・checksum付きsnapshot、合成移動時間を使い、Liveとは明示的に区別します。Live用のProvider、Calendar FreeBusy、Routes、Scheduler、Event Map、複数候補UIは実装済みです。実Google通信にはBillingを紐付けたprojectのOAuth Clientと制限付きAPI key、Lu.ma/Doorkeeperには利用許可のあるCredentialが必要です。

## 環境変数

`.env.example` を `.env` にコピーし、必要に応じて変更します。既に`.env`がある場合は上書きしません。

- `OPENCLAW_ROOT`: Python ルート。既定値は `../agents-OpenClaw`
- `OPENCLAW_PYTHON_BIN`: 使用する Python 実行ファイル
- `OSEKKAI_DATA_ROOT`: ランタイムデータの保存先。Git 追跡対象外の専用領域にする
- `OSEKKAI_SESSION_SECRET`: 署名付き匿名セッション用。本番では32 byte以上のランダム値が必須
- `OSEKKAI_SESSION_SECRET_PREVIOUS`: 鍵ローテーション中だけ旧鍵を指定
- `OSEKKAI_DEMO_MODE`: `true` で P0 デモ。`false` ではデモ fixture/seed/resetを使用しない
- `OSEKKAI_TIMEZONE`: 既定値 `Asia/Tokyo`
- `OSEKKAI_DATA_RETENTION_DAYS`: 会話・根拠の保持日数
- `OSEKKAI_BRIDGE_TIMEOUT_MS`: Next.js–Python ブリッジの timeout
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI`: Calendar OAuth Web Client
- `OSEKKAI_CREDENTIAL_ENCRYPTION_KEY`: OAuth state/tokenのFernet暗号化key
- `GOOGLE_ROUTES_API_KEY`: server側Routes/Geocoding用key
- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`: browser側Maps JavaScript用key
- `OSEKKAI_LIVE_ORIGIN_LATITUDE` / `OSEKKAI_LIVE_ORIGIN_LONGITUDE`: Live Demoの大まかな出発地点
- `LUMA_ICAL_URL`: 主催者・利用者が共有を許可したiCal URL
- `DOORKEEPER_API_TOKEN`: Doorkeeper API token

Live起動、Google Cloud、Source同期の完全な手順はRepository rootの[README.md](../README.md#live-demo設定)を参照してください。FrontendがPython childへ渡す環境変数はallowlist方式で、Session secretや無関係なapplication secretは継承しません。

## 30日保持の無人メンテナンス

既定30日の自動削除対象は、会話本文と推定根拠です。ProfileやEpisode内に複製された期限切れの推定根拠も除去しますが、明示設定、介入に必要な最小Episode、feedback、KPI自体は30日では自動削除せず、設定画面の全削除まで保持します。`memoryConsent=false` の場合も、会話本文・推定・根拠は保存せず、本人が指定した休止などの明示制御とサービス提供に必要な最小Episodeだけを保存できます。冪等処理のledgerは24時間保持し、「これは覚えないで」の本文はledgerにも保存しません。

通常APIは、現在の利用者のcleanupと短い全体バッチを実行します。API trafficが途絶えたnamespaceにも保持処理を適用するには、リポジトリ直下で次のコマンドを外部の日次schedulerから実行します。

```powershell
python agents-OpenClaw\scripts\osekkai_maintenance.py --retention-days 30 --json
```

この独立したPythonプロセスは `frontend/.env` を自動では読みません。schedulerにはWebアプリと同じ `OSEKKAI_DATA_ROOT`、`NODE_ENV`、`OSEKKAI_DEMO_MODE` を明示してください。demo modeの時計は再現性のため2019年の固定時刻であり、`--force` は走査を開始・再開しても時刻を進めません。本番の保持処理では `NODE_ENV=production` かつ `OSEKKAI_DEMO_MODE=false` を使用します。

workerは1回の起動で保持カーソルを有限個の全バッチまで進めます。個別namespaceが破損中または別処理によりロック中でも全体を中断せず、`skippedNamespaces` に `corrupt_or_unreadable`、`invalid_stored_data`、`invalid_or_unwritable`、または `lock_busy` を記録します。skipされたnamespaceは同じ起動中には再試行されません。終了コード0だけで完了と判断せず、JSONの `status`、`cycleCompleted`、`usersSkipped` を監視し、未完了またはskipがあれば警告・再実行してください。通常は直近24時間に走査完了済みなら `status=not_due` で終了します。Windows タスクスケジューラやcronの登録と監視は環境ごとに行い、このリポジトリは自動設定しません。

## P0 リソース保護

`/api/osekkai` は短時間のインメモリ制限をクライアント IP と署名済み匿名 user ID の両方に適用します。匿名 session の新規発行には、さらに低い IP 単位の上限があります。Python CLI は bounded FIFO permit pool（既定4プロセス、ハード上限16）で実行し、queue が満杯または待機期限切れの場合は固定文面の 429/503 と `Retry-After` を返します。

これらはメモリ上限を持つ **instance-local** の防御です。multi-instance / serverless 構成の全体quotaは保証しないため、公開本番環境ではingressに共有rate-limit serviceを追加してください。self-hosted productionで `OSEKKAI_TRUST_PROXY_IP_HEADERS=true` を使えるのは、信頼するreverse proxyが呼出元指定のforwarding headerを除去または上書きする場合だけです。未設定時はspoofingを避けるため共有fail-safe IP bucketを使い、Vercel上ではplatform headerを自動的に信頼します。

JSON storeは、1ファイル2 MiB、1ユーザーあたり会話2,000件かつ8 MiB、Episode 2,000件かつ16 MiB、冪等ledger 2,000件を上限にします。一方、全ユーザーを合算したdisk容量やnamespace数のglobal capはありません。公開本番環境では、永続volumeのOS/container quota、空き容量の監視と警告、バックアップと削除運用も別途用意してください。

調整項目は `.env.example` の `OSEKKAI_BRIDGE_MAX_CONCURRENCY`、`OSEKKAI_BRIDGE_MAX_QUEUE`、`OSEKKAI_BRIDGE_QUEUE_TIMEOUT_MS`、`OSEKKAI_RATE_LIMIT_REQUESTS`、`OSEKKAI_SESSION_ISSUE_RATE_LIMIT`、`OSEKKAI_RATE_LIMIT_WINDOW_MS`、`OSEKKAI_RATE_LIMIT_MAX_KEYS`、`OSEKKAI_TRUST_PROXY_IP_HEADERS` です。

## テスト

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run generate:contracts
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build

Set-Location ..\agents-OpenClaw
python -m compileall scripts tests
python -m unittest discover -s tests -p "test_osekkai_*.py" -v
python scripts/osekkai_contracts.py --validate-all
python scripts/osekkai_run.py --demo --reset --user-id 00000000-0000-4000-8000-000000000001 --json
```

テストは一時データ領域を使います。実ランタイムデータは `agents-OpenClaw/data/osekkai/` にあり、リポジトリの `.gitignore` で追跡対象外です。
