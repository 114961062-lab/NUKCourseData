# 高大課程CSV自動更新系統

本Repository透過GitHub Actions定時呼叫Cloudflare Worker，彙整高大115-1全校課程並產生CSV，供CodePen或其他靜態網站讀取。

## 一、建立Repository

1. 在GitHub帳號 `114961062-lab` 建立公開Repository：`NUKCourseData`。
2. 將本套件內全部檔案上傳到Repository根目錄，必須保留 `.github/workflows` 等資料夾結構。
3. CSV公開網址將固定為：

   `https://raw.githubusercontent.com/114961062-lab/NUKCourseData/main/data/nuk_courses_1151.csv`

## 二、允許Actions寫入

進入Repository：

`Settings → Actions → General → Workflow permissions`

選擇 `Read and write permissions` 後儲存。Workflow本身也已限制為 `contents: write`。

## 三、第一次手動執行

1. 進入 `Actions`。
2. 選擇「更新高大課程 CSV」。
3. 點選 `Run workflow`。
4. 等待綠色勾勾。
5. 回到 `data/nuk_courses_1151.csv`，確認已有課程資料。

之後系統會每6小時自動執行；GitHub排程使用UTC，可能延遲數分鐘。

## 四、CodePen串接

`codepen/csv-loader.js`已填入上述Raw CSV網址。可以把內容放到CodePen JavaScript最前方，呼叫：

```javascript
const courses = await loadNukCourseCsv();
console.log(`已讀取 ${courses.length} 門課`);
```

## 五、更新保護

- 每個單位最多重試3次。
- 同時最多查詢3個單位，避免對Worker造成過大壓力。
- 某單位失敗時，優先保留該單位上一版資料。
- 第一次執行若抓取不完整，或總課程少於100門，不覆蓋CSV。
- 資料沒有變更時，不會產生無意義的commit。

## 六、手動測試

電腦已安裝Python 3.12時，可在Repository根目錄執行：

```bash
python scripts/update_courses.py
```

不需要安裝第三方Python套件。
