# 高大89至114學年度歷史課程封存

本套件加入現有 `NUKCourseData` Repository 後，可在 Actions 頁面按一次執行，分批抓取民國89至114學年度的第1學期、第2學期與暑修課程。

## 請放入現有Repository的檔案

```text
.github/workflows/archive-history.yml
scripts/archive_history.py
scripts/build_history_index.py
```

現有檔案不必刪除，115學年度每6小時更新的工作流程也會保留。

## 執行方式

1. 將上述三個檔案放到相同路徑並提交。
2. 進入GitHub Repository上方的「Actions」。
3. 左側選擇「建立高大89-114歷史課程資料」。
4. 點選「Run workflow」，再按一次綠色按鈕。
5. 等待「彙整並提交歷史資料」完成。

這是一個長時間工作。系統同時最多處理2個學年度，避免短時間對高大課程網站送出過多查詢；完整執行時間可能約1至3小時，請勿在尚未完成時重複啟動。

## 產出位置

```text
data/history/nuk_courses_0891.csv
data/history/nuk_courses_0892.csv
data/history/nuk_courses_0893.csv  （有暑修資料時才建立）
...
data/history/nuk_courses_1141.csv
data/history/nuk_courses_1142.csv
data/history/nuk_courses_1143.csv  （有暑修資料時才建立）
data/history/index.json
```

各CSV欄位與現行 `data/nuk_courses_1151.csv` 相同。`index.json` 會記錄完成年度、各學期課程數、缺少年度及部分失敗年度。

## 失敗處理

- 個別部別暫時失敗時，若Repository已有該部別舊資料，會保留上一版。
- 若某年度標記為 `partial`，可再次執行同一個工作流程；不需刪除已成功的資料。
- 早期尚未成立的系所回傳0門屬正常情況。
- 民國89至99學年度必須保留前置零，例如 `089`、`099`。
