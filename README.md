# Event_RSS

関西のアニメ・お笑い・映画などの情報源を毎日巡回し、新しく見つかった項目を集めるリポジトリ。
GitHub Actions が毎日 18:07（JST）に `collect.py` を実行し、結果をコミットする。

集めた新着は、休日さがし dot（Claude の定期実行）が読んで「関西休日台帳」に登録する。

## 出力

| ファイル | 中身 |
|---|---|
| `data/new.json` | 直近 7 日に新しく見つかった項目（新しい順）。dot はこれを読む |
| `feed.xml` | `new.json` と同じ内容の RSS。RSS リーダーで購読できる |
| `data/items.json` | これまでに見つけた項目（120 日分） |
| `data/status.json` | 情報源ごとの最終実行結果。`ok: false` なら取得に失敗している |

RSS: https://raw.githubusercontent.com/ractodaisuki/Event_RSS/main/feed.xml

## 検索ワード（interests.json）

興味のある検索ワードは `interests.json` で管理する。ここを書き換えれば、次の巡回から反映される。

| キー | 使うところ | 中身 |
|---|---|---|
| `news` | collect.py（毎日） | Google ニュースの検索 RSS として巡回する。`query` に検索語、`title_pattern`（任意）で告知らしい題名だけを残す。`id` を変えると新しい情報源として扱われる |
| `web_search` | 休日さがし dot（週 1 回） | dot が WebSearch に使う検索語。関西の公演・展示を探して台帳に登録する |
| `exclude_title` | collect.py | この語を題名に含む項目は新着（new.json / feed.xml）に出さない |
| `allow_title` | collect.py | `exclude_title` より優先して残す語 |

## 情報源の追加

`sources.json` に 1 件足す。`type` は次の 3 種類。

- `rss`: RSS / Atom フィード（Google ニュースの検索は interests.json の `news` に書く）
- `links`: ページ内のリンクのうち、`link_pattern`（正規表現）に合うものを項目として拾う
- `page`: ページの本文が変わったら「更新されました」を 1 件出す（項目ごとのリンクがないページ向け）

`title_pattern`（任意）に正規表現を書くと、題名がそれに合う項目だけを残す。ニュース検索の RSS で、ライブの告知以外を落とすのに使う。

新しく足した情報源は、初回の巡回で見つかった項目を既知として登録するだけで、新着には出さない。

## 手元で動かす

```sh
python3 collect.py
```

Python 3.11 以上、標準ライブラリだけで動く。
