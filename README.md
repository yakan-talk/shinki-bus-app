# 神姫バス 接近＆時刻表ナビ (`shinki-bus-app`)

「県立大工学部前」（神姫バス停留所名：`県立大工学部`）と姫路城北口方面（`姫路城大手門前` / `白鷺橋` / `大手前通り` / `姫山公園北・医療センター・博物館・美術館前`）を結ぶ神姫バスの**公式時刻表データ**と**リアルタイム接近情報（走行位置・遅延状況）**を一画面に統合したスマホ対応ダークモードWebアプリです。

## ファイル構成

- `app.py` — バックエンド API ＆ Web サーバー（`navi.shinkibus.jp` リアルタイム接近情報取得＋時刻表統合JSON API）
- `timetable_data.py` — 2026年11月14日改正の神姫バス公式時刻表データ（平日・土日祝）および停留所間所要時間プロファイル
- `static/index.html` — スマホ縦画面対応ダークモードUI
- `static/style.css` — スタイルシート
- `static/app.js` — フロントエンド制御（30秒自動更新・ワンタップ即時更新・逆方向タブ切替・全時刻表展開）

## 起動方法

```powershell
C:\Users\nagoy\AppData\Local\Programs\Thonny\python.exe c:\Users\nagoy\Antigravity-projects\shinki-bus-app\app.py
```

ブラウザで `http://127.0.0.1:8050/` を開くとアプリが表示されます。

## 主なAPIエンドポイント

- `GET /api/bus-status?direction=to_castle` — 県立大工学部前 → 姫路城北口方面の次発バス接近状況・現在走行位置・直近5本リスト
- `GET /api/bus-status?direction=to_univ` — 姫路城北口方面 → 県立大工学部前の次発バス接近状況・現在走行位置・直近5本リスト
- `GET /api/timetable?direction=to_castle|to_univ` — 平日・土日祝の全時刻表JSON
