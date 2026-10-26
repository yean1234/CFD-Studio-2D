# 液浸水槽の2D断面計算

[한국어](SECTION-2D.md) · [English](SECTION-2D.en.md) · [日本語](SECTION-2D.ja.md)

- TMC-49二重液浸水槽のConfigを、**CPU中心を通るy–z鉛直断面**の2D OpenFOAMケースとして生成
- 粗い格子(2~3 mm)CFDのセルごとの蒸気体積率と壁面熱流束を、気泡場研究パイプラインの入力形式で出力
- 形状・物性・実行設定の基準は3D Configのみ · 2Dは同じConfigに`case_dimension`と`section_2d`を追加
- 3Dの既定動作と生成ファイルは変更なし · 2Dは明示的に選択した場合のみ生成

## 研究との対応

- 流れ: 粗い格子CFD → セルごとの`(α, q″)` → 相関式による気泡仕様 → 合成気泡場 → 熱流束推定モデルによる検証
- 2D断面はBubbleML 2D正解データと同じ次元で比較するための**適用経路**の入力
- `coarse_inputs.csv`はCooperゲートコード(`cooperval.coarsen`)の`coarse_inputs.csv`と同じ列
- BubbleML側の粗い入力(検証経路)はCooperゲートコードが担当 · 本リポジトリは水槽CFD側のみ生成

## 断面と軸

| OpenFOAM軸 | 水槽座標 | 備考 |
| --- | --- | --- |
| x | 奥行きz (0 = 背面壁, 70 mm = 前面壁) | ボードz 15~23 mm, CPU面z = 23 mm |
| y | 高さy | 重力 −y · 界面400 mm · 上部開放面800 mm |
| z | 1セル厚 (`frontAndBack` = `empty`) | 既定の厚さ = `mesh.dx_mm` |

- 断面位置: `section_2d.x_mm` · 空欄なら`heater.cpus[cpu_index]`のx中心(既定CPU0, 185 mm)
- CPU発熱面が壁として残るのはy–z断面のみ · x–y正面断面ではCPU面が断面に垂直
- CPUを通らない断面は生成前にエラー · ボードとコイルは断面が通る場合のみ固体領域として生成
- 既定Config: 6,140セル · ヒーター面13枚(3.08 mm) · 0.1 sあたり約6 s(直列, 下記の検証環境)

## 実行

```bash
cd tmc49_full_tank
MODE=2D ./Allrun                                  # Configのcase_dimensionより優先
python3 tools/build_case.py --dimension 2D --check # 生成せず検証のみ
python3 tools/export_coarse_2d.py --out export_2d  # 計算後に粗い入力を出力
```

- Configに`"case_dimension": "2D"`があれば`./Allrun`とStudio実行も2D生成器を使用
- Studio同梱Configの`immersion_2d`がこの設定を含む
- 2Dでは並列数を`NP2D_MAX`(既定4)に制限 · 数千セルでの通信コストを回避
- 計測条件の適用: `CONDITION=C3_T20 MODE=2D ./Allrun`
- その後3Dで生成すると`constant/section2d.json`を削除 · 古い2D格子対応表を残さない

## 3D → 2Dのスケーリング

| `heat_rule` | 保存する量 | 2Dヒーター(既定Config) | 幅あたり入熱 |
| --- | --- | --- | --- |
| `local_flux` (既定) | CPU熱流束・発熱高さ | 72.0 kW/m² · 40 mm | 2,880 W/m (水槽幅平均の4.96倍) |
| `width_average` | 発熱高さ・水槽幅あたり電力 | 14.5 kW/m² · 40 mm | 581 W/m |
| `flux_and_power` | CPU熱流束・水槽幅あたり電力 | 72.0 kW/m² · 8.07 mm (CPU中心基準で縮小) | 581 W/m |

- 幅あたり電力の基準幅: `represented_width_mm` · 空欄なら水槽幅456 mm
- CPU面は`externalWallHeatFluxTemperature`の`flux`モード · 厚さに依存せず熱流束を指定
- コイルUA目標 = 3D `UA_target_W_K` × (2D幅あたり入熱 ÷ 3D入熱) · 上層液の平衡温度`Ta + Q/UA`を3Dと一致させる規則
- コイルUAは格子上限の90%に制限(3D生成器と同じ規則) · 直接指定: `section_2d.coil_UA_W_mK`
- `local_flux`は3 mm格子のコイル上限(約52 W/(m·K))を超え、上層液が初期約0.02 K/sで昇温 · 約730 s後にTMC-49沸点47 °Cへ到達
- 長時間の熱平衡が必要な場合は`flux_and_power`またはコイル周辺の格子細分化を使用 · 生成器が毎回この数値を表示

## 出力ファイル

| ファイル | 内容 |
| --- | --- |
| `fields_2d.h5` (h5pyがなければ`.npz`) | `temperature`・`velx`・`vely`・`alpha_vapour`・`alpha_water` (フレーム, y, x) · 固体セルNaN · `mask`・座標・無次元基準値 |
| `heater_wall_2d.csv` | フレーム・ヒーター面ごとのq″、壁隣接セル温度、CFD壁面温度、蒸気体積率、下層液平均温度 |
| `coarse_inputs.csv` | `case_id, coarse_cell, x_m, q_W_m2, vapor_fraction` · 時間平均 · Cooperゲートと同じ列 |
| `coarse_inputs_extended.csv` | 上記 + 壁面温度・過熱度・サブクール度・平均フレーム数 |
| `export_manifest.json` | 断面・スケーリング・コイル・流体値・使用フレーム・仮定一覧 |

- 時間平均: 先頭30%のフレームを除外(`--skip-initial`) · 初期条件`0`フォルダは既定で除外
- `x_m`: ヒーターに沿った位置 · 本ケースでは高さy [m]
- `--coarse-dx-mm`: ヒーター面をより粗い長さで平均 · 余りはCooperゲートと同様に除外
- サブクール度: TMC-49沸点 − 下層液(液相率0.9以上のセル)の面積加重平均温度
- OpenFOAMなしでASCII・binaryフィールドを直接読込 · セル順序は`constant/section2d.json`の格子対応表を使用

## 検証結果

- 基準: 2026-10-05 · Linuxコンテナ · OpenCFD OpenFOAM v2312 · 既定`immersion_2d` Config
- `blockMesh`・`checkMesh`: Mesh OK · 解析方向2 · `cpu`面13枚 · `frontAndBack` empty
- 直列で0.1 sまで計算完了 · CPU前面セルで蒸気生成(最大蒸気体積率約0.6)
- 下層液(y < 300 mm)のエネルギー増加がCPU投入熱量と2%以内で一致(0.1 s: 0.882 J / 0.864 J)
- `MODE=2D ./Allrun` 4プロセス0.05 s: 分割・計算・再構成・VTK変換完了 · 直列結果とセル値一致(相関係数1.0)
- 3D生成ファイルは変更前コードとバイト単位で同一(既定Config・`C3_T20`)
- 単体テスト`tests/test_section_2d.py` 9件合格
- 長時間計算・格子/時間収束・実験比較・気泡統計の検証は未実施

## 制限

- 2D断面は水槽x方向の流れと気泡拡散を表現しない · ボード前面47 mm隙間の蒸気滞留を過大評価する可能性
- CPU壁面温度は3 mmセルで約1,100~1,500 Kとなる境界モデル値であり、物理的な壁面過熱度ではない
- 気泡仕様のΔT_supはq″からCooper逆算または壁関数経路で求める必要 · 3Dも同じセル寸法と境界を使用
- TMC-49の臨界圧はConfigに根拠がなく`p_critical_Pa = null` · Cooper換算圧力の計算前に出典確認が必要
- Config編集プレビュー: `case_dimension`が`2D`のとき**2D断面**に切替 · `section_2d.x_mm`と厚さの薄板と、断面にかかる基板・コイル・CPU面のみ表示 · 生成器のメッシュ・境界パッチ・計算結果は表示しない
- 結果Viewerでの2D計算結果表示は未検証 · 研究解析には出力ファイルを推奨
- `section_2d`の`x_mm`・`represented_width_mm`・`thickness_mm`・`coil_UA_W_mK`は空欄で自動計算 · Studioの保存検証もこの4項目の`null`を許可
- Lee係数・蒸気輸送物性・界面張力など3D Configのresearch_preliminary状態をそのまま継承

## 出典

- 設計の参考(測定結果ではない): 個別研究ノートの粗い入力の定義・条件ごとの代表値1つ・BubbleML 2D/3Dの役割分担
- 列構成: Cooperゲートコード`cooperval/coarsen.py`の`coarse_inputs.csv`
- 配列配置: BubbleMLデータセットの(時間, y, x)配置 — Hassan et al., *BubbleML*, NeurIPS 2023 Datasets and Benchmarks
- 相関式: Cooper, M. G. (1984), *Saturation nucleate pool boiling — a simple correlation*, IChemE Symp. Ser. 86
- 測定値: 上記の検証結果のみ本リポジトリで実行した結果
