# AIエージェント利用ガイド

- CFD Studio V1.0 · エージェントインターフェース v1.4

[한국어](CFD-STUDIO-AGENT-GUIDE.md) · [English](CFD-STUDIO-AGENT-GUIDE.en.md) · [日本語](CFD-STUDIO-AGENT-GUIDE.ja.md)

## 作業進行表示

- 資料確認・コード修正・テストも状態送信が必要 · ファイル変更だけでは画面は更新されない
- リポジトリーのルートで `cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_progress.py` を使用
- `output` がなければ作成 · 新しい `--session-file output\agent-session.json` を指定 · 既存ファイルは上書きしない
- 開始前：`start --session-file output\agent-session.json --mode development --stage review --detail "入力を確認" --wait-visible`
- 各段階の前：`update --session-file output\agent-session.json --stage test --detail "関連テストを実行" --wait-visible`
- 短い操作の間に `status` を確認 · 長い作業では60秒以内に確認・更新
- 終了：`finish --session-file output\agent-session.json --stage completed --detail "テスト完了・CFD未実行"`
- モード：開発は `development`、Studio画面操作は `operation`
- 段階：`review`, `draft`, `debug`, `test`, `ui`, `waiting`, `blocked` · 終了は `completed` または `failed`
- 説明はユーザーの言語で簡潔に記述 · 認証情報やConfig全体は送信しない
- 終了コード `3` または `PAUSED`：編集・操作を停止し、状態だけ確認して新しいユーザー指示を待機
- コード `2`：エラー確認 · コード `4`：表示受信未確認 · 表示成功と報告しない
- `displayed: true` は表示中のStudioタブで描画された確認 · 対象タブへの接続・ユーザー確認・計算許可ではない
- 120秒更新がなければ接続切断表示 · HTTP失敗は作業状態の接続切断 · 待機・進行不可・終了状態は点滅しない
- 状態・直近20件・一時停止はサーバーメモリーに保持 · ページ再読込後も取得可能 · サーバー再起動で初期化
- 外部LLM・実行済み命令・ソルバーを強制停止する機能ではない · エージェントが短い作業の間に確認
- 状態専用の経路 · Config入力・保存・計算は引き続き現在の画面の公開命令を使用
- 更新は起動中のサーバーやタブへ自動適用されない · 未保存入力と実行中計算を確認してからStudio再起動・ページ再読込
- [状態エラーコード](AGENT-PROGRESS.md)

## 接続確認と復旧

1. 画面操作ツールが起動するか確認
2. StudioのHTTPとエージェントスクリプトの応答を確認
3. ユーザーが見ているタブで`CFDAgent.describe()`と`CFDAgent.observe()`を取得
4. session・プロジェクト・Caseを実画面と照合してから操作

| 確認対象 | 根拠 | 証明しないもの |
| --- | --- | --- |
| 操作ツール | 呼び出し成功 | Studioへの接続 |
| サーバーとスクリプト | `agent_diagnostics.py` | 現在タブへの接続・ユーザー確認 |
| 現在のタブ | タブ内のdescribe・observeと画面照合 | 保存・計算の許可 |
| 下書き反映 | JSON再取得・通知・3D確認 | Case保存・CFD完了 |

- 診断の`stages`：automation_host / studio_http / agent_scripts / current_tab
- HTTP正常でも`current_tab: not_checked`、終了コード0もタブ接続の証明ではない
- ポートは`CFD_STUDIO_PORT`、未指定時は`studio_config.json`を使用、Windows実行環境で診断
- `APP-A001`：Studioへ接続する前の外部ツールの作業パスエラー、ツールの復旧手順を試して同じ失敗の反復を停止
- ローカル環境の変更は復旧候補であり、解決の保証ではない
- `APP-N001`：サーバー接続失敗、停止中サーバーの起動と稼働中サーバーの再起動を区別
- 外部ツールの問題を直す目的で正常なサーバー・ブラウザー・ソルバーを終了しない
- 質問UIが表示されない場合は通常の会話に必要な質問を再掲、無応答は確認・承認ではない

### 操作と開発の区別

- 通常操作は現在タブの公開CFDAgent命令と画面操作を使用
- デバッグを依頼された場合は対象段階を停止し、エラーと影響を記録、関連コードを修正・検査した後に再接続・再取得
- プロジェクト・未保存入力・計算・Raw・結果を維持し、コード検査をCFD実行と報告しない
- サーバー変更後も未保存入力を確認せずにタブを再読込しない
- 外部の障害は残る原因と必要な対応を明示し、無関係な機能変更を続けない

### 下書きの出典と状態

- 編集画面からの出力、サーバーTemplateの写し、リポジトリの参考ファイルを区別
- 別ファイルの下書きは画面反映・ユーザー確認・Case保存ではない
- 復旧後は編集画面のJSONを再取得し、ユーザーの変更と照合して必要な値だけ反映
- 文献値・単位換算・Template既定値・提案仮定・非公開値を区別
- ソルバー導入、実行アダプター、形状、結果読取、輸送の対応をそれぞれ確認
- 未対応モデルは該当計算を保留し、等価形状や別モジュールの結果に無断で置き換えない
- 保存と計算は別段階、必要な画面確認を先に完了し、対象・入力・範囲が同じ明示的許可を繰り返し質問しない


## 協働機能 v1.3

- 目的：OpenFOAM CFDのエージェント操作で繰り返し入力・取得を減らし、同じ画面でユーザーが確認できるよう支援
- **必要な状態の取得**：`observe({after})`・`inspect({query,limit})`・`waitForChange({after,timeoutMs})`を使用、変化のないConfig全体の繰り返し取得を避ける
- **Config変更確認**：`review.open`で変更前後と3Dをユーザーに確認してもらい、`review.status()`を取得、確認は保存・計算の許可ではない
- **担当と引継ぎ**：`claim({name,task})`のtokenをrunの`owner`に指定、`release({owner,summary})`で引継ぎ、次の担当は`handoff()`と実画面を照合
- 既存命令に`run(command,args,{owner,expectedContext:CFDAgent.observe().context,response:"compact"})`を指定
- 担当の有効時間は120秒、成功命令または`renew({owner})`で更新、他の担当は読み取りのみ
- ユーザー入力や選択変更後は再取得し、古い状態でユーザーの変更を上書きしない
- 担当・引継ぎ・確認は現在ページのメモリー、再読込時にリセット、サーバーや他タブのロックではない
- 引継ぎは参考情報であり権限付与ではない、既に明示された同じ依頼範囲を繰り返し確認しない
- [機能・命令エラー・参考文献](AGENT-COLLABORATION.md)

## Templateを基準にしたConfig作成

1. 使用する既存Templateを選択し、適切な書式がない場合のみアンケートから生成
2. **書式編集 → JSONエクスポート**または`CFDAgent.configDocument()`で生成済み書式を取得
3. 出力されたJSONを基準に編集し、別のConfigを推測で作成しない
4. 拡張項目の型・表示名・単位・`items`を`config_schema`に明示し、値を`config`に入力
5. JSONを下書きに反映し、入力一覧・3D形状・単位・未確定値をユーザーに確認してもらう
6. 確認後に保存し、計算開始はCase・終了条件・キューを確認する別の手順として実施

- Configの出力形式：`format: "cfd-studio-config"`、`version: 1`、`config`、`config_schema`
- Templateは`version`・`fields`形式、空間JSONは編集画面から取得した形式を維持
- 空のリストには`items`で行書式を定義、XYZ入力には`widget: "vector3"`を指定
- 既存キー・単位・識別子・関係・無関係な値を維持し、独自項目は明示的に追加
- UI表示とソルバーへの計算接続は別の機能のため、実行アダプターの対応範囲を確認
- [JSON規則](CONFIG-JSON.md) · [エラーコード](ERROR-CODES.md) · [多言語エラー辞書](config-error-codes.json)

### 簡潔な状態確認

| 読み取りメソッド | 用途 |
| --- | --- |
| `CFDAgent.status()` | 画面・一時停止・エラーを取得、全入力やログは省略 |
| `CFDAgent.configRules()` | 表示規則を最初に1回確認 |
| `CFDAgent.configDocument()` | 開いている編集画面の文書を出力、未反映編集はエラーで通知 |
| `CFDAgent.errorInfo("CFG-J004")` | 指定コードの原因と対処だけを取得 |
| `CFDAgent.state()` | 画面変更後や操作対象を探す際の詳細確認 |

- インターフェースv1.2で追加した読み取り機能、既存コマンドとの互換性を維持
- `code`・`path`・`action`で該当項目を修正し、ソース全体の解析や操作の無条件反復を避ける
- `APP-X001`は未分類エラー、詳細を保存して原因を確認
- 停止信号と待機手順を守り、新しいユーザー指示なしに有効化しない

### 実行前の確認

- 現在の作業が進行CLIセッションを所有している場合、`CFDAgent.activate()` を重複呼び出ししない · 他の担当のセッションは使わない
- `CFDAgent.configDocument()` は `{document: ...}` またはエラーを返す · `document` を確認して使用
- Templateの `document.fields` は書式、プロジェクト・Caseの `document.config` は入力値 · 相互に置換しない
- プリセット未選択でもTemplateに値が残る場合あり · 文献値・既定値・未確定値を区別
- 空間JSONの取得成功と3D生成成功は別 · プレビュー警告・境界・多孔質領域を確認
- ソルバーのインストール確認だけで形状生成・格子取込・輸送・実行接続を判定しない
- 未対応形状では計算段階を停止 · 下書きとエラーコードを保持し、等価モデルへ勝手に変更しない
- 編集中の下書き・プロジェクト保存・Case保存・格子検査・計算完了を別々に記録

## 結果の確認

- ViewerでCaseを1件選択し、**3D Virtual / Data Sheet**を切替
- Data Sheet左側：全体平均または指定座標の時系列、最大3つの物理量
- 右側：保存フレームの線上プロファイル、始点・終点・標本数を指定
- 線上の値は最寄りの保存セルに基づくため、空間・時間補間として説明しない
- JSONはConfig全体・空間定義全体・主要分類単位で入力、個々の属性にはJSONボタンなし
- Template作成だけでは実行アダプターは追加されないため、実際の実行接続状態を確認


## 開始手順

1. CFD Studioを起動し、使用するプロジェクトを選択
2. 外部エージェントに本ガイドと作業内容を渡す
3. プロンプトと作業依頼をエージェントに渡し、ユーザーが見ているStudioのタブに接続
4. 画面の動作と最上部の**エージェント操作中**表示で進行状況を確認
5. **エージェント操作を停止**でUIを非表示にして停止通知 · 続行する作業はエージェントとの会話で新しく指示

- プロンプトを渡すだけではブラウザーに接続されないため、使用するエージェントツールの手順に従って接続
- コマンド名とJSONキーは表示言語にかかわらず共通

## JSON入力と段階別の確認

- エージェントインターフェース **v1.1**からConfig・空間形状の専用JSONコマンドに対応
- 個別の入力欄を埋める代わりにJSONを一括入力 · 同じ画面でConfigと3Dプレビューを確認
- 現在のタブの編集画面と入力検査を使用 · ファイルの直接変更や別サーバーへの接続は不要

| 段階 | エージェントの作業 | ユーザーの確認 |
| --- | --- | --- |
| 1 | プロジェクト・Case・CFD Template・ソルバー・作業目的を確認 | 対象と解析目的を確認 |
| 2 | 実際のTemplate書式と空間JSONを取得 | 不足する寸法・物性・条件を提供 |
| 3 | 空間JSONを作成し下書きに反映 | 3D形状・領域名・単位・固体/液体/気体の割り当てを確認 |
| 4 | 書式に合わせて残りのConfig JSONを作成し下書きに反映 | 各設定の意味・値・単位・根拠・未確定値を確認 |
| 5 | 変更内容を要約して保存可否を質問 | 確認の返答後にConfig・Caseを最終保存 |
| 6 | 終了条件・保存間隔・キュー全体の順序を説明 | 確認の返答後にキュー追加・計算開始 |
| 7 | ログ・Case状態・結果を確認 | 完了・失敗・検証状態を報告 |

- 各段階の結果を説明してから次へ進む · Config作成の依頼だけで計算を開始しない
- ユーザー確認はエージェントの案内規則 · プログラムが承認応答を強制検査する機能ではない
- **JSON保存**は下書きへの反映 · Config最終保存・Case保存・キュー開始とは別の操作
- 実行済みの読み取り専用Configは**このConfigで新規Case**からコピーを編集

### 専用コマンド

| コマンド | 機能 | 引数 |
| --- | --- | --- |
| `config.json.open` | Configまたは空間全体のJSONを開く | `scope: "config"`または`"geometry"` |
| `config.json.fill` | JSON編集バッファーに一括入力 | `value`: JSON文字列 · 最大1 MB |
| `config.json.apply` | 既存の検査を行い、下書きに反映 | なし |

- `CFDAgent.state().json`で`scope`・`title`・`value`・`readonly`・`dirty`を取得 · JSON画面が閉じている場合は`null`
- `config.json.open`の前に対象のConfig編集画面を開く · プロジェクトやCaseの自動選択は行わない
- 取得したJSONをコピーし、必要な値のみ変更 · 名前・型・単位・ID・関連付け・メタデータを維持
- `version`・`fields`を持つTemplate書式、Config値オブジェクト、空間全体の文書は異なる形式 · 読み取った形式のまま編集
- 書式や必須情報が不足する場合はユーザーに質問 · 欠落値を推測で確定しない
- 空間JSONに含まれない物性や計算条件はConfig JSONで入力
- `apply`の`dispatched`だけで反映成功と判断しない · `notices`、JSON再取得、3Dプレビューで確認
- 文法・型のエラーは同じ下書きで修正 · 読み取り専用と一時停止の制約を維持
- `apply`は最終保存やCFD実行を行わない

### JSON入力例

- 開いているConfig編集画面から空間全体の文書を取得

```javascript
await CFDAgent.run('config.json.open', { scope: 'geometry' });
const current = CFDAgent.state().json;
if (!current || current.readonly) throw new Error('Editable JSON required');
const document = JSON.parse(current.value);
// 実際の書式とユーザーが提供した寸法・条件に合わせてdocumentを編集
```

- 編集した文書を渡す関数 · 反映後にユーザーへ画面確認を依頼

```javascript
async function applyDraft(document) {
  const fill = await CFDAgent.run('config.json.fill', {
    value: JSON.stringify(document, null, 2)
  });
  if (fill.status !== 'dispatched') return fill;
  return await CFDAgent.run('config.json.apply');
}
// 返されたstate.jsonとstate.noticesを確認
// ユーザー確認前に最終保存・queue.add・queue.startを実行しない
```

- 一般のConfigでは`scope: "config"`を使い、新たに読み取った文書で同じ手順を実施
- ユーザーへの確認事項: 対象形状、寸法と単位、材料と物性、初期・境界条件、時間刻み、終了条件、出力間隔、変更点と仮定

## 準備

- `cfd_studio/실행.bat`でStudioを起動
- 対応環境はWindows 10/11 x64 · macOSは非対応
- ブラウザー操作ツールを備えたLLMエージェントを使用
- **ユーザーが見ているCFD Studioのタブ**に接続
- 別のブラウザーウィンドウで実行したコマンドは、そのウィンドウにのみ反映
- LLMツールの導入、アカウントへのログイン、ブラウザー接続はエージェントツール側で実施
- StudioはHTTP・MCPコマンドサーバーやリモートデバッグポートを公開しない
- CFD実行前にソルバーのインストール、Studioからの実行対応、Config、終了条件、キューを確認

## エージェントの有効化

- 内蔵AIの開始ボタンはなし · 外部エージェントが `CFDAgent.prompt()` を読み、現在のStudioタブに接続
- エージェント専用コマンド: `await CFDAgent.activate({name:"Agent", task:"作業内容"})`
- 開発作業は進行CLIの `start` を使用 · 有効なセッションがあれば既存セッションを更新
- 人向けの開始・再開・命令入力ボタンやキーボード切替は提供しない
- 有効な作業中のみ **外部エージェント操作中** と **エージェント操作を停止** を表示
- 停止すると関連UIを即座に非表示にし、`cfd-agent-pause` と `PAUSED` で次の操作を遮断
- 完了時も非表示 · 停止後は新しいユーザー指示が必要
- ユーザーが入力・選択を変更したら再確認

## コマンド

- 接続中のタブでJavaScriptを実行する機能から`window.CFDAgent`を使用
- Studioのソース解析やプロジェクトファイルの直接編集をせずに画面を操作
- `CFDAgent.describe()`: インターフェースのバージョン、コマンド一覧、プロンプト
- `CFDAgent.state()`: 現在のプロジェクト、Case、キュー、画面、入力値、ボタン、通知、ログ
- `CFDAgent.prompt()`: コピー用プロンプト
- `CFDAgent.history()`: 最大100件のコマンド記録
- `CFDAgent.finish()`: 操作表示を終了 · ユーザーによる一時停止状態は維持
- `await CFDAgent.run(command, args)`: 画面操作

```javascript
// 現在の画面と実在するプロジェクトIDを取得
await CFDAgent.activate({name: 'Agent', task: 'Review project'});
const state = CFDAgent.state();

// 例: 先頭のプロジェクトが依頼対象であることを確認して選択
const project = state.workspace?.projects?.[0];
if (!project) throw new Error('No project available');
await CFDAgent.run('project.select', { id: project.id });

// 選択中のCaseのConfigを開き、現在の入力欄を確認
await CFDAgent.run('config.open');
CFDAgent.state().controls;
```

| コマンド | 動作 | 引数 |
| --- | --- | --- |
| `cfd.open` | CFD画面を開く | なし |
| `viewer.open` | 選択CaseのViewerを開く、または結果を準備 | なし |
| `project.select` | プロジェクトを選択 | `id` |
| `project.find` / `project.new` | プロジェクト検索／新規作成を開く | なし · CFD画面で使用 |
| `project.manage` | プロジェクト管理を開く | なし |
| `case.select` | 現在のプロジェクトのCaseを選択 | `id` |
| `case.new` | 新規CaseのConfigを開く | なし |
| `config.open` | Configを編集・閲覧 | なし |
| `template.new` | 新規CFD Templateを開く | なし |
| `queue.add` | 選択中の下書きをキューに追加 | なし |
| `queue.start` | 表示中のキュー全体を開始・再開 | なし |
| `queue.pause` | 次の計算から一時停止 | なし |
| `case.stop` | 選択した実行中Caseを中断 | なし |
| `case.recovery` | 失敗理由と復旧画面を開く | なし |
| `queue.skip` | キュー内の失敗Caseをスキップ | なし |
| `result.open` | 結果の生成・更新・開くボタンを操作 | なし |
| `result.refresh` | Viewerの結果を再読み込み | なし |
| `result.csv` | 選択Caseの全CSVデータを出力 | なし |
| `viewer.mode` | Viewerモードを選択 | `mode: "3d"`または`"data"` |
| `settings.open` | 環境設定を開く | なし |
| `ui.click` | ボタンや項目の開閉を操作 | `target` |
| `ui.fill` | 入力欄に文字列を入力 | `target`, `value` |
| `ui.select` | 選択リストを変更 | `target`, `value` |
| `ui.check` | チェックボックス・ラジオボタンを選択 | `target`, `checked` |

## 値の入力

- `state().controls`で`target`、`label`、`value`、`options`、`disabled`、`readonly`を確認
- ダイアログや項目を切り替えたら入力欄の一覧を再取得
- 置き換えられた入力欄の`target`は再利用しない
- 数値も文字列で渡す例: `value: "0.01"`
- 選択リストでは表示名ではなく`options[].value`を使用
- 不正な数値形式は拒否 · 範囲外エラーは入力欄で確認して修正
- ファイル入力にはブラウザー操作ツールのアップロード機能を使用
- 実行済みConfigは読み取り専用 · **このConfigで新規Case**でコピーを編集
- 入力コマンドだけでは保存されないため、画面の**保存**ボタンを使用
- 形状、物性値、境界条件を根拠なく設定しない

```javascript
const field = CFDAgent.state().controls.find(item => item.label === 'プロジェクト名');
if (!field) throw new Error('Read the current controls first');
await CFDAgent.run('ui.fill', { target: field.target, value: '熱伝達比較' });
```

- ラベルは表示言語により異なるため、実際の一覧から選択
- 外部エージェント用の命令JSON例

```json
{"command":"config.open","args":{}}
```

## 結果の確認

- `status: "dispatched"`は画面への操作送信を示す
- **保存、出力、CFD計算の成功や完了を示すものではない**
- 非同期処理は`state()`の通知、キュー、Case状態、ログで確認
- エラー内容を確認してから続行 · タイムアウトした操作を自動再送しない
- 計算の開始、再試行、中断はユーザーの依頼範囲で実施
- キュー開始は他のプロジェクトのCaseにも影響する可能性があるため、全体の順序を確認
- 可視化準備率、数値検査、計算完了、実験検証は区別して報告

| 状態・エラー | 対応 |
| --- | --- |
| `rejected` | 返された`error`を確認 |
| `BUSY` | 現在の操作を確認し、順番にコマンドを送信 |
| `PAUSED` | 新しいユーザー指示まで待機 |
| `STALE_TARGET` / `CONTROL_NOT_VISIBLE` | 画面を読み直し、現在の対象を選択 |
| `CONTROL_DISABLED` | 画面に示された必要条件を確認 |
| `INVALID_INPUT` / `INPUT_INVALID` | 入力形式または範囲を修正 |

## 停止後の待機

- 停止時は `state().paused` が真となり `cfd-agent-pause` を通知
- 編集・命令を止め、新しい明示的なユーザー指示を待機 · 自動有効化は禁止
- 新しい指示の後にのみ `CFDAgent.state().progress.state.stop_revision` を読み、専用コマンドを使用
- `userRequest` は実際の新しい指示 · サーバーは会話の真偽を検証できないためエージェントが規則を守る

```javascript
await CFDAgent.activate({name: 'Agent', task: taskSummary,
  afterStop: stopRevision, userRequest: actualNewUserInstruction});
```

- CLI: `activate --session-file output\new-agent-session.json --after-stop N --user-request "実際の新しい指示" --stage review --detail "新しい作業" --wait-visible`
- `N` は現在の `stop_revision` · 新しいセッションファイルを使用 · 以前の担当トークンは無効化
- ブラウザー所有セッションは `await CFDAgent.finish()`、CLI所有セッションは CLI `finish` で終了
- 再読み込みでは停止を解除しない · 回避目的のタブ・サーバー再起動は禁止
- 外部LLM・実行中のシェル命令・CFDを強制終了する機能ではない · 各作業の前に信号を確認

## 対応範囲

- 同じタブの既存ボタンと入力イベントを使用 · 入力検査、保存、スナップショットの規則も適用
- コマンド処理中の別コマンドは拒否 · 自動再送なし
- 状態取得にはConfig値を含むため、接続したエージェントに渡す情報を確認
- 操作記録にはコマンド、対象ID、送信状態を記録 · 入力値は記録しない
- 記録はタブのメモリー内に保持し、再読み込みで初期化
- 再読み込みでセッションIDが変わるため、以前の入力欄IDは再利用しない
- JavaScript実行機能がない場合は、画面操作ツールで同じボタンを操作
- ブラウザー接続、ファイル送信、OSのフォルダー選択、権限は使用するブラウザーとエージェントツールの対応範囲に従う
- `CFDAgent`が見つからない場合は未保存の編集を保全してから再読み込み · Studio再起動は待機中のみ実施し、実行中のソルバーやユーザーのブラウザーを終了しない

## 接続診断

- `agent_diagnostics.py`でStudio HTTPとエージェントホストの作業パスエラーを区別
- HTTP成功はユーザータブへの接続完了を意味しない · ブラウザーや計算を再起動しない
- `APP-A001`: ホストの作業パスエラー · `APP-A002`: ポート/スクリプト · `APP-N001`: HTTP接続失敗
- [診断コマンドとサイロ実行の制限](silo-agent-debug-20261003.md)

```bat
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_diagnostics.py
```

- 再起動操作では既存のStudioサーバーを保持してそのアドレスを開く · 別サービスのポート使用時はAPP-A002 · ポートの自動変更やプロセスの強制終了なし

## 形状ごとの細分化

- 実際のTemplate JSONを先に出力。既存の局所格子リストに `target_path` と `cell_size` を設定し、参照と直接座標を混在させない。JSONの配列を並べ替えた場合は参照パスも更新。計算前に細分化範囲と予想負荷を提示。形状プレビューは格子検証ではありません。
- [Mesh refinement](MESH-REFINEMENT.md)
