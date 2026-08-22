# Repository instructions

このワークスペースのActive productは、東京都の孤独課題に取り組む「おっせかいおばさん」だけです。

## Product mission

- 利用者の好みを理解したうえで、いつもの選択から少しだけ外れた、本人にはまりそうな実在Eventを1件提案する
- 提案対象は、会話、共同活動、再参加、Community形成など、孤独の緩和につながる接点が確認できるEventに限定する
- OpenClawが最新情報を継続取得し、Calendarの空きとGoogle Routesの実移動時間を合わせて判断する
- PUSHを待たず、利用者自身も現在地または指定地域から交流Eventを地図で探せるようにする
- 図書館、公園、大型展示など、そこに行くだけでは交流根拠がない場所を孤独解消Eventとして扱わない

これは医療診断や治療を行う製品ではありません。緊急性のある入力はEvent推薦から切り離し、適切な相談先への案内を優先してください。

## Source of truth

作業前に、必要な範囲を次の順で確認してください。

1. ユーザーの最新の明示指示
2. `Plan2.md`の「13.1 Task運用ルール」と実行順Task Queue
3. `Tokyo_Social_Calibration.pdf`の課題背景、価値仮説、審査説明
4. `PLAN.md`のP0実装履歴、契約、安全・Privacy要件
5. `README.md`の現状、構成、起動・検証方法

`docs/brain/`は現在存在しないため、参照前提にしないでください。PDFや計画書は設計判断の材料であり、不変の仕様ではありません。実データ、Provider制約、テスト結果、ユーザーの最新指示と矛盾した場合は、古い記述へ実装を無理に合わせず、根拠を示して`Plan2.md`を更新してください。

## Current state and claims

- 現在実装済みなのは、外部接続を使わず再現できるP0ローカルデモです
- Live Provider同期、Google Calendar OAuth / FreeBusy、Google Routes、Google MapsのEvent Mapは`Plan2.md`の未完了Taskです
- 未実装機能をREADME、UI、審査説明で実装済みと表現しないでください
- synthetic fixture、過去snapshot、Live取得値、AI推定、主催者確認値を必ず区別してください
- PV・Demo動画の制作はユーザー側で進行しており、実装Taskや完了Gateに含めません。ただし、製品UIと動画の世界観・主張は一致させてください

## Event and data rules

- 鮮度、開催日時、募集状態、Source URLを検証できないEventをLive PUSHしない
- canceled、sold out、expired、stale、重複Eventを候補から除外する
- `一人参加OK`、`次回あり`、定員、交流形式などを根拠なしで生成しない
- Connection Evidenceを保存し、継続性、共同活動、少人数会話、再参加導線を評価する
- 単なる人気順や近さ順ではなく、本人の好み、隣接ジャンル、Calendar、移動、料金、過去Feedbackを同時に扱う
- Judge向け主経路は正の1件提案とする。候補がない場合に架空Eventを生成しない
- 現在地は明示操作時だけ取得し、Profileやlogへ正確な座標を永続保存しない。拒否時は駅名・地域名検索を使う
- CalendarはFreeBusyだけを使用し、予定タイトル、説明、場所、参加者を取得・保存しない

## Implementation boundaries

- UI: `frontend/app/osekkai`, `frontend/components/osekkai`, `frontend/app/osekkai/_components`
- API: `frontend/app/api/osekkai`
- Generated client / validator: `frontend/lib/osekkai`
- Server adapter: `frontend/lib/server/osekkai-*`
- Python owner: `agents-OpenClaw/scripts/osekkai_*`
- Policy: `agents-OpenClaw/config/osekkai_policy.json`
- Contract SSOT: `contracts/osekkai`
- Tests: `agents-OpenClaw/tests/test_osekkai_*.py`とfrontendのVitest

Provider取得、正規化、Connection判定、Profile、Policy、Calendar、Routes、SchedulerのownerはPythonです。Next.jsに第二のProvider実装や判断ロジックを作らず、生成Contractを介して接続してください。

## Task workflow

1. `Plan2.md`で依存Taskが完了している次の未完了Taskを選ぶ
2. 対象ファイルと既存テストを確認してから変更する
3. Contract変更時はJSON Schemaを先に更新し、PythonとTypeScriptのvalidator・型・testを追従させる
4. 正常系だけでなく、Credential不足、timeout、quota、stale、malformed response、位置情報拒否も検証する
5. 完了条件と検証コマンドを満たした後だけTaskを`[x]`にし、変更ファイル、結果、残課題を記録する
6. 外部Credentialだけが不足している場合は該当Providerをblockedとして記録し、独立して進められるTaskを継続する

## Validation commands

Pythonは`agents-OpenClaw`から実行します。

```powershell
Set-Location agents-OpenClaw
python -m compileall scripts tests
python -m unittest discover -s tests -p "test_osekkai_*.py" -v
python scripts/osekkai_contracts.py --validate-all
```

Frontendは`frontend`から実行します。

```powershell
Set-Location frontend
npm.cmd run generate:contracts
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

## Legacy boundary

`archive/tomo-san/`は復旧用の退避領域です。ユーザーが明示的にTomo-sanの復元を依頼しない限り、検索、import、コピー、実行、編集をしないでください。

`agents-OpenClaw/scripts`に残る非`osekkai_`ファイルの一部は参考資産です。Active runtimeから直接呼ばず、現在のTaskに必要な考え方だけをOsekkai専用moduleへ移植してください。
