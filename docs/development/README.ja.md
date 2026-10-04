# 開発文書

- 2026-10-05 · V1.0 · baseline `e861572`
- 詳細な技術基準は韓国語版で管理します。この日本語版は範囲と参照先の案内であり、全文翻訳ではありません。

[한국어](README.md) · [English](README.en.md) · [日本語](README.ja.md)

- [環境と最初の変更](ONBOARDING.md)
- [要件と受入基準](REQUIREMENTS.md)
- [システム・構成要素](ARCHITECTURE.md)
- [Config・保存・結果の契約](DATA-CONTRACTS.md)
- [状態・API・エージェント操作](RUNTIME-API.md)
- [試験と数値・実験検証](VERIFICATION.md)
- [インストール・復旧・配布](OPERATIONS.md)
- [未完了事項と優先順位案](BACKLOG.md)
- [壁面層とAMRの開発案](MESH-ROADMAP.md)
- [引継ぎと文書管理](MAINTENANCE.md)
- [設計判断](decisions/README.md)
- [調査資料](REFERENCES.md)

```bash
python tools/check_development_docs.py
```

- プロジェクト・結果・未コミット変更を保持
- ソルバー設置・実行接続・可視化準備・物理検証は別状態
- AMR・壁面層接続・実験検証・全ソルバー対応の完了を意味しない
