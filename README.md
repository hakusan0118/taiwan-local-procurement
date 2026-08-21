# Taiwan Local Procurement

以可追溯、可重現的方式整理臺灣地方政府採購決標資料。第一階段比較花蓮縣地方政府體系的 2010 與 2023 年決標公告，之後再逐年擴充為公共監督儀表板。

## 第一階段範圍

- 機關：花蓮縣政府及代碼 `3.76.55` 底下的所屬機關、13 個鄉鎮市公所及所屬機關
- 年度：2010、2023
- 公告：只保留公告類型完全等於「決標公告」的紀錄
- 來源：OpenFun 政府採購標案 API（原始資料來自行政院公共工程委員會）

## 執行方式

1. 到 GitHub repository 的 **Actions**。
2. 選擇 **整理花蓮決標資料**。
3. 點 **Run workflow**，選擇 `2010`、`2023` 或 `both`。
4. 完成後可下載 workflow artifact；資料也會提交到執行用的分支。

本機執行：

```bash
python scripts/fetch_procurement.py --year 2023
python scripts/build_exports.py --years 2010 2023
```

## 資料結構

- `data/raw/hualien/<year>/daily/`：逐日 API 原始回應，作為稽核依據
- `data/raw/hualien/<year>/tenders/`：各案完整 API 回應
- `data/processed/hualien/procurement_<year>.csv`：單年度標案表
- `data/processed/hualien/procurement_master.csv`：跨年度合併主表
- `data/processed/hualien/vendors.csv`：標案與得標廠商關聯
- `data/processed/hualien/data_quality.csv`：失敗日期與資料品質問題

CSV 採 UTF-8 BOM，Microsoft Excel 可直接開啟。金額缺漏保留空白，不會填成零。

## 合法、低負載原則

- 優先使用公開 API，不繞過登入、CAPTCHA、IP 封鎖或其他存取限制。
- 單線程請求、固定間隔、指數退避；已成功下載的檔案直接使用快取。
- API 回傳非 JSON 或請求失敗時留下錯誤紀錄，不誤判為零筆。
- 公開成果只保留公共監督所需欄位，不主動發布聯絡人、電話、私人地址等非必要個資。
- 分析結果不得冒充政府官方服務，並保留原始公告連結供核對。

## 授權與來源

資料引用：**CC-BY 歐噴, 工程會**。

程式碼授權將在正式公開前另行決定。資料內容以政府電子採購網原公告為準。
