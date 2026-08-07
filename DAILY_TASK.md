# 每日任務指令

這份文件是 MIR 每日論文 agent 的完整作業說明。排程每天台北時間 09:00（UTC 01:00）
喚醒一個全新工作階段，那個階段除了這個 repo 之外沒有任何上下文，所以以下步驟必須
能獨立執行完畢。

## 目標

挑三篇還沒讀過的 MIR 論文，讀完全文，寫成中英對照分析，產出一個
`data/YYYY-MM-DD.json` 並推上 `main`。推上去之後 GitHub Actions 會重建網站，
https://megan8821.github.io/idontwannareadpaper/ 就會更新。

## 步驟

### 1. 先確認今天還沒做過

看 `data/` 裡有沒有今天日期的檔案。有的話就停下來，不要重做。

### 2. 收集已讀清單

讀 `data/*.json` 裡所有 `arxiv_id`。這是去重的唯一依據——選出來的三篇不能出現在
這份清單裡。

### 3. 找候選論文

主軸是 arXiv 每日列表，依序看：

- https://arxiv.org/list/cs.SD/recent
- https://arxiv.org/list/eess.AS/recent
- https://arxiv.org/list/cs.IR/recent

官方 API 被 robots.txt 擋掉，只能抓列表頁與全文頁。抓取有速率限制，**整個任務的
arXiv 請求控制在七到八次以內**——大致是三次列表頁加三到四次全文頁，不要用瀏覽器
把每篇候選都點開。

這個環境抓到的 arXiv 內容有延遲，列表上「最新」的日期可能落後真實日期好幾週。
這是預期的，照樣挑列表上最新的未讀論文即可，不要為了湊到今天的日期而空手而歸。

關注的子領域，對應到 JSON 的 `subfield` 欄位：

| subfield | 範圍 |
| --- | --- |
| `generative` | 生成式音樂模型 |
| `representation` | 音源分離與表徵學習 |
| `transcription` | 轉譜與音高分析 |
| `retrieval` | 檢索、推薦與情緒 |
| `cluster` | 音樂聚類與相似度 |
| `other` | 以上皆非但仍屬 MIR |

### 4. 週末規則

週六與週日不找新論文，改從平日累積下來的候選裡挑三篇未讀的補上。做法一樣是讀
`data/*.json` 去重，只是候選來源限定在先前列表頁看過、還沒寫過的論文。

### 5. 讀完全文再寫

每篇都要讀全文，不能只讀摘要。真的拿不到全文（付費牆、抓取失敗）時，把
`fulltext_read` 設成 `false`，網站會標示「僅摘要層級」——不要假裝讀過。

每篇寫五個面向：動機、背景與相關研究、方法、限制、討論。中英各一份完整分析，
兩邊都要能單獨讀懂，不是逐句對譯。一般篇幅中長篇；架構或技術特別新穎的把 `deep`
設成 `true`，並把該篇寫成深度分析。

### 6. 寫出 JSON

schema 完整定義在 `build_site.py` 開頭的 docstring，照著寫。檔名是
`data/YYYY-MM-DD.json`，日期用台北時間。

### 7. 重建與驗證

```
python3 build_site.py            # 重建 index.html 與 archive/
python3 verify_site.py           # 21 項瀏覽器檢查，必須全過
```

`verify_site.py` 需要 Playwright。環境裡已有瀏覽器時用
`PW_CHROMIUM=<chrome 路徑> python3 verify_site.py` 指過去，不要另外下載。

檢查沒過就不要推。

### 8. 推上 main

把新的 `data/YYYY-MM-DD.json` 連同重建出來的 `index.html`、`archive/` 一起 commit，
直接推 `main`。Actions 會自己跑 build 與部署——它是從 `data/` 重建，所以就算
commit 進去的 HTML 有出入也以 CI 的產物為準，但保持 repo 內容一致還是比較好追。

推完確認兩件事：

- workflow「Build and deploy site」跑完是 success
- `curl -sI https://megan8821.github.io/idontwannareadpaper/` 回 200

### 9. 失敗退路

任何一步失敗而且當場修不掉——抓不到 arXiv、build 壞掉、驗證沒過、推不上去——
建立一封 Gmail 草稿當警示，主旨 `[MIR agent] 失敗 YYYY-MM-DD`，內文寫清楚卡在
哪一步、錯誤訊息是什麼、已經做到哪裡。不要無聲失敗。

當天已經寫好但推不上去的分析內容，一併放進那封草稿，不要弄丟。

## 尚未定案的部分

以下幾項刻意留白，等實際跑一兩週看結果再決定，現階段不用處理：

- 每週掃一次 IEEE、ACM、ISMIR、TASLP（不是每日更新且有付費牆，只有概念）
- 挑選偏誤要不要用輪流覆蓋子領域之類的規則去平衡
- 有了 GitHub 之後，Gmail 草稿要不要每天照寫一份當雙保險
- 資料超過三十天後改成增量更新（現在每次全量重建）
