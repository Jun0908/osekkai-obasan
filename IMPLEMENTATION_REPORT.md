# 「おっせかいおばさん」P0 実装報告

- 対象: `osekkai-obasan-submit-main`
- 実装日: 2026-08-22
- 状態: P0 ローカル MVP の実装・最終受入完了。P1/P2 の機能と外部 adapter は未実装
- Repository分離後: 依存0件の旧Tomo-san資産を `archive/tomo-san/` へ退避。本文中のlegacy route退行確認は分離前P0の履歴証跡
- 製品境界: 既存 Tomo-san を改名・転用せず、UI `/osekkai`、API `/api/osekkai`、Python 専用ストアとして分離

検証環境は Windows / PowerShell、Node.js 22.22.1、npm 10.9.4、Python 3.11.9 です。作業開始時の観測では `frontend/node_modules`、lockfile、frontend test/typecheck script、Python 自動テストがない状態でした。現在は `frontend/package-lock.json` と非対話の build/typecheck/lint/test script、Python unittest を用意しています。Windows の正確な edition/build 番号は作業前ログに残っていません。

## 1. 変更した既存ファイル

作業ディレクトリに Git 履歴がないため、新規と既存の区分を履歴から機械的に復元することはできません。現行ツリーでは、主に次の既存設定・導線ファイルを最小変更しています。

- `README.md`、`PLAN.md`、`.gitignore`
- `frontend/package.json`、`frontend/package-lock.json`、`frontend/tsconfig.json`、`frontend/next.config.js`、ESLint/Vitest 設定
- `frontend/app/layout.tsx`、`frontend/app/site-chrome.tsx`
- `frontend/.env.example`、`frontend/README.md`

Tomo-san の `/tomo`、市民相談、PublicCase、スタッフ画面、Talking Photo のdomain logicは新製品へ取り込んでいません。共通layout/site chromeに `/osekkai` への入口を追加しつつ、新機能のUI・API・データ・Python処理は専用pathへ隔離しました。最終のlegacy route smoke testは成功しています。

## 2. 新規・P0 専用ファイル

- `contracts/osekkai/*.schema.json`: canonical JSON Schema
- `agents-OpenClaw/config/osekkai_policy.json`: version 付き Distance Policy
- `agents-OpenClaw/fixtures/osekkai/`: Free/Busy、Open Data raw/normalized snapshot、Profile fixture
- `agents-OpenClaw/scripts/osekkai_*.py`: contract、store、profile、chat、safety、policy、metrics、CLI、demo runner
- `agents-OpenClaw/tests/test_osekkai_*.py`: contract、privacy、security、concurrency、policy、metrics、demo test
- `frontend/app/osekkai/`: 5画面と専用 CSS
- `frontend/app/api/osekkai/`: session、chat、profile、freebusy、opportunities、decide、interventions、feedback、metrics、demo/seed、demo/reset APIと互換alias
- `frontend/components/osekkai/`: Chat、Settings、Demo、Impact、専用 chrome の UI
- `frontend/lib/osekkai/`: 生成型、runtime validator、API client
- `frontend/lib/server/osekkai-*.ts`: 匿名 session、CSRF/Origin 検証、Python bridge、Python SSOT adapter

## 3. 実装済み機能

- 明示設定と推定を分離した Distance Profile
- `memoryConsent` と `pushConsent` の独立管理
- 決定論的会話処理、Social Battery、明示 pause、Safety 優先
- ターン単位の「これは覚えないで」、記憶の閲覧・個別削除、Profile・会話・Episode等のユーザー単位アプリデータ削除
- Calendar 予定詳細を保持しない Free/Busy 契約
- 公式 Open Data snapshot の URL、dataset、license、capturedAt、checksum、field provenance
- guardrail-first の PUSH/no-PUSH 判定、候補フィルタ、決定論的な最大1件選択
- PUSH/no-PUSH の Intervention Episode、reason code、policy version、単調 sequence
- 4反応、3距離評価、cooldown、冪等 feedback
- Just-Right、Overreach、Under-Support、承諾率と分母ゼロの「未計測」
- demo、measured、reference estimate、unverified の分類分離
- 署名付き HttpOnly/SameSite=Strict 匿名 Cookie、鍵ローテーション、CSRF、Origin、Content-Type、body size、userId 注入の防御
- ユーザー単位lock、atomic JSON replace、対象mutationの冪等実行、24時間ledger、保持期限cleanup、推定根拠の連鎖scrub
- file 2 MiB、会話2,000件/8 MiB、Episode 2,000件/16 MiB、ledger 2,000件というユーザー単位quota
- Python同時実行、FIFO queue、request/session rate limit、429/503の `Retry-After` を持つinstance-local resource guard
- API trafficに依存しない日次保持worker（有限batch、cursor再開、破損/lock競合の個別skipとJSON状態出力）
- 完全未使用ユーザーだけを同一lock内で原子的に準備する非破壊demo seed
- `リセット` 入力で削除範囲を確認する破壊的reset、12段階デモ、canonical 7件の未検証指標を含むImpact画面

## 4. 未実装の P1/P2 機能

P1/P2 の機能と外部adapterは未実装です。将来用field・保存directory・計画上のscaffoldはありますが、Google OAuth/Calendar FreeBusy、ライブ Open Data 同期、Maps 移動可能性、Telegram PUSH/callback、介入配信scheduler、実参加・再訪の実データ化、Third Place/Role、UCLA-3、公式支援先、匿名行政集計、比較実験は接続していません。P0 の保持メンテナンスには日次実行可能な専用commandがありますが、OS schedulerへの登録は行いません。P0 のボタンや指標は、未接続のものを実運用済みと表示しません。

## 5. 起動方法

```powershell
python -m pip install -r agents-OpenClaw\requirements.txt
Set-Location frontend
Copy-Item .env.example .env.local
npm.cmd ci
npm.cmd run dev
```

`http://localhost:3000/osekkai` が新製品の入口です。従来トップ `/` と Tomo-san `/tomo` はそのまま残ります。

## 6. 必要な環境変数

P0 の一覧は `frontend/.env.example` にあります。ローカルデモでは `OPENCLAW_ROOT`、`OPENCLAW_PYTHON_BIN`、`OSEKKAI_DATA_ROOT`、`OSEKKAI_DEMO_MODE=true` を使います。本番環境では32文字以上の強い `OSEKKAI_SESSION_SECRET` が必須で、ローテーション中は `OSEKKAI_SESSION_SECRET_PREVIOUS` に旧鍵を指定できます。bridge concurrency/queue、request/session rate limit、信頼するproxy headerも環境変数で設定できます。

会話・推定根拠の既定30日保持を無人運用する場合は、外部の日次schedulerから次を実行します。`frontend/.env.local` は自動読込されないため、frontendと同じ `OSEKKAI_DATA_ROOT`、`NODE_ENV`、`OSEKKAI_DEMO_MODE` 等をworkerへ渡してください。demo modeの `clock_now()` は再現用の2019年固定時刻です。個別の破損namespaceとuser lock競合は理由付きでskipし、他のnamespaceを継続します。終了コード0でも `complete_with_skips` や `maintenance_lock_busy` があり得るため、JSONの `status`、`cycleCompleted`、`usersSkipped`、`skippedNamespaces` を監視します。OS schedulerの登録は環境依存のため実装範囲外です。

```powershell
python agents-OpenClaw\scripts\osekkai_maintenance.py --retention-days 30 --json
```

## 7. 2分デモ手順

1. freshな匿名セッションで `/osekkai/demo` を開く。自動seedは完全な未使用状態だけを非破壊で準備するため、手動resetは不要。
2. 「今週疲れた。何もしたくない」で Social Battery 低下と no-PUSH を確認する。
3. 「少し外に出たいが、話したくない」と合成4時間 Free Window を読む。
4. 出典付きの低強度候補が1件だけ PUSH されることを確認する。
5. 「行ってみる」、「ちょうどいい」、実参加、再訪のデモ操作を順に実行する。
6. `/osekkai/impact` で PUSH/no-PUSH 理由、Profile、Episode、分類付き KPI の更新を確認する。

デモは固定 fixture、固定時計、ローカル Python 処理だけで動き、外部 API を呼びません。参加・再訪は `classification=demo` であり、実測効果ではありません。

## 8. 実行したテストと結果

2026-08-22の最終確認で、次のコマンドをすべて実行しました。

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

結果は次のとおりです。

- `npm.cmd ci`: 458 packagesをlockfileから再導入、audit 0 vulnerabilities
- contract生成: 16 schemas、2回連続で同一出力、manifest `ea1b21980bf0`
- typecheck: PASS、ESLint: PASS
- Vitest: 17 files / 80 tests PASS
- `next build`: PASS。5画面、legacy dynamic route、canonical APIを生成し、削除済み `/api/osekkai/state` がmanifestにないことを確認
- Python compileall: PASS、unittest: 69 tests PASS
- Python contract validation: 16 schemas / 8 instances PASS
- demo runner: 12/12、最初 `do_not_push`、次 `suggest_solo_place`、Social Battery 20、2 Episode、`classification=demo` の6指標、未検証7指標
- fresh Cookieの実ブラウザ: 手動resetなしで12/12。外部HTTPSをabortし、通信は `127.0.0.1` のみ、page error 0件
- 5画面: 390x844と1440x900でhorizontal overflowなし。`/`、`/tomo`、`/staff` はlegacy chromeのまま表示
- live HTTP negative test: CSRF欠落403、foreign Origin 403、Content-Type 415、64 KiB超413、browser `userId` 400、不正Schema 400、非文字列body冪等key 400。すべて厳密error envelopeと `no-store`
- production smoke: `/`、`/tomo`、`/staff`、5画面が200。CookieはSecure/HttpOnly/SameSite=Strict、data modeはlive、demo resetは404

## 9. 既知の制約

- 会話理解は受入シナリオ中心の決定論的ルールで、自由会話全般を理解する LLM ではありません。
- Free Window、移動時間、参加、再訪はデモデータです。Opportunity もオフライン snapshot で、現在開催中の案内ではありません。
- 匿名 Cookie は本格アカウントではなく、複数端末同期や本人復旧はできません。
- 30日retentionは会話と推定根拠を対象とし、明示Profile設定、Episode、feedback、KPIは本人の全削除まで残ります。`memoryConsent=false` でも明示的な安全制御とservice-essentialな最小Episodeは保存します。
- JSONストアとプロセス間lockは永続diskを持つ単一ホスト向けです。rate limitとbridge permitはNode.js instance内だけで、全ユーザー合算disk上限もありません。公開本番では共有rate limit、OS/container disk quota、監視が必要です。
- ユーザー削除後もraw UUIDを含まないHMAC化lock fileは運用artifactとして残る場合があります。
- 実ユーザーの効果、医学的効果、行政効果は未検証です。
- 作業ディレクトリに `.git` がなく、branch、変更前 commit、backup 場所の記録を確認できません。そのため、完全な差分一覧と変更前状態への復元可否は未確認です。

## 10. `/` を `/osekkai` へ切り替えるか

現在は切り替えません。`/` は既存 Tomo-san/市民相談のトップを維持し、ヘッダーに `/osekkai` への入口だけを追加しています。受入後の redirect や製品トップ変更は、別の製品判断として残します。
