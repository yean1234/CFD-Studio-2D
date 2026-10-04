# 倉庫の対称条件とメッシュ計画

[한국어](WAREHOUSE-SYMMETRY.md) · [English](WAREHOUSE-SYMMETRY.en.md) · [日本語](WAREHOUSE-SYMMETRY.ja.md)

- 接続済み整列積載モデルのConfig → **メッシュ → 計算領域**で全領域またはY中央面の片側半分を選択
- **最大セル辺長 (m)**に正数を入力 · 3cmは`0.03` · 空欄なら既存の基本間隔と細分化を維持
- **メッシュ計画を確認**でセル数・予定最大辺長・基本配列サイズ・セル数上限を確認 · メッシュ生成や計算開始ではない
- 積載・初期濃度・物性・熱境界が対称な接続済みモデルのみ対応 · 非対称流動を除外する仮定
- セル数上限を超えると生成を停止し、間隔を自動変更しない · 配列サイズはソルバー全体のメモリではない
- Viewerは計算した半分のみ表示し、除外領域の座標照会を拒否 · Configの形状編集は元の全空間を維持
- 局所細分化は既存ブロックの軸方向にも伝播 · 自動適応格子と独立した細密・粗密3D領域の接合は未対応

## 対応機能

| 機能 | 状態 | 範囲 |
| --- | --- | --- |
| 速度・温度・希薄濃度の連成 | 接続済み | 既存の仮定モデル、外部漏洩なし |
| 多孔質穀物積載 | 接続済み | 均質化した積載外形、個々の袋膜は未解像 |
| 全領域とY対称半領域 | 接続済み | 整列積載生成器、Y中央面の両側から選択 |
| 最大辺長と事前計画 | 接続済み | セル配列生成前に算定、明示的なセル数上限 |
| 形状別局所細分化 | 接続済み | 軸方向に投影し周辺区間にも伝播 |
| 局所メッシュ定義とフォルダー | 接続済み | 物理壁なし、フォルダーは表示整理のみ |
| 除外側の結果ミラー表示 | 未実装 | 計算領域のみ表示・照会 |
| 自動適応格子と独立3D細分化接合 | 未実装 | 静的局所細分化とは別 |
| 任意軸・任意CADの対称条件 | 未実装 | ソルバー導入だけでは接続されない |
| 実験検証・7日間全体・定常状態の保証 | 未完了 | 実行・収支検査とは別 |

## 対称条件

- 半分を計算し、中央面にOpenFOAM `symmetryPlane`を適用 · 壁面として生成しない
- 積載外形の鏡映対応と初期Gaussian濃度のY中心を検査 · 一様物性・初期温度・初期静止流と共通の外皮熱境界は現在の実行器の条件
- 形状の対称性だけでは流動の対称性を保証できない · 非対称な熱源・流入口・開口や対称性の破れには全領域の評価が必要
- 体積と総質量は計算した半分の値 · 全領域と比較する際は総量と単位体積量を区別
- 全体Configを保持し、結果の`computational_domain.bounds_m`と切り取った積載外形に実計算範囲を記録
- エラー: `MESH-S001`非対応モデル/領域、`MESH-S002`非対称積載、`MESH-S003`非対称初期濃度、`MESH-S004`初期場の対称境界欠落

## 格子規模

- 提供例の公称寸法78×25m、軒高7.2m、屋根高さ3.5m
- 最大辺長3cm: 全体808,156,608セル、半分404,078,304セル
- 半領域の速度3成分・温度・濃度のfloat64配列だけで16.16GB · 圧力・乱流・格子・行列・一時配列・出力は除外
- 大規模3cm格子は生成・実行していない · 計算資源の適合性確認が必要
- 30mと30cmは異なる入力 · 幅25mの半分を30mセルで解像できない
- `maximum_cell_edge_m`は上限 · 大きい値でも既存の形状境界や基本細分化は除去しない
- 局所範囲は適合するブロック境界を保つため軸方向にも伝播 · 小さな観察領域でもセル数増加を事前確認

## 検証

- OpenFOAM v2312で全体1,860セル、各Y半領域930セルの`blockMesh`・`checkMesh`・連成ソルバーを実行
- 1秒の開発試験、各3保存フレーム、実行検査通過
- 共通位置と保存時刻での最大差: 速度2.67×10⁻⁷m/s未満、温度3.36×10⁻⁸K未満、濃度4.50×10⁻¹⁵kg/m³未満
- 質量収支相対誤差8.68×10⁻¹⁵未満 · 格子/時間収束、実験検証、燻蒸効果の証明ではない
- 計画照会はNumPyなしのWindows標準Pythonで実行 · 計算は既存WSL数値環境を使用
- 入力・体積・初期質量・上限検査: `python -m unittest discover -s tests -p "test_warehouse_symmetry.py"`

## JSON

```json
{"porous_mesh": {"domain_mode": "symmetry_y_min", "maximum_cell_edge_m": 0.03}}
```

- 全Configではなく実際のTemplate出力に追加する項目例 · `kind`・`base_max_spacing_m`・`refinement`・`maximum_cells`を維持

## 参考文献

- [OpenFOAM symmetryPlane](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/constraint/symmetryPlane/)
- [OpenFOAM blockMesh](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.3-mesh-generation-with-the-blockmesh-utility)
- [Dornier et al., Mean Mesh Adaptation for Efficient CFD Simulations with Operating Conditions Variability, 2024](https://arxiv.org/abs/2412.01274)
- 条件サンプルに基づく平均誤差適応研究は参考方法論 · 当該アルゴリズムの実装や任意の超細密/超粗密半領域分割の精度保証を意味しない

## 研究を参考にした格子遷移

- [研究を参考にした格子遷移](APPLE-STORAGE-METHODS.ja.md)

- [Alexander, Jakhar & Dasgupta (2024), Scientific Reports 14, 25402](https://doi.org/10.1038/s41598-024-76385-y)
- [Alexander, Jakhar & Dasgupta (2025), Scientific Reports 15, 11534](https://doi.org/10.1038/s41598-025-95886-y)
