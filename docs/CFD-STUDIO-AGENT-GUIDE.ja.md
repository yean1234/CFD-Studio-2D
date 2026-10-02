# AIエージェント利用ガイド

- CFD Studio V1.0 · エージェントインターフェース v1.3

[한국어](CFD-STUDIO-AGENT-GUIDE.md) · [English](CFD-STUDIO-AGENT-GUIDE.en.md) · [日本語](CFD-STUDIO-AGENT-GUIDE.ja.md)

## 協働機能 v1.3

- 目的：OpenFOAM CFDのエージェント操作で繰り返し入力・取得を減らし、同じ画面でユーザーが確認できるよう支援
- **必要な状態の取得**：`observe({after})`・`inspect({query,limit})`・`waitForChange({after,timeoutMs})`を使用、変化のないConfig全体の繰り返し取得を避ける
- **Config変更確認**：`review.open`で変更前後と3Dをユーザーに確認してもらい、`review.status()`を取得、確認は保存・計算の許可ではない
- **担当と引継ぎ**：`claim({name,task})`のtokenをrunの`owner`に指定、`release({owner,summary})`で引継ぎ、次の担当は`handoff()`と実画面を照合
- 既存命令に`run(command,args,{owner,expectedContext:CFDAgent.observe().context,response:"compact"})`を指定
- 担当の有効時間は120秒、成功命令または`renew({owner})`で更新、他の担当は読み取りのみ
- ユーザー入力や選択変更後は再取得し、古い状態でユーザーの変更を上書きしない
- **ユーザーに操作権を返す**は担当解除と命令一時停止であり、ソルバー停止とは別
- 担当・引継ぎ・確認は現在ページのメモリー、再読込時にリセット、サーバーや他タブのロックではない
- 引継ぎは参考情報であり権限付与ではない、既に明示された同じ依頼範囲を繰り返し確認しない
- 作業別プロンプト：`recipe("observe"|"review"|"handoff","ja")`、または**作業ガイド → 作業プロンプトをコピー**
- [機能・命令エラー・参考文献](AGENT-COLLABORATION.md)

## Templateを基準にしたConfig作成

1. アンケートとソルバー選択からTemplateを生成
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
- 停止信号と待機手順を守り、ユーザーの再開操作を代行しない

## 結果の確認

- ViewerでCaseを1件選択し、**3D Virtual / Data Sheet**を切替
- Data Sheet左側：全体平均または指定座標の時系列、最大3つの物理量
- 右側：保存フレームの線上プロファイル、始点・終点・標本数を指定
- 線上の値は最寄りの保存セルに基づくため、空間・時間補間として説明しない
- JSONはConfig全体・空間定義全体・主要分類単位で入力、個々の属性にはJSONボタンなし
- Template作成だけでは実行アダプターは追加されないため、実際の実行接続状態を確認


## 開始手順

1. CFD Studioを起動し、使用するプロジェクトを選択
2. **環境設定 → LLMエージェント → エージェントガイド → 案内プロンプトをコピー**を選択
3. プロンプトと作業依頼をエージェントに渡し、ユーザーが見ているStudioのタブに接続
4. 画面の動作と最上部の**エージェント操作中**表示で進行状況を確認
5. 右上の**エージェント操作を停止**で一時停止し、**エージェント操作を再開**で続行

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

## 案内プロンプト

- 右上の**環境設定 → LLMエージェント → エージェントガイド**を開く
- **案内プロンプトをコピー**を選択し、エージェントとの会話に貼り付け
- コピーできない場合は**ガイドを表示**から本文を手動でコピー
- **Alt + Shift + A**でガイドパネルを開閉
- プロンプトには準備、コマンド、入力方法、実行結果の確認方法を記載
- 自動生成されるエージェント向けプロンプトは英語 · 画面のボタンは韓国語・英語・日本語に対応
- 報告はユーザーの言語で行い、ユーザー定義の名前とConfig値は翻訳しないよう指示

## 画面表示

| 表示・ボタン | 機能 |
| --- | --- |
| 青い枠 | 操作対象のボタンや入力欄を強調 |
| 最上部中央の**エージェント操作中** | 操作中に点滅 · 動きを抑える設定では固定表示 |
| 右上の**エージェント操作を停止** | 以降のコマンドを遮断し、一時停止信号を通知 |
| 同じ位置の**エージェント操作を再開** | 再開信号を通知 |
| 右下のパネル | 現在のコマンドと最近の送信記録を表示 |
| **コマンドを一時停止** / **コマンドを許可** | コマンド受付を停止・再開 |
| **×** | ガイドパネルのみ非表示 · コマンドは停止しない |

- 実際のプロジェクト、Case、Config、Viewerの画面に操作を反映
- 一時停止しても、送信済みの操作や実行中のCFD計算は継続
- ユーザーが選択や入力を変更した場合、エージェントは画面を再確認してから続行
- 以下の画像は韓国語表示の例 · ボタンの配置は各言語で共通

![エージェント操作表示](assets/agent-controls/banner.png)

![エージェントガイド](assets/agent-controls/guide.png)

## コマンド

- 接続中のタブでJavaScriptを実行する機能から`window.CFDAgent`を使用
- Studioのソース解析やプロジェクトファイルの直接編集をせずに画面を操作
- `CFDAgent.describe()`: インターフェースのバージョン、コマンド一覧、プロンプト
- `CFDAgent.state()`: 現在のプロジェクト、Case、キュー、画面、入力値、ボタン、通知、ログ
- `CFDAgent.prompt()`: コピー用プロンプト
- `CFDAgent.history()`: 最大100件のコマンド記録
- `CFDAgent.waitForResume({timeoutMs:30000})`: ユーザーの再開操作を待機 · 1回につき最大60秒
- `CFDAgent.finish()`: 操作表示を終了 · ユーザーによる一時停止状態は維持
- `await CFDAgent.run(command, args)`: 画面操作
- ガイドパネルの**コマンド入力 → コマンド実行**からJSONコマンドも実行可能

```javascript
// 現在の画面と実在するプロジェクトIDを取得
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
- ガイドパネルに入力するJSONの例

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
| `PAUSED` | ユーザーによる再開まで待機 |
| `STALE_TARGET` / `CONTROL_NOT_VISIBLE` | 画面を読み直し、現在の対象を選択 |
| `CONTROL_DISABLED` | 画面に示された必要条件を確認 |
| `INVALID_INPUT` / `INPUT_INVALID` | 入力形式または範囲を修正 |

## 一時停止と再開

- 停止時に`state().paused`が`true`となり、`cfd-agent-pause`イベントが発生
- 再開時に`cfd-agent-resume`イベントが発生 · 信号にはセッション、連番、時刻を含む
- 毎回のコマンド送信前に状態を確認 · 停止信号や`PAUSED`応答を受けたら待機
- エージェントのブラウザー制御側で待機処理を実装

```javascript
while (CFDAgent.state().paused) {
  const signal = await CFDAgent.waitForResume({ timeoutMs: 30000 });
  if (signal.status === 'resumed') break;
}
// 次の操作を決める前に、画面とユーザーによる変更を再確認
const current = CFDAgent.state();
```

- 依頼された作業が完了したら`CFDAgent.finish()`を呼び出す
- 応答がない場合も**エージェント操作を停止**で追加コマンドを遮断可能
- Studioから外部LLMプロセス自体を強制停止することはできないため、接続ツール側で信号に従って待機
- 送信済みの操作とCFD計算は継続 · CFDの停止にはCaseの計算中断機能を使用
- 別タブ、再読み込み、内部UI関数の呼び出し、自動再開によって停止状態を回避しない

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
