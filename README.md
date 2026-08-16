# idontwannareadpaper

每天自動挑三篇音樂資訊檢索（MIR）的新論文，讀完全文，寫成中英對照的分析，發布到一個可搜尋的網頁上。

網站：https://megan8821.github.io/idontwannareadpaper/

## 這裡有什麼

```
index.html            當天的三篇（主頁）
topics/<子領域>.html   該子領域讀過的全部論文，由新到舊
data/YYYY-MM-DD.json  每天的原始資料 ← 真正的資料庫在這裡
build_site.py         從 data/ 產生所有 HTML，並在產出前驗證資料
test_build_site.py    資料層單元測試（標準函式庫，不需要瀏覽器）
verify_site.py        瀏覽器檢查，由 CI 跑
```

兩層檢查分工不同：`test_build_site.py` 問「資料合不合格、每塊該產出什麼」，
`verify_site.py` 問「產出來的網站在瀏覽器裡對不對」。前者毫秒級且不需要瀏覽器，
所以 CI 先跑它——資料錯了就不用等 Playwright 裝完才知道。

主頁只放當天，因為依日期瀏覽撐不住：累積一年就是 365 個日期標題要滑過去，
而子領域固定就那六個。過了今天的論文一律從主題頁進去找。

**搜尋是跨頁的。** 每一頁都內嵌一份全站索引（只有標題、作者、ID、日期、主題，
不含分析全文），所以在主頁搜一篇上個月的論文，會出現「在其他頁面找到 N 篇」，
點下去直接跳到該論文所在的主題頁並展開那張卡。要回到某一天就搜那天的日期
（例如 `2026-08-10`）。索引目前每篇約 276 bytes，一年約 295KB——如果哪天嫌它
太肥，該做的是改成分頁載入，而不是把它拿掉。

整個網站是純靜態的：沒有後端、沒有資料庫伺服器、沒有外部 CSS 或 JS。
每個 HTML 都是自足的單一檔案，離線也能開，十年後也不會壞。

## 每天發生什麼事

台北時間每天早上九點，一個排程任務會：

1. 抓 arXiv 的 `cs.SD`、`eess.AS`、`cs.IR` 最新列表，濾出跟音樂有關的論文
   （語音、ASR、TTS、深偽偵測、環境音會被排除）
2. 比對 `data/` 裡已經讀過的 arXiv ID，排除重複
3. 依六個關注的子領域排序，挑出三篇
4. 逐篇讀摘要頁與 HTML 全文，包含實驗與限制章節
5. 寫成中英對照的分析：動機、背景與相關研究、方法、限制、討論
6. 存成 `data/YYYY-MM-DD.json`，重跑 `build_site.py`，commit 並 push

架構或技術特別新穎的論文會標上 ★，分析寫得更深入。
拿不到全文的（例如付費牆後的期刊論文）會標「僅摘要層級」，不會假裝讀過。

## 關注的子領域

- `generative` 生成式音樂模型
- `representation` 音源分離與表徵學習
- `transcription` 轉譜與音高分析
- `retrieval` 檢索、推薦與情緒
- `cluster` 音樂聚類與相似度
- `other` 其他 MIR 主題

## 自己改東西

**改版面、顏色、區塊順序**：改 `build_site.py`，然後跑

```bash
python3 build_site.py data .
```

不需要任何套件，Python 3 標準函式庫就夠。所有 HTML 會重新產生一次，
過去的論文不用重新分析——分析結果都存在 `data/` 裡。

**改子領域**：`build_site.py` 開頭的 `SUBFIELDS`。加一個子領域就會多一個主題頁與一個導覽連結；
沒有任何論文的子領域不會產生頁面。

**加一天**：在 `data/` 放一個新的 JSON（格式見 `build_site.py` 開頭的說明），重跑一次就好。
schema 是強制的——欄位缺漏、`subfield` 打錯字、section 少一個、`arxiv_id` 重複，
都會讓 build 直接失敗並指出是哪一篇，不會安靜地產出一個看起來正常但其實錯的頁面。

段落過長則只警告不擋（中文 >400 字、英文 >160 words），而且只看最新一天——
文風是判斷題，不該擋住當天的產出，而警告整個資料庫會長到沒人讀。

**跑測試**：

```bash
python3 -m unittest discover        # 資料層，53 項，不到一秒
```

## 資料格式

```json
{
  "date": "2026-08-05",
  "entries": [
    {
      "arxiv_id": "2607.16657",
      "title_en": "...", "title_zh": "...",
      "authors": "...", "submitted": "2026-07-18", "categories": "cs.SD",
      "subfield": "representation",
      "deep": true,
      "fulltext_read": true,
      "why_zh": "為什麼挑這篇", "why_en": "...",
      "sections": {
        "motivation":  {"zh": "...", "en": "..."},
        "intro":       {"zh": "...", "en": "..."},
        "method":      {"zh": "...", "en": "..."},
        "limitation":  {"zh": "...", "en": "..."},
        "discussion":  {"zh": "...", "en": "..."}
      }
    }
  ]
}
```

## 已知限制

- arXiv 官方 API 被 robots.txt 擋掉，所以讀的是給人看的列表頁，偶爾會漏掉分類邊緣的論文
- 抓取有速率限制，每天控制在七到八次以內
- IEEE、ACM、ISMIR、ICASSP 不是每日來源也拿不到全文，改為每週掃一次，只有摘要的會標記出來
- 「挑哪三篇」是判斷不是演算法，會有偏誤（例如偏好架構有新意的論文）
