# 奇想和書航路 — Curio Washo Atlas（週刊書誌版）

**毎週の書誌データから、まだ見ぬ奇書を発掘する。**

「奇想和書航路」は、国立国会図書館の **JAPAN/MARC(M/S) 週次ZIP** をまとめて取り込み、マニエリスム・驚異の部屋・錬金術・博物誌・図像学など、**18概念・43テーマ**に関連する和書を探索する非公式の独立書誌サイトです。初期登録書籍は**0冊**です。洋書版の書誌は引き継がず、外部の検索APIも利用しません。

- 姉妹サイト：[奇想洋書航路](https://amorrmoa.github.io/curio-book-atlas/)
- 公開予定：[奇想和書航路](https://amorrmoa.github.io/curio-washo-atlas/)
- 公式データ：[JAPAN/MARCデータ（毎週更新）](https://www.ndl.go.jp/data/data_service/jnb_product)

## システムの特徴

| 項目 | 内容 |
| --- | --- |
| 取得元 | 国立国会図書館 JAPAN/MARC(M/S) 週次配布ZIP |
| 外部検索API | 使用しない（公開ZIPのダウンロードは行う） |
| 更新頻度 | 毎週日曜日10:17 JSTごろ（GitHub Actionsの実行時刻は前後する） |
| 初回取得 | 直近8週分のZIP（設定変更可能、最大12週） |
| 2回目以降 | 未処理のZIPのみ取得、過去の書誌は保持 |
| 掲載対象 | 原則2026年6月〜2028年12月刊行の日本語の単行書 |
| 選定 | 書名・件名から18概念・43テーマとの一致を判定 |
| 新規追加枠 | 最大16冊／回・同一出版社から最大2冊／回 |
| 管理 | 重複防止、既存書誌の更新、削除通知への対応 |
| 出典表示 | 国立国会図書館の書誌データを加工して作成した旨を掲載 |

### なぜ週次ZIPなのか

Google Booksや国立国会図書館サーチの**検索用APIを繰り返し呼ばない**ので、APIキーや検索のクォータに依存しません。ただし、ダウンロード先の利用条件・サーバー負荷に配慮する必要があります。ZIPも配布停止、形式変更、通信エラーが起こりえます。**利用制限ゼロという意味ではありません。**

この書誌は、国立国会図書館側で作成・更新された**書誌完成・更新分**です。発売前の新刊を速報的に見つける用途には向きません。情報が遅れて入ることもあります。

### 採用候補の扱い

自動収集した書籍はすべて「自動発見候補」と表示します。研究書としての価値や出版内容を人間が確認した推薦ではありません。書誌には版違い、発売日の修正、重版などが含まれる場合があります。書誌詳細はNDLサーチへの検索リンクで確認してください。

## GitHub Pagesで公開する（初回）

**重要：洋書用の `curio-book-atlas` にはアップロードしないでください。**

1. GitHubの [新規リポジトリ作成画面](https://github.com/new) で **`curio-washo-atlas`** という**別リポジトリ**を作成します。`Public`を選びます。READMEの自動生成はオフでも構いません。
2. このZIPを解凍し、`.github`、`docs`、`scripts`、`tests`、`README.md` を**新しいリポジトリのルート（最上位）**へアップロードして `Commit changes` を押します。`docs/index.html` と `.github/workflows/weekly-catalogue.yml` が正しい位置にあることを確認してください。**古い `discover-and-deploy.yml` は混ぜないでください。**
3. [Pages設定](https://github.com/amorrmoa/curio-washo-atlas/settings/pages) で **Settings → Pages → Source: GitHub Actions** を選びます。
4. [Actions](https://github.com/amorrmoa/curio-washo-atlas/actions) で **Update weekly JAPAN/MARC catalogue and publish** → **Run workflow** を選びます。
5. 緑のチェックなら [サイト](https://amorrmoa.github.io/curio-washo-atlas/) を開きます。初回はサイトへの公開反映に少し時間差が出ることがあります。

初回実行は直近8週分の書誌ファイルをダウンロードします。取得に失敗するとその回のActionsはエラーになり、既存の公開サイトと書誌ファイルを勝手に消さない構成です。

## 主なファイル

```text
.github/workflows/weekly-catalogue.yml  毎週の自動取込・サイト公開
docs/index.html                       Webページ本体
docs/assets/site.css                 スタイル
docs/assets/site.js                  検索・並び替え・保存
docs/data/books.json                 累積書誌（初期0冊）
docs/data/processed_archives.json    取得済み週次ファイルの履歴
scripts/weekly_marc.py               ZIP取得・MARC変換・採用判断
scripts/takayama_ja_taxonomy.json    18概念・43テーマ
tests/test_weekly_marc.py            オフラインテスト
```

## 自分で動作を試す

Python 3.12以上、追加のPythonライブラリは不要です。

```bash
python -m unittest discover -s tests -v
python scripts/weekly_marc.py --dry-run
```

実ファイルへのアクセスを避け、手元にダウンロードした週次ZIPを試すこともできます。

```bash
python scripts/weekly_marc.py --archive /path/to/official_jmo.zip --dry-run
```

ZIPの取得元ページが変更された場合は、`scripts/weekly_marc.py` 内の `parse_index()` および `records_from_zip()` を確認してください。

## 出典・利用条件

**出典：国立国会図書館 JAPAN/MARC(M/S)書誌データを本サイト独自のテーマ分類で加工して作成。**

- [国立国会図書館「JAPAN/MARCデータ（毎週更新）」](https://www.ndl.go.jp/data/data_service/jnb_product)
- [国立国会図書館「書誌データの利用方法」](https://www.ndl.go.jp/data/data_service/quickguide)

国立国会図書館作成の書誌データは原則として無償利用できますが、出典・加工したことの表示が求められます。第三者提供データには別の条件が適用される場合があります。書籍の本文は含みません。

**動作検証について：** MARC21とMARCタグ形式を使ったオフラインテストは行っていますが、このパッケージ作成環境から実際の2026年のZIPを直接取得することはできませんでした。初回のGitHub Actions実行で、公式配布ファイルとの完全な互換性を最終確認してください。もしエラーが出た場合はログをご提示ください。

---

*「驚異」は、いつも書物の中に。*
