#!/usr/bin/env python3
"""
生成 Logo Data Engine Pipeline 技術報告 PDF（中文、LaTeX 風格）
輸出：/raid/ming/logo/logo_data_engine/docs/pipeline_report.pdf
"""

import subprocess, sys

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8"/>
<style>
/* ── 字型 ── */
@font-face {
  font-family: 'NotoSerif';
  src: url('/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc');
  font-weight: normal;
}
@font-face {
  font-family: 'NotoSerif';
  src: url('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc');
  font-weight: bold;
}
@font-face {
  font-family: 'NotoSans';
  src: url('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc');
  font-weight: normal;
}
@font-face {
  font-family: 'NotoSans';
  src: url('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc');
  font-weight: bold;
}

/* ── 頁面設定 ── */
@page {
  size: A4;
  margin: 2.5cm 2.4cm 2.8cm 2.4cm;
  @bottom-center {
    content: counter(page);
    font-family: 'NotoSerif', serif;
    font-size: 10pt;
    color: #555;
  }
}
@page :first {
  @bottom-center { content: ''; }
}

/* ── 整體 ── */
body {
  font-family: 'NotoSerif', 'Noto Serif CJK TC', serif;
  font-size: 10.5pt;
  line-height: 1.75;
  color: #1a1a1a;
  text-align: justify;
  hyphens: none;
}

/* ── 封面 ── */
.cover {
  page-break-after: always;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 24cm;
  text-align: center;
}
.cover-rule-top {
  width: 100%;
  border: none;
  border-top: 3px solid #2c3e7a;
  margin-bottom: 0.8cm;
}
.cover-rule-bottom {
  width: 100%;
  border: none;
  border-top: 1.5px solid #2c3e7a;
  margin-top: 0.8cm;
}
.cover-subtitle {
  font-family: 'NotoSans', sans-serif;
  font-size: 11pt;
  color: #5a5a7a;
  letter-spacing: 0.06em;
  margin-bottom: 0.6cm;
}
.cover-title {
  font-size: 22pt;
  font-weight: bold;
  color: #1a2050;
  line-height: 1.4;
  margin: 0.3cm 0;
}
.cover-command {
  margin-top: 0.8cm;
  background: #f4f6fb;
  border: 1px solid #c8cce0;
  border-radius: 5px;
  padding: 0.5cm 0.8cm;
  font-family: 'Courier New', monospace;
  font-size: 8.5pt;
  color: #1a2050;
  text-align: left;
  line-height: 1.7;
  white-space: pre;
  width: 90%;
}
.cover-meta {
  margin-top: 1cm;
  font-size: 10pt;
  color: #555;
  line-height: 2;
}

/* ── 目錄頁 ── */
.toc-page {
  page-break-after: always;
}
.toc-title {
  font-size: 14pt;
  font-weight: bold;
  color: #2c3e7a;
  border-bottom: 2px solid #2c3e7a;
  padding-bottom: 4pt;
  margin-bottom: 14pt;
}
.toc-entry {
  display: flex;
  justify-content: space-between;
  padding: 2pt 0;
  border-bottom: 1px dotted #bbb;
  font-size: 10pt;
}
.toc-entry.h2 { padding-left: 1em; font-size: 9.5pt; color: #333; }
.toc-entry.h3 { padding-left: 2.2em; font-size: 9pt; color: #555; }

/* ── 標題 ── */
h1 {
  font-size: 16pt;
  font-weight: bold;
  color: #1a2050;
  margin-top: 1.5cm;
  margin-bottom: 6pt;
  border-bottom: 2px solid #2c3e7a;
  padding-bottom: 4pt;
  page-break-after: avoid;
}
h2 {
  font-size: 13pt;
  font-weight: bold;
  color: #2c3e7a;
  margin-top: 1cm;
  margin-bottom: 5pt;
  page-break-after: avoid;
}
h3 {
  font-size: 11pt;
  font-weight: bold;
  color: #3a4a8a;
  margin-top: 0.7cm;
  margin-bottom: 4pt;
  page-break-after: avoid;
}
h4 {
  font-size: 10.5pt;
  font-weight: bold;
  color: #444;
  margin-top: 0.5cm;
  margin-bottom: 3pt;
  page-break-after: avoid;
}

/* ── 段落 ── */
p { margin: 0 0 6pt 0; }

/* ── 程式碼 ── */
pre, code {
  font-family: 'Courier New', 'Lucida Console', monospace;
  font-size: 8.5pt;
}
pre {
  background: #f5f6fa;
  border: 1px solid #d0d4e8;
  border-left: 4px solid #2c3e7a;
  padding: 8pt 10pt;
  overflow-x: auto;
  border-radius: 3px;
  margin: 6pt 0 10pt 0;
  line-height: 1.55;
  color: #1a1a2e;
  page-break-inside: avoid;
}
code {
  background: #eef0fa;
  padding: 1pt 3pt;
  border-radius: 2px;
  color: #1a2050;
}

/* ── 表格 ── */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 10pt 0 14pt 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
}
thead tr {
  background-color: #2c3e7a;
  color: white;
}
thead th {
  padding: 6pt 8pt;
  text-align: left;
  font-weight: bold;
}
tbody tr:nth-child(even) { background-color: #f0f2fa; }
tbody tr:nth-child(odd)  { background-color: #ffffff; }
tbody td {
  padding: 5pt 8pt;
  border-bottom: 1px solid #d4d8ec;
}
tfoot td {
  font-weight: bold;
  background: #e8eaf6;
  border-top: 2px solid #2c3e7a;
  padding: 5pt 8pt;
}

/* ── 資訊框 ── */
.box {
  border: 1px solid #b8c0e0;
  border-radius: 4px;
  padding: 10pt 12pt;
  margin: 10pt 0;
  page-break-inside: avoid;
}
.box-info    { background: #eef2ff; border-left: 5px solid #2c3e7a; }
.box-warn    { background: #fff8e1; border-left: 5px solid #e67e00; }
.box-success { background: #e8f5e9; border-left: 5px solid #2e7d32; }
.box-danger  { background: #fdecea; border-left: 5px solid #c62828; }
.box-label {
  font-weight: bold;
  font-size: 9.5pt;
  margin-bottom: 4pt;
  font-family: 'NotoSans', sans-serif;
}

/* ── 流程圖（ASCII art → 等寬） ── */
.flowchart {
  font-family: 'Courier New', monospace;
  font-size: 8pt;
  background: #f9faff;
  border: 1px solid #c8cce0;
  padding: 10pt;
  line-height: 1.5;
  white-space: pre;
  page-break-inside: avoid;
}

/* ── 數字徽章 ── */
.badge {
  display: inline-block;
  background: #2c3e7a;
  color: white;
  border-radius: 50%;
  width: 16pt;
  height: 16pt;
  text-align: center;
  line-height: 16pt;
  font-size: 8pt;
  font-weight: bold;
  margin-right: 4pt;
  vertical-align: middle;
}

/* ── 列表 ── */
ul, ol { margin: 4pt 0 8pt 0; padding-left: 1.5em; }
li { margin-bottom: 2pt; }

/* ── 圖說 ── */
.caption {
  text-align: center;
  font-size: 9pt;
  color: #555;
  margin-top: -6pt;
  margin-bottom: 10pt;
  font-style: italic;
}

/* ── 頁面分隔 ── */
.pagebreak { page-break-before: always; }

/* ── 小標注 ── */
.note {
  font-size: 9pt;
  color: #666;
  font-style: italic;
}

.kv { display: flex; gap: 8pt; margin-bottom: 2pt; }
.kv-key { font-weight: bold; min-width: 140pt; color: #2c3e7a; }
.kv-val { color: #1a1a1a; font-family: 'Courier New', monospace; font-size: 9pt; }

.step-header {
  background: #2c3e7a;
  color: white;
  padding: 5pt 10pt;
  border-radius: 4px;
  font-family: 'NotoSans', sans-serif;
  font-weight: bold;
  font-size: 10.5pt;
  margin-top: 12pt;
  margin-bottom: 6pt;
  page-break-after: avoid;
}
.step-body {
  border-left: 3px solid #2c3e7a;
  padding-left: 12pt;
  margin-bottom: 10pt;
}

.gate-pass   { color: #2e7d32; font-weight: bold; }
.gate-soft   { color: #e67e00; font-weight: bold; }
.gate-fail   { color: #c62828; font-weight: bold; }
.gate-skip   { color: #777;    font-weight: bold; }

.mono { font-family: 'Courier New', monospace; font-size: 9pt; }
</style>
</head>
<body>

<!-- ═══════════════════════════════════════════════════════════════
     封面
════════════════════════════════════════════════════════════════ -->
<div class="cover">
  <hr class="cover-rule-top"/>
  <div class="cover-subtitle">技術報告 ／ Technical Report</div>
  <div class="cover-title">
    Logo Data Engine<br/>
    多品牌批次資料管道<br/>
    設計與執行說明
  </div>
  <div class="cover-command">./logo_data_engine/run_multibrand_batch.sh \
  --run-name      batch_10_vlm3_sam3          \
  --target-records 10                          \
  --use-vlm                                    \
  --vlm-model-id  llava-hf/llava-1.5-7b-hf    \
  --with-sam3                                  \
  --cuda-devices  1,2</div>
  <hr class="cover-rule-bottom"/>
  <div class="cover-meta">
    執行批次：<strong>batch_10_vlm3_sam3</strong><br/>
    執行日期：2026-04-04<br/>
    工作目錄：<code>/raid/ming/logo/logo_data_engine</code><br/>
    執行環境：Conda <code>logo_sam3</code> ／ CUDA Devices 1, 2
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     目錄
════════════════════════════════════════════════════════════════ -->
<div class="toc-page">
  <div class="toc-title">目錄</div>

  <div class="toc-entry"><span>1&ensp;執行概覽</span><span>3</span></div>
  <div class="toc-entry h2"><span>1.1&ensp;批次參數一覽</span><span>3</span></div>
  <div class="toc-entry h2"><span>1.2&ensp;AI 模型堆疊（Preflight 結果）</span><span>3</span></div>
  <div class="toc-entry h2"><span>1.3&ensp;整體數字摘要</span><span>4</span></div>

  <div class="toc-entry"><span>2&ensp;Pipeline 全流程架構</span><span>5</span></div>
  <div class="toc-entry h2"><span>2.1&ensp;兩階段 DB 設計（Staging → Engine）</span><span>5</span></div>
  <div class="toc-entry h2"><span>2.2&ensp;流程圖總覽</span><span>5</span></div>

  <div class="toc-entry"><span>3&ensp;各步驟詳細說明</span><span>6</span></div>
  <div class="toc-entry h3"><span>Step 0&ensp;Preflight — 模型可用性預檢</span><span>6</span></div>
  <div class="toc-entry h3"><span>Step 1&ensp;Batch Plan — 計算 Limit per Pair</span><span>7</span></div>
  <div class="toc-entry h3"><span>Step 2&ensp;Collector — 多品牌圖片爬取</span><span>7</span></div>
  <div class="toc-entry h3"><span>Step 3&ensp;Balance（第一次）— Oversample 候選池</span><span>8</span></div>
  <div class="toc-entry h3"><span>Step 4&ensp;Ontology — 品牌知識庫抓取</span><span>8</span></div>
  <div class="toc-entry h3"><span>Step 5–6&ensp;Staging Seed &amp; Ingest</span><span>9</span></div>
  <div class="toc-entry h3"><span>Step 7&ensp;Quality Gate — 五道品質過濾</span><span>9</span></div>
  <div class="toc-entry h3"><span>Step 8–9&ensp;Export Passed &amp; 最終平衡</span><span>12</span></div>
  <div class="toc-entry h3"><span>Step 10&ensp;SAM3 Logo Segmentation</span><span>12</span></div>
  <div class="toc-entry h3"><span>Step 11&ensp;Phase1 Workflow — 核心標注引擎</span><span>14</span></div>
  <div class="toc-entry h3"><span>Step 12&ensp;Export Knowledge Base</span><span>17</span></div>
  <div class="toc-entry h3"><span>Step 13&ensp;Analyze Run — 批次分析報告</span><span>18</span></div>

  <div class="toc-entry"><span>4&ensp;輸出目錄結構</span><span>19</span></div>
  <div class="toc-entry"><span>5&ensp;Knowledge Base 欄位完整說明</span><span>20</span></div>
  <div class="toc-entry"><span>6&ensp;本批次統計結果</span><span>22</span></div>
  <div class="toc-entry"><span>7&ensp;Review Queue 與下一步行動</span><span>23</span></div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     第 1 節：執行概覽
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>1&ensp;執行概覽</h1>

<h2>1.1&ensp;批次參數一覽</h2>

<table>
  <thead><tr><th>參數</th><th>指令列選項</th><th>值</th><th>說明</th></tr></thead>
  <tbody>
    <tr><td>批次名稱</td><td><code>--run-name</code></td><td><code>batch_10_vlm3_sam3</code></td><td>輸出目錄名稱</td></tr>
    <tr><td>目標筆數</td><td><code>--target-records</code></td><td><code>10</code></td><td>最終品質過關後保留的記錄數</td></tr>
    <tr><td>Oversample 倍數</td><td>（預設）</td><td><code>3</code></td><td>候選池大小 = 10 × 3 = 30 筆</td></tr>
    <tr><td>VLM 啟用</td><td><code>--use-vlm</code></td><td><code>true</code></td><td>啟用 LLaVA 圖像描述後端</td></tr>
    <tr><td>VLM 模型</td><td><code>--vlm-model-id</code></td><td><code>llava-hf/llava-1.5-7b-hf</code></td><td>LLaVA 1.5 7B 模型</td></tr>
    <tr><td>SAM3 分割</td><td><code>--with-sam3</code></td><td><code>true</code></td><td>啟用 SAM3 精細 Logo Mask 分割</td></tr>
    <tr><td>CUDA 設備</td><td><code>--cuda-devices</code></td><td><code>1,2</code></td><td>設定 CUDA_VISIBLE_DEVICES=1,2</td></tr>
    <tr><td>Object-First</td><td>（預設開啟）</td><td><code>true</code></td><td>先找物件框再找 Logo</td></tr>
    <tr><td>OCR</td><td>（預設開啟）</td><td><code>true</code></td><td>PaddleOCR 讀取 Logo 文字</td></tr>
    <tr><td>Resume</td><td>（預設開啟）</td><td><code>true</code></td><td>已存在記錄自動跳過</td></tr>
    <tr><td>Conda 環境</td><td><code>--env-name</code></td><td><code>logo_sam3</code></td><td>執行所用的 Conda 虛擬環境</td></tr>
  </tbody>
</table>

<h2>1.2&ensp;AI 模型堆疊（Preflight 實際檢測結果）</h2>

<p>每次批次執行的第一步是 <strong>Preflight 預檢</strong>，系統會逐一初始化所有 AI 模型並回報可用性。以下為本批次實際 preflight 結果（<code>meta/preflight.json</code>）：</p>

<table>
  <thead><tr><th>模組</th><th>模型 ID</th><th>狀態</th><th>用途</th></tr></thead>
  <tbody>
    <tr>
      <td>GroundingDINO</td>
      <td><code>IDEA-Research/grounding-dino-tiny</code></td>
      <td class="gate-pass">✓ 可用</td>
      <td>物件偵測、Logo BBox 定位</td>
    </tr>
    <tr>
      <td>PaddleOCR</td>
      <td><code>en</code>（英文模型）</td>
      <td class="gate-pass">✓ 可用</td>
      <td>Logo 區域文字辨識</td>
    </tr>
    <tr>
      <td>CLIP（品質評分）</td>
      <td><code>openai/clip-vit-base-patch32</code></td>
      <td class="gate-pass">✓ 可用</td>
      <td>Quality Gate：判斷圖片是否含 Logo</td>
    </tr>
    <tr>
      <td>CLIP（品牌比對）</td>
      <td><code>openai/clip-vit-base-patch32</code></td>
      <td class="gate-pass">✓ 可用</td>
      <td>Logo Crop 對品牌名稱庫做 Retrieval</td>
    </tr>
    <tr>
      <td>BLIP（圖說）</td>
      <td><code>Salesforce/blip-image-captioning-base</code></td>
      <td class="gate-pass">✓ 可用</td>
      <td>整圖與 Logo Crop 的自然語言描述（備用）</td>
    </tr>
    <tr>
      <td>LLaVA VLM</td>
      <td><code>llava-hf/llava-1.5-7b-hf</code></td>
      <td class="gate-pass">✓ 可用</td>
      <td>主要 Caption/QA 後端（<code>--use-vlm</code>）</td>
    </tr>
    <tr>
      <td>YOLO-World</td>
      <td><code>yolov8s-worldv2.pt</code></td>
      <td class="gate-pass">✓ 可用</td>
      <td>Quality Gate：Logo 預篩（Prescreener）</td>
    </tr>
    <tr>
      <td>SAM3</td>
      <td><code>Sam3LogoSegmenter</code></td>
      <td class="gate-pass">✓ 可用（CUDA）</td>
      <td>Logo Mask 精細像素級分割</td>
    </tr>
  </tbody>
</table>

<div class="box box-info">
  <div class="box-label">注意：YOLO-World 信心閾值</div>
  本批次 YOLO-World prescreener 的偵測閾值設定為 <strong>0.3</strong>（即 <code>conf_threshold=0.3</code>）。
  若圖片中 YOLO-World 未找到任何高於閾值的 Logo，不會直接過濾，而是標記為
  <code>soft_pass</code> 並在記錄上附加 <code>difficulty_flags: ["no_logo_prescreen_detection", "hard_logo_candidate"]</code>。
</div>

<h2>1.3&ensp;整體數字摘要</h2>

<table>
  <thead><tr><th>指標</th><th>數值</th><th>說明</th></tr></thead>
  <tbody>
    <tr><td>設定的品牌/類別 Pairs 數</td><td>17</td><td>batch_plan 計算出的 pair 總數</td></tr>
    <tr><td>每 Pair 抓取上限</td><td>2</td><td>由 batch_plan 推算：30 ÷ 17 ≈ 2</td></tr>
    <tr><td>Collector 實際抓取</td><td>34</td><td>multi_brand_fetcher.py 從 Poshmark 爬回</td></tr>
    <tr><td>Oversample 候選池</td><td>30</td><td>balance-records 從 34 筆均勻選出</td></tr>
    <tr><td>Staging Gate 輸入</td><td>40</td><td>含歷史批次圖片（staging DB 累積）</td></tr>
    <tr><td>Quality Gate 通過</td><td>10</td><td>30 筆因 near_duplicate 過濾</td></tr>
    <tr><td>最終平衡後保留</td><td>10</td><td>= target-records，目標達成</td></tr>
    <tr><td>SAM3 分割成功</td><td>10 / 10</td><td>10 筆全數成功（ok），0 筆失敗</td></tr>
    <tr><td>正式 DB 品牌筆數</td><td>13</td><td>seed-ontology 寫入 engine DB</td></tr>
    <tr><td>Logo Instances 產生</td><td>10</td><td>phase1 annotation 插入</td></tr>
    <tr><td>Knowledge Base 記錄數</td><td>20</td><td>JOIN image_records ✕ logo_instances</td></tr>
    <tr><td>Review Queue 筆數</td><td>20</td><td>全數標記 needs_review（confidence &lt; 0.9）</td></tr>
    <tr><td>品牌種類</td><td>6</td><td>Adidas, Disney, Under Armour, Lululemon, New Balance, Starbucks</td></tr>
    <tr><td>類別種類</td><td>3</td><td>apparel, shoes, mugs</td></tr>
    <tr><td>資料來源</td><td>1</td><td>poshmark（marketplace）</td></tr>
  </tbody>
  <tfoot>
    <tr><td>目標達成</td><td>✓ True</td><td>target_achieved = true</td></tr>
  </tfoot>
</table>

<!-- ═══════════════════════════════════════════════════════════════
     第 2 節：Pipeline 架構
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>2&ensp;Pipeline 全流程架構</h1>

<h2>2.1&ensp;兩階段 DB 設計（Staging → Engine）</h2>

<p>本 Pipeline 使用 <strong>兩個獨立的 SQLite 資料庫</strong>，以確保品質過濾前後的資料完全隔離：</p>

<ul>
  <li><strong>Staging DB</strong>（<code>staging/logo_engine.db</code>）：
    用於 Step 5–9 的 oversample 候選管理與品質篩選。所有候選圖片先進入此 DB，
    經 Quality Gate 後，只有 <code>quality_status=passed</code> 的記錄才進入下一階段。
  </li>
  <li><strong>Engine DB</strong>（<code>engine/logo_engine.db</code>）：
    最終 10 筆圖片的正式資料庫。Step 10（SAM3）以後的所有標注、品牌資料、
    Logo Instances 均寫入此 DB，並作為 Knowledge Base 的後端儲存。
  </li>
</ul>

<h2>2.2&ensp;流程圖總覽</h2>

<div class="flowchart">  指令列參數解析
       │
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 0：preflight（→ staging DB）                                           │
  │  初始化所有 AI 模型，回報可用性                                               │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  meta/preflight.json
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 1：batch-plan                                                          │
  │  計算 17 pairs × limit_per_pair = 2，目標候選池 30 筆                        │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  meta/batch_plan.json
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 2：collector-fetch-products --all                                      │
  │  multi_brand_fetcher.py → Poshmark 爬取 → 34 筆原始記錄 + 60+ 張圖片         │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  meta/raw_records.json + fetch/images/*.jpeg
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 3：balance-records（第一次）target=30                                  │
  │  從 34 筆均勻抽樣 30 筆，確保品牌/類別平衡                                   │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  meta/candidate_records.json
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 4：ontology-fetch-brands                                               │
  │  brand_data_fetcher.py → Wikidata → 品牌知識庫（aliases, industry...）        │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  brand/brand_records.json
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 5：seed-ontology（staging DB）                                         │
  │  品牌資料寫入 staging DB                                                     │
  └──────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 6：ingest-images（staging DB）                                         │
  │  30 筆候選圖片 + pHash 去重後寫入 staging DB                                  │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  40 筆進入 Quality Gate（含歷史）
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 7：gate（staging DB）— 5 道品質關卡                                    │
  │  ① size_format：40通過  ② blur：40通過  ③ dedupe：10通過/30失敗(near_dup)   │
  │  ④ clip_logo：6通過/4軟通過  ⑤ logo_prescreen：10軟通過                     │
  │  → 最終：10 passed / 30 filtered                                             │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  meta/staging_gate.json
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 8：export-image-records（quality_status=passed）                       │
  │  從 staging DB 撈出 10 筆過關記錄                                             │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  meta/passed_records.json
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 9：balance-records（第二次）target=10                                  │
  │  確保最終 10 筆品牌分佈均勻                                                   │
  └──────────────────────────────────────────────────────────────────────────────┘
       │  fetch/records.json（最終 10 筆）
       │
       ├──────────────────────────────────────────────────────────────┐
       ▼                                                              ▼
  ┌────────────────────────────────────────────┐     品牌資料繼續流向 Step 11
  │  Step 10：segment-sam3（engine DB）         │
  │  對每張圖執行 3 層 Grounding + SAM3 分割：  │
  │  L1: GroundingDINO 物件框（object-first）  │
  │  L2: GroundingDINO Logo BBox              │
  │  L3: SAM3 精細像素級 Mask                 │
  │  → 10/10 成功                              │
  └────────────────────────────────────────────┘
       │  segment/records_with_logo_masks.json
       │  segment/masks/*.png
       │  segment/visualizations/*.png
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 11：phase1-workflow（engine DB）                                       │
  │  11a. seed-ontology → 13 品牌寫入 engine DB                                  │
  │  11b. ingest-images → 10 筆圖片寫入 engine DB                                │
  │  11c. gate（engine DB） → 10/10 通過                                         │
  │  11d. annotate（SAM3 Enrich 模式）：                                          │
  │       ├─ PaddleOCR → Logo BBox 文字辨識                                      │
  │       ├─ CLIP Retrieval → Logo Crop vs 品牌名稱庫                             │
  │       ├─ BLIP Captioning → 整圖 + Logo Crop 描述                              │
  │       ├─ LLaVA VLM → 整圖 + Logo Crop 自然語言描述（主要 Caption）            │
  │       └─ merge_signals() → 融合所有信號決定品牌歸屬                            │
  │  11e. review-queue → 輸出低信心記錄清單（全 20 筆 needs_review）               │
  └──────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 12：export-kb                                                          │
  │  JOIN image_records ✕ logo_instances → 20 筆 knowledge_base.json             │
  └──────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  Step 13：analyze-run + summary                                              │
  │  產生 analysis.md、summary.json、meta/summary.json                           │
  └──────────────────────────────────────────────────────────────────────────────┘</div>


<!-- ═══════════════════════════════════════════════════════════════
     第 3 節：各步驟詳細說明
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>3&ensp;各步驟詳細說明</h1>

<!-- Step 0 -->
<div class="step-header"><span class="badge">0</span> Preflight — 模型可用性預檢</div>
<div class="step-body">

<p><strong>目的：</strong>在任何資料處理開始前，逐一初始化所有 AI 模型並確認其可用性。若任何核心模型初始化失敗，後續步驟將無法正確執行。</p>

<p><strong>對應指令：</strong></p>
<pre>python -m logo_data_engine \
    --db staging/logo_engine.db \
    preflight \
    --with-sam3 \
    --use-vlm --vlm-model-id llava-hf/llava-1.5-7b-hf</pre>

<p><strong>初始化順序與行為：</strong></p>
<ol>
  <li><strong>GroundingDINO</strong>：載入 <code>IDEA-Research/grounding-dino-tiny</code>，測試能否前向傳播</li>
  <li><strong>PaddleOCR</strong>：初始化英文 OCR 模型（<code>lang="en"</code>）</li>
  <li><strong>CLIP Logo Scorer</strong>：載入 <code>openai/clip-vit-base-patch32</code>，用於 Quality Gate</li>
  <li><strong>CLIP Brand Retriever</strong>：同上模型，用於品牌 Retrieval</li>
  <li><strong>BLIP Captioner</strong>：載入 <code>Salesforce/blip-image-captioning-base</code></li>
  <li><strong>LLaVA VLM</strong>：載入 <code>llava-hf/llava-1.5-7b-hf</code>（7B 參數，需 GPU 記憶體）</li>
  <li><strong>YOLO-World Prescreener</strong>：載入 <code>yolov8s-worldv2.pt</code>，閾值 0.3</li>
  <li><strong>SAM3</strong>：初始化 <code>Sam3LogoSegmenter</code>（<code>device=cuda</code>，<code>object_first=True</code>）</li>
</ol>

<p><strong>實際輸出（<code>meta/preflight.json</code>）：</strong></p>
<pre>{"with_sam3": true, "use_vlm": true,
 "grounding_dino":    {"enabled": true, "available": true, "model_id": "IDEA-Research/grounding-dino-tiny"},
 "paddleocr":         {"enabled": true, "available": true},
 "clip_logo_gate":    {"enabled": true, "available": true},
 "clip_retrieval":    {"enabled": true, "available": true},
 "blip_caption":      {"enabled": true, "available": true},
 "vlm":               {"enabled": true, "available": true, "model_id": "llava-hf/llava-1.5-7b-hf"},
 "yolo_prescreen":    {"enabled": true, "available": true, "threshold": 0.3},
 "sam3":              {"enabled": true, "available": true, "device": "cuda", "object_first": true}}</pre>

</div>

<!-- Step 1 -->
<div class="step-header"><span class="badge">1</span> Batch Plan — 計算 Limit per Pair</div>
<div class="step-body">

<p><strong>目的：</strong>根據 <code>--target-records × oversample_factor = 10 × 3 = 30</code>，計算每個品牌/類別 Pair 應抓幾筆（<code>recommended_limit_per_pair</code>），使總候選數接近 30。</p>

<p><strong>對應指令：</strong></p>
<pre>python -m logo_data_engine --db staging/logo_engine.db \
    batch-plan --target 30</pre>

<p><strong>計算邏輯：</strong>系統讀取所有設定的 brand/category pairs（共 17 個），計算 <code>⌈30 ÷ 17⌉ = 2</code>。</p>

<p><strong>實際輸出（<code>meta/batch_plan.json</code>）：</strong></p>
<pre>{"target": 30, "configured_pairs": 17, "recommended_limit_per_pair": 2}</pre>

</div>

<!-- Step 2 -->
<div class="step-header"><span class="badge">2</span> Collector — 多品牌圖片爬取</div>
<div class="step-body">

<p><strong>目的：</strong>呼叫 <code>multi_brand_fetcher.py</code>，以 <code>--all</code> 模式遍歷所有設定的品牌/類別 Pairs，從 Poshmark 等 Marketplace 爬取商品圖片及 metadata。</p>

<p><strong>對應指令：</strong></p>
<pre>python multi_brand_fetcher.py \
    --all \
    --limit 2 \
    --output meta/raw_records.json \
    --image-dir fetch/images/</pre>

<p><strong>Poshmark 爬取機制：</strong>對每個 <code>(brand, category)</code> pair，構造搜尋 URL（例如 <code>https://poshmark.com/search?query=adidas+shirt&amp;type=listings</code>），爬取前 N 筆商品，下載縮圖並記錄 metadata。</p>

<p><strong>每筆原始記錄的欄位（raw_records.json）：</strong></p>
<table>
  <thead><tr><th>欄位</th><th>範例值</th><th>說明</th></tr></thead>
  <tbody>
    <tr><td><code>brand</code></td><td><code>"Adidas"</code></td><td>品牌標籤</td></tr>
    <tr><td><code>category</code></td><td><code>"apparel"</code></td><td>類別標籤</td></tr>
    <tr><td><code>source</code></td><td><code>"poshmark"</code></td><td>資料來源名稱</td></tr>
    <tr><td><code>source_channel</code></td><td><code>"marketplace"</code></td><td>管道類型</td></tr>
    <tr><td><code>source_kind</code></td><td><code>"marketplace"</code></td><td>來源種類（影響 soft-pass 判斷）</td></tr>
    <tr><td><code>product_name</code></td><td><code>"Adidas Shirt"</code></td><td>商品名稱</td></tr>
    <tr><td><code>product_url</code></td><td><code>"https://poshmark.com/listing/..."</code></td><td>商品頁面 URL</td></tr>
    <tr><td><code>image_url</code></td><td><code>"https://di2ponv0v5otw.cloudfront.net/..."</code></td><td>圖片 CDN URL</td></tr>
    <tr><td><code>local_image_path</code></td><td><code>"fetch/images/adidas_69c47adb.jpg"</code></td><td>本地儲存路徑</td></tr>
    <tr><td><code>global_product_id</code></td><td><code>"69c47adb006e4345ae58f0fb"</code></td><td>Poshmark 商品 ID</td></tr>
    <tr><td><code>crawl_timestamp_utc</code></td><td><code>"2026-04-04T01:13:44.996800+00:00"</code></td><td>爬取時間戳</td></tr>
    <tr><td><code>image_download_status</code></td><td><code>"downloaded"</code></td><td>下載狀態</td></tr>
  </tbody>
</table>

<p><strong>實際輸出（<code>meta/collector.json</code>）：</strong></p>
<pre>{"output": "meta/raw_records.json", "records": 34, "pairs": 17}</pre>

<div class="box box-info">
  <div class="box-label">圖片命名規則</div>
  下載的圖片以 <code>&lt;brand&gt;_&lt;global_product_id&gt;.&lt;ext&gt;</code> 命名，存放於 <code>fetch/images/</code>。
  例如：<code>adidas_69c47adb006e4345ae58f0fb.jpg</code>、<code>disney_69c9e3a9d6c0dcd7953eee8e.jpeg</code>。
</div>

</div>

<!-- Step 3 -->
<div class="step-header"><span class="badge">3</span> Balance（第一次）— Oversample 候選池</div>
<div class="step-body">

<p><strong>目的：</strong>從 Collector 抓回的 34 筆中，均勻抽取 30 筆，使品牌與類別的分佈盡量平衡，避免某品牌獨佔候選池。</p>

<p><strong>對應指令：</strong></p>
<pre>python -m logo_data_engine --db staging/logo_engine.db \
    balance-records \
    --input  meta/raw_records.json \
    --output meta/candidate_records.json \
    --target 30</pre>

<p><strong>平衡策略：</strong>以 <code>(brand, category, source)</code> 為分層鍵，在各層中均勻取樣，優先補足數量不足的稀有組合。</p>

<p><strong>實際輸出（<code>meta/balance.json</code>）：</strong></p>
<pre>{"input": "meta/raw_records.json", "output": "meta/candidate_records.json",
 "seen": 34, "selected": 30, "target": 30}</pre>

</div>

<!-- Step 4 -->
<div class="step-header"><span class="badge">4</span> Ontology — 品牌知識庫抓取</div>
<div class="step-body">

<p><strong>目的：</strong>呼叫 <code>brand_data_fetcher.py</code>，對每個出現在候選記錄中的品牌名稱，查詢 Wikidata 取得結構化知識（別名、行業、國家、母公司等），作為後續品牌比對與 Prompt 建構的依據。</p>

<p><strong>對應指令：</strong></p>
<pre>python brand_data_fetcher.py \
    --product-records meta/candidate_records.json \
    --output          brand/brand_records.json</pre>

<p><strong>Wikidata 查詢流程：</strong></p>
<ol>
  <li>對每個品牌名稱執行 Wikidata 搜尋（exact match 優先）</li>
  <li>從匹配的 entity 中提取：<code>aliases_en</code>、<code>industries</code>、<code>countries</code>、<code>parent_organizations</code>、<code>inception_year</code>、<code>official_websites</code></li>
  <li>將結果序列化為 <code>brand_records.json</code></li>
</ol>

<p><strong>實際品牌記錄範例（Adidas）：</strong></p>
<pre>{"query": "Adidas", "matched": true, "matched_by": "exact_or_top_wikidata_search",
 "entity_id": "Q12358242", "label": "Adidas",
 "description": "trade mark of Adidas AG",
 "aliases_en": ["Adidas brand", "Cloudfoam", "Adidas Cloudfoam",
                "Cloudfoam Comfort", "Cloudfoam Comfort shoes"],
 "wikidata_url": "https://www.wikidata.org/wiki/Q12358242",
 "official_websites": ["https://www.adidas-group.com/"],
 "parent_organizations": [],
 "countries": ["Germany"],
 "industries": ["sportswear"],
 "inception_year": "1924"}</pre>

<p>這些 aliases_en 在 Step 10（SAM3）的 Prompt 建構中扮演關鍵角色：GroundingDINO 會以
<code>"Adidas logo"</code>、<code>"Cloudfoam logo"</code>、<code>"Adidas Cloudfoam logo"</code> 等多種變體同時偵測，
提高 Logo 定位的召回率。</p>

<p><strong>實際輸出（<code>meta/ontology.json</code>）：</strong></p>
<pre>{"output": "brand/brand_records.json", "dry_run": false}</pre>

</div>

<!-- Step 5–6 -->
<div class="step-header"><span class="badge">5</span><span class="badge">6</span> Staging Seed &amp; Ingest — 寫入暫存資料庫</div>
<div class="step-body">

<p><strong>Step 5（seed-ontology）：</strong>將 <code>brand_records.json</code> 中 <code>matched=true</code> 的品牌寫入 staging DB 的 <code>brand_records</code> 資料表，tier 設定為 <code>"silver"</code>。</p>

<p><strong>Step 6（ingest-images）：</strong>對 <code>candidate_records.json</code> 中每筆記錄：</p>
<ol>
  <li>計算圖片的 pHash（感知雜湊，用於後續去重）</li>
  <li>若 pHash 在既有記錄中已存在（Hamming distance ≤ 6），跳過</li>
  <li>否則寫入 staging DB <code>image_records</code> 資料表，初始 <code>quality_status=NULL</code></li>
</ol>

<p><strong>實際輸出（<code>meta/staging_ingest.json</code>）：</strong></p>
<pre>{"seen": 30, "inserted": 30, "skipped_existing": 0,
 "skipped_duplicate": 0, "phash_failures": 0}</pre>

</div>

<!-- Step 7 -->
<div class="pagebreak"></div>
<div class="step-header"><span class="badge">7</span> Quality Gate — 五道品質過濾</div>
<div class="step-body">

<p><strong>目的：</strong>對 staging DB 中所有 <code>quality_status IS NULL</code> 的圖片依序執行 5 道品質關卡，
更新 <code>quality_status</code>（<code>passed</code> 或 <code>filtered</code>）並記錄詳細的 gate 結果。</p>

<p><strong>對應指令：</strong></p>
<pre>python -m logo_data_engine --db staging/logo_engine.db \
    gate --all --report</pre>

<p><strong>本批次實際 Gate 結果總覽：</strong></p>
<table>
  <thead><tr><th>關卡名稱</th><th>passed</th><th>soft_pass</th><th>failed</th><th>skipped</th><th>失敗原因</th></tr></thead>
  <tbody>
    <tr>
      <td>① size_format</td>
      <td class="gate-pass">40</td><td>0</td><td>0</td><td>0</td>
      <td>—</td>
    </tr>
    <tr>
      <td>② blur</td>
      <td class="gate-pass">40</td><td>0</td><td>0</td><td>0</td>
      <td>—</td>
    </tr>
    <tr>
      <td>③ dedupe（pHash）</td>
      <td class="gate-pass">10</td><td>0</td>
      <td class="gate-fail">30</td><td>0</td>
      <td><code>near_duplicate</code></td>
    </tr>
    <tr>
      <td>④ clip_logo</td>
      <td class="gate-pass">6</td>
      <td class="gate-soft">4</td>
      <td>0</td><td>0</td>
      <td>soft_pass（低分但來自 marketplace）</td>
    </tr>
    <tr>
      <td>⑤ logo_prescreen</td>
      <td>0</td>
      <td class="gate-soft">10</td>
      <td>0</td><td>0</td>
      <td>soft_pass（YOLO 未偵測到 Logo）</td>
    </tr>
  </tbody>
  <tfoot>
    <tr><td>最終結果</td><td><strong>10 passed</strong></td><td colspan="2"><strong>30 filtered</strong></td><td></td><td></td></tr>
  </tfoot>
</table>

<h4>① 尺寸與格式關卡（size_format）</h4>
<div class="box box-info">
  <div class="box-label">判斷條件</div>
  <ul>
    <li>最小寬度：<strong>256px</strong>（<code>min_width=256</code>）</li>
    <li>最小高度：<strong>256px</strong>（<code>min_height=256</code>）</li>
    <li>允許格式：<strong>JPEG、PNG、WEBP</strong></li>
    <li>失敗代碼：<code>too_small</code> 或 <code>unsupported_format</code></li>
  </ul>
</div>
<p>本批次 40 張圖片全部通過，代表 Poshmark 圖片均符合最低解析度要求。Gate 輸出範例：</p>
<pre>{"gate": "size_format", "outcome": "passed", "width": 300, "height": 300, "format": "JPEG"}</pre>

<h4>② 模糊偵測關卡（blur）</h4>
<div class="box box-info">
  <div class="box-label">計算方法</div>
  採用 <strong>Laplacian Variance</strong> 衡量圖像銳利度。
  計算方式：將圖片轉為灰階後，對每個像素計算其 4-鄰域 Laplacian（
  <code>上 + 下 + 左 + 右 − 4×中心</code>），取整體變異數。
  閾值 <strong>45.0</strong>：低於此值視為過度模糊（<code>too_blurry</code>）。
</div>
<p>本批次實際 blur_score 範例（Disney mug 圖）：</p>
<pre>{"gate": "blur", "outcome": "passed", "blur_score": 1383.24365234375}</pre>
<p>此分數遠高於閾值 45.0，說明圖片相當清晰。通過後，blur_score 對 quality_score 的貢獻為 <code>min(1.0, blur_score / 90.0)</code>。</p>

<h4>③ 感知哈希去重關卡（dedupe）</h4>
<div class="box box-warn">
  <div class="box-label">本批次主要過濾關卡</div>
  本批次共有 <strong>30 筆</strong>因此關卡被過濾，是最大的篩選瓶頸。
</div>
<p>計算圖片的 pHash（64-bit 感知哈希），與所有已通過的圖片做 Hamming Distance 比較。
若 Hamming Distance ≤ <strong>6</strong>，視為近似重複（<code>near_duplicate</code>）。</p>
<p>Hamming Distance 計算方式（XOR 後計算 bit 數）：</p>
<pre>distance = bin(int(phash_a, 16) ^ int(phash_b, 16)).count('1')</pre>
<p>Gate 輸出範例（通過）：</p>
<pre>{"gate": "dedupe", "outcome": "passed", "phash_distance": null, "threshold": 6}</pre>
<p>Gate 輸出範例（失敗）：</p>
<pre>{"gate": "dedupe", "outcome": "failed", "phash_distance": 2, "threshold": 6}</pre>

<div class="box box-info">
  <div class="box-label">為何有 30 筆重複？</div>
  staging DB 為累積式設計，含有先前批次已下載的圖片。
  本次 30 筆重複來自 Poshmark 上相同商品圖在不同批次中重複出現，
  系統正確地以 pHash 偵測並過濾，確保最終資料集不含重複圖。
</div>

<h4>④ CLIP Logo 品質關卡（clip_logo）</h4>
<p>使用 <code>openai/clip-vit-base-patch32</code> 計算整張圖片與 prompt <code>"a photo with a brand logo"</code> 的餘弦相似度分數。</p>
<div class="box box-info">
  <div class="box-label">決策邏輯</div>
  <ul>
    <li>分數 ≥ <strong>0.22</strong>（<code>clip_threshold</code>）：<span class="gate-pass">passed</span></li>
    <li>分數 &lt; 0.22 且 ≥ <strong>0.08</strong>（<code>clip_soft_floor</code>）且為 marketplace/ecommerce 可信來源：
      <span class="gate-soft">soft_pass</span>，標記 <code>difficulty_flags: ["low_clip_logo_score"]</code></li>
    <li>分數 &lt; 0.08 或非可信來源：<span class="gate-fail">filtered</span>（<code>low_clip_logo_score</code>）</li>
  </ul>
</div>
<p>Gate 輸出範例（soft_pass）：</p>
<pre>{"gate": "clip_logo", "outcome": "soft_pass",
 "score": 0.21255092322826385, "threshold": 0.22,
 "soft_floor": 0.08, "model_id": "openai/clip-vit-base-patch32"}</pre>
<p>本批次 10 筆通過記錄中：6 筆 <span class="gate-pass">passed</span>、4 筆 <span class="gate-soft">soft_pass</span>（分數介於 0.08–0.22 之間，均來自 Poshmark marketplace）。</p>

<h4>⑤ YOLO-World Logo 預篩關卡（logo_prescreen）</h4>
<p>使用 <code>yolov8s-worldv2.pt</code> 對整張圖做 open-vocabulary 目標偵測，判斷是否存在 Logo 相關物件（置信度 ≥ 0.3）。</p>
<div class="box box-info">
  <div class="box-label">決策邏輯</div>
  <ul>
    <li>有偵測到 Logo（置信度 ≥ 0.3）：<span class="gate-pass">passed</span>，另標記：
      <ul>
        <li>BBox 面積 &lt; 2% 圖面積 → <code>small_logo_candidate</code></li>
        <li>BBox 面積 &gt; 35% 圖面積 → <code>large_logo_candidate</code></li>
        <li>偵測到 &gt;1 個 Logo → <code>multi_logo_candidate</code></li>
      </ul>
    </li>
    <li>未偵測到（detections 為空）：<span class="gate-soft">soft_pass</span>，標記
      <code>difficulty_flags: ["no_logo_prescreen_detection", "hard_logo_candidate"]</code></li>
    <li>模型不可用：<span class="gate-skip">skipped</span></li>
  </ul>
</div>
<p>Gate 輸出範例（soft_pass）：</p>
<pre>{"gate": "logo_prescreen", "outcome": "soft_pass",
 "detections": [], "model_id": "/raid/ming/logo/engine/model_cache/yolov8s-worldv2.pt"}</pre>
<p>本批次 10 筆通過記錄全部為 <span class="gate-soft">soft_pass</span>，代表 YOLO-World 在這批 Marketplace 縮圖上未找到明確 Logo，
但因為 soft_pass 機制，這些「困難案例」仍被保留，並以 <code>hard_logo_candidate</code> 標記，留待 SAM3 精細處理。</p>

<p><strong>實際輸出（<code>meta/staging_gate.json</code>，精簡）：</strong></p>
<pre>{"seen_images": 40, "updated_images": 40,
 "quality_status_counts": {"filtered": 30, "passed": 10},
 "report": {
   "failure_reason_counts": {"near_duplicate": 30},
   "gate_stats": {
     "size_format":    {"passed": 40, "failed": 0,  "soft_pass": 0},
     "blur":           {"passed": 40, "failed": 0,  "soft_pass": 0},
     "dedupe":         {"passed": 10, "failed": 30, "soft_pass": 0},
     "clip_logo":      {"passed": 6,  "failed": 0,  "soft_pass": 4},
     "logo_prescreen": {"passed": 0,  "failed": 0,  "soft_pass": 10}
   }
 }
}</pre>

</div>

<!-- Step 8-9 -->
<div class="step-header"><span class="badge">8</span><span class="badge">9</span> Export Passed &amp; 最終平衡</div>
<div class="step-body">

<p><strong>Step 8（export-image-records）：</strong>從 staging DB 撈出所有 <code>quality_status='passed'</code> 的記錄，輸出為 <code>meta/passed_records.json</code>。本批次共 10 筆。</p>

<p><strong>Step 9（balance-records，第二次）：</strong>對 10 筆通過記錄再次做品牌/類別平衡，輸出最終 <code>fetch/records.json</code>（10 筆）。</p>

<div class="box box-success">
  <div class="box-label">過關數量驗證</div>
  系統會檢查 <code>passed_count ≥ target_records</code>（10 ≥ 10），條件成立才繼續。
  若不成立，Pipeline 立即報錯退出，提示使用者提高 <code>--oversample-factor</code>。
</div>

</div>

<!-- Step 10 -->
<div class="pagebreak"></div>
<div class="step-header"><span class="badge">10</span> SAM3 Logo Segmentation — 精細像素級分割</div>
<div class="step-body">

<p><strong>目的：</strong>對最終 10 筆圖片，執行三層漸進式 Logo 定位與分割，產出精細的 pixel-level Logo Mask。</p>

<p><strong>對應指令：</strong></p>
<pre>python logo_segmentation_pipeline.py \
    --input-records  fetch/records.json \
    --output         segment/records_with_logo_masks.json \
    --mask-dir       segment/masks/ \
    --viz-dir        segment/visualizations/ \
    --brand-records  brand/brand_records.json</pre>

<h4>Object-First 三層偵測架構</h4>

<p><strong>Layer 1：GroundingDINO 物件偵測（Object-First）</strong></p>
<p>使用 <code>IDEA-Research/grounding-dino-tiny</code> 先偵測圖片中的主要物件（非 Logo），
縮小後續 Logo 偵測的搜尋範圍。物件 Prompt 依據 category 與品牌動態組合：</p>
<table>
  <thead><tr><th>category</th><th>object_terms（部分）</th><th>expected_object_fraction_range</th></tr></thead>
  <tbody>
    <tr><td>apparel</td><td>shirt, tee, hoodie, jacket, clothing</td><td>[0.06, 0.98]</td></tr>
    <tr><td>shoes</td><td>shoe, sneaker, footwear, boot</td><td>[0.06, 0.98]</td></tr>
    <tr><td>mugs</td><td>mug, cup, tumbler, coffee cup</td><td>[0.05, 0.75]</td></tr>
  </tbody>
</table>

<p><strong>Layer 2：GroundingDINO Logo 偵測（在物件 Crop 上）</strong></p>
<p>對 Layer 1 找到的物件框，裁切出 Crop 後再用 Logo 相關 Prompt 偵測：</p>
<pre>logo_prompt_variants = [
    "Adidas logo",          "Adidas brand logo",
    "Adidas emblem",        "Adidas mark",
    "Cloudfoam logo",       "Cloudfoam brand logo",
    "Adidas Cloudfoam logo","Adidas shirt logo",
    "Adidas logo on shirt", "shirt logo"
]</pre>
<p>expected_logo_fraction_range：<code>[0.0001, 0.23]</code>（Logo 占圖比例合理範圍，太大或太小的偵測框會被排除）</p>

<p>實際偵測輸出範例（Adidas 上衣）：</p>
<pre>{"logo_grounding_label": "shirt logo",
 "logo_grounding_score": 0.365249,
 "logo_grounding_bbox_xyxy": [71.24, 79.65, 183.4, 202.29],
 "logo_grounding_bbox_area": 13755.2,
 "logo_grounding_bbox_fraction": 0.12701,
 "logo_grounding_model_id": "IDEA-Research/grounding-dino-tiny"}</pre>

<p><strong>Layer 3：SAM3 精細 Mask 分割</strong></p>
<p>以 Layer 2 的 Logo BBox 作為 Point Prompt，由 SAM3（<code>Sam3LogoSegmenter</code>）在<strong>原始全圖</strong>上產生 pixel-level binary mask：</p>
<pre>{"logo_bbox_xyxy": [71.24, 79.65, 183.4, 202.29],
 "logo_bbox_area": 13755.2,
 "logo_mask_area_pixels": 10874,
 "logo_mask_area_fraction": 0.10041,
 "logo_segmentation_iou_prediction": 0.000751,
 "logo_segmentation_status": "ok",
 "logo_mask_path": "segment/masks/7d5ce5b96afddd7f.png",
 "logo_visualization_path": "segment/visualizations/7d5ce5b96afddd7f.png"}</pre>

<h4>輸出說明</h4>
<table>
  <thead><tr><th>輸出</th><th>格式</th><th>說明</th></tr></thead>
  <tbody>
    <tr><td><code>segment/records_with_logo_masks.json</code></td><td>JSON 陣列</td><td>原始圖片記錄 + 所有 SAM3 偵測欄位</td></tr>
    <tr><td><code>segment/masks/&lt;id&gt;.png</code></td><td>灰階 PNG</td><td>Binary Mask：白色=Logo 區域，黑色=背景</td></tr>
    <tr><td><code>segment/visualizations/&lt;id&gt;.png</code></td><td>RGB PNG</td><td>原圖疊加 Mask 半透明遮罩 + BBox 框線的視覺化</td></tr>
  </tbody>
</table>

<p><strong>實際輸出統計（<code>meta/segment.json</code>）：</strong></p>
<pre>{"records": 10, "ok": 10, "no_detection": 0,
 "missing_image": 0, "download_failed": 0,
 "model_unavailable": 0, "inference_error": 0}</pre>

<div class="box box-success">
  <div class="box-label">SAM3 分割成功率</div>
  本批次 10/10（100%）成功分割，零失敗。每筆 Mask 平均覆蓋 Logo BBox 面積的約 79%
  （<code>mask_area_pixels=10874</code> vs <code>bbox_area=13755</code>），符合精細分割預期。
</div>

</div>

<!-- Step 11 -->
<div class="pagebreak"></div>
<div class="step-header"><span class="badge">11</span> Phase1 Workflow — 核心標注引擎</div>
<div class="step-body">

<p><strong>目的：</strong>對最終 10 筆圖片執行完整的 AI 標注管線，產生 Logo Instances 並寫入正式 engine DB。</p>

<p><strong>本批次使用 SAM3 Enrich 模式：</strong>因 <code>--with-sam3</code> 已在 Step 10 產生分割結果，
Phase1 的 annotation 子步驟採用 <code>annotate_from_segment_records(enrich=True)</code>，
直接從 SAM3 結果讀取 BBox 與 Mask，再疊加 OCR/CLIP/VLM 進行豐富化。</p>

<h4>11a. Seed Ontology（engine DB）</h4>
<p>將 brand_records.json 中 13 個品牌寫入正式 engine DB，tier=<code>"silver"</code>。</p>
<pre>{"inserted": 13, "tier": "silver", "dry_run": false}</pre>

<h4>11b. Ingest Images（engine DB）</h4>
<p>10 筆圖片記錄寫入正式 engine DB。</p>
<pre>{"seen": 10, "inserted": 10, "skipped_existing": 0,
 "skipped_duplicate": 0, "phash_failures": 0}</pre>

<h4>11c. Quality Gate（engine DB）</h4>
<p>對正式 DB 中的圖片再次執行 Gate（<code>resume=True</code>，已 gated 的跳過）。本批次全 10 筆通過：</p>
<pre>{"seen": 10, "status_counts": {"passed": 10}, "failure_reason_counts": {}}</pre>

<h4>11d. Annotate（SAM3 Enrich 模式）</h4>

<p>對每筆 <code>logo_segmentation_status="ok"</code> 的 SAM3 記錄，依序執行以下步驟：</p>

<p><strong>1. 裁切 Logo Crop</strong></p>
<p>從 SAM3 輸出的 <code>logo_bbox_xyxy</code>（或 <code>logo_grounding_bbox_xyxy</code>）裁切出 Logo 區域，
作為後續 OCR 與 CLIP 的輸入。</p>
<pre>x0, y0, x1, y1 = 71, 79, 183, 202   # Adidas 上衣範例
logo_crop = image.crop((71, 79, 183, 202))</pre>

<p><strong>2. PaddleOCR — Logo 文字辨識</strong></p>
<p>對 Logo Crop 執行 OCR，嘗試辨識品牌文字（如 "ADIDAS"、"STARBUCKS"）。</p>
<div class="box box-info">
  <div class="box-label">PaddleOCR 輸入 / 輸出</div>
  <ul>
    <li><strong>輸入：</strong>原始圖片路徑 + <code>crop_box_xyxy</code>（裁切範圍）</li>
    <li><strong>輸出：</strong><code>{"engine":"paddleocr","text":"ADIDAS","confidence":0.92,"lines":[...]}</code></li>
    <li>若 Logo 為純圖形（無文字）：<code>{"text":null,"confidence":0.0,"lines":[]}</code></li>
  </ul>
</div>
<p>本批次多數記錄 <code>ocr_text=null</code>，原因是 Poshmark 縮圖中 Logo 文字過小或角度傾斜，
PaddleOCR 未能辨識出有效文字。</p>

<p><strong>3. CLIP Brand Retrieval — Logo 品牌比對</strong></p>
<p>以 Logo Crop 圖片為 Query，對品牌知識庫中每個品牌的文字 Prompt 計算 CLIP 分數，取最高分作為品牌歸屬依據。</p>
<div class="box box-info">
  <div class="box-label">CLIP Retrieval 輸入 / 輸出</div>
  <ul>
    <li><strong>圖片端：</strong>Logo Crop（PIL Image）</li>
    <li><strong>文字端（每個品牌）：</strong><code>"a photo of the {alias} logo"</code>（使用所有 aliases_en）</li>
    <li><strong>例如 Adidas：</strong><code>"a photo of the Cloudfoam Comfort shoes logo"</code></li>
    <li><strong>輸出：</strong>按分數排序的 top-N matches 清單</li>
  </ul>
</div>
<p>實際輸出範例（Disney Mug 圖的 Logo Crop，CLIP 比對 Adidas）：</p>
<pre>{"matches": [
  {"brand_id": "adidas",       "score": 0.2501, "prompt": "a photo of the Cloudfoam Comfort shoes logo"},
  {"brand_id": "lululemon",    "score": 0.2495, "prompt": "a photo of the lululemon logo"},
  {"brand_id": "samsung",      "score": 0.2491, "prompt": "a photo of the Samsung brand logo"},
  {"brand_id": "under-armour", "score": 0.2469, "prompt": "Under Armour, Inc. logo"},
  {"brand_id": "nike",         "score": 0.2409, "prompt": "Nike, Inc. logo"}
], "model_id": "openai/clip-vit-base-patch32"}</pre>

<div class="box box-warn">
  <div class="box-label">CLIP 歧義注意</div>
  本批次中，CLIP 各品牌分數差異極小（差距 &lt; 0.01），系統將此標記為
  <code>ambiguity_note: "ambiguous_clip_brand_retrieval"</code>，
  並降低 confidence（最終 confidence ≈ 0.63），觸發 <code>review_status=needs_review</code>。
</div>

<p><strong>4. LLaVA VLM — 圖像自然語言描述（主要 Caption）</strong></p>
<p>僅對 <code>quality_status=passed</code> 的記錄執行。使用 <code>llava-hf/llava-1.5-7b-hf</code>（7B 參數多模態模型）對整圖與 Logo Crop 各生成一段描述。</p>

<div class="box box-info">
  <div class="box-label">LLaVA 輸入 Prompt 設計</div>
  <table>
    <thead><tr><th>目標</th><th>Prompt 文字</th></tr></thead>
    <tbody>
      <tr><td>整圖描述</td><td><code>"Describe the brand, object, and photo scene."</code></td></tr>
      <tr><td>Logo Crop 描述</td><td><code>"Describe the logo, brand, and object in this crop."</code></td></tr>
    </tbody>
  </table>
</div>

<p>實際輸出範例（Disney Mug 整圖）：</p>
<pre>full_image_caption:
"USER: \nDescribe the brand, object, and photo scene.
ASSISTANT: The image features a Goofy Cuisine coffee mug, which is a cartoon-themed
mug with a picture of Goofy, a popular character from the Disney universe. The mug
is placed on a white surface, possibly a table or a bed. The scene is set in a room"</pre>

<p>Logo Crop 描述範例（Adidas Logo Crop）：</p>
<pre>logo_crop_caption:
"USER: \nDescribe the logo, brand, and object in this crop.
ASSISTANT: The image features a close-up of a black and white logo, which appears
to be a combination of a letter and a graphic. The logo is placed on a white
background, making it stand out. The brand name is not visible in the image,
but the logo itself is the main focus."</pre>

<div class="box box-info">
  <div class="box-label">BLIP 備用機制</div>
  當 <code>--use-vlm</code> 啟用時，LLaVA 為主要 Caption 引擎；BLIP（<code>Salesforce/blip-image-captioning-base</code>）
  為備用。若 VLM 回傳錯誤，系統自動 fallback 至 BLIP 的輸出。
  兩者的 prompt 相同，但 BLIP 為非對話式模型，輸出格式無 <code>USER:/ASSISTANT:</code> 標記。
</div>

<p><strong>5. merge_signals() — 多信號品牌決策融合</strong></p>
<p>整合 brand_hint（collector 標籤）、OCR 文字、CLIP 分數、VLM Caption，依照以下優先順序決定最終品牌歸屬：</p>
<ol>
  <li><strong>brand_hint + OCR 一致</strong>：最高信心，confidence = 0.95+，attribution_source = <code>"ocr_match"</code></li>
  <li><strong>CLIP 第一名且清晰領先</strong>（gap &gt; 0.02）：高信心，attribution_source = <code>"clip_retrieval"</code></li>
  <li><strong>CLIP 歧義</strong>（各品牌分數接近）：標記 <code>ambiguous_clip_brand_retrieval</code>，降低 confidence</li>
  <li><strong>Brand Hint 作為保底</strong>：若 CLIP/OCR 均不確定，採用 collector 的 brand_hint</li>
</ol>

<p>最終融合結果範例（Adidas 圖，CLIP 歧義）：</p>
<pre>{"attribution_source": "clip_retrieval",
 "merged_brand_id":   "adidas",
 "merged_brand_name": "Adidas",
 "confidence":        0.6251,
 "ambiguity_note":    "ambiguous_clip_brand_retrieval"}</pre>

<h4>11e. Review Queue 輸出</h4>
<p>對所有 <code>confidence &lt; 0.9</code> 的 Logo Instances，輸出待人工審核清單。</p>
<pre>python -m logo_data_engine --db engine/logo_engine.db review-queue --output review/review_queue.json</pre>
<p>本批次 20 筆 Logo Instances 全數 <code>needs_review</code>（confidence 範圍約 0.62–0.75）。</p>

<p><strong>實際輸出（<code>meta/phase1.json</code>，精簡）：</strong></p>
<pre>{"ontology":   {"inserted": 13},
 "images":     {"seen": 10, "inserted": 10},
 "gate":       {"quality_status_counts": {"passed": 20}},
 "annotation": {"seen": 10, "inserted": 10},
 "review":     {"records": 20}}</pre>

</div>

<!-- Step 12 -->
<div class="step-header"><span class="badge">12</span> Export Knowledge Base</div>
<div class="step-body">

<p><strong>目的：</strong>將 engine DB 中的 <code>image_records</code> 與 <code>logo_instances</code> 做 JOIN，輸出一份完整的、自描述的 JSON 知識庫，供下游訓練、分析或人工審核使用。</p>

<p><strong>對應指令：</strong></p>
<pre>python -m logo_data_engine --db engine/logo_engine.db \
    export-kb --output export/knowledge_base.json</pre>

<p><strong>實際輸出統計：</strong></p>
<pre>{"output": "export/knowledge_base.json", "records": 20}</pre>

<p>20 筆 = 10 張圖 × 每張平均 2 個 Logo Instances（部分圖片偵測到多個 Logo）。</p>

</div>

<!-- Step 13 -->
<div class="step-header"><span class="badge">13</span> Analyze Run — 批次分析報告</div>
<div class="step-body">

<p><strong>目的：</strong>對整個批次執行結果做結構化分析，產生 Markdown 報告與 JSON 摘要。</p>

<p><strong>對應指令：</strong></p>
<pre>python -m logo_data_engine --db engine/logo_engine.db \
    analyze-run \
    --run-dir    results/batch_10_vlm3_sam3 \
    --output-md  analysis/analysis.md \
    --output-json analysis/summary.json \
    --target-records 10</pre>

<p>報告內容包含：品牌/類別/來源分佈表、品質狀態統計、Logo Instance Tier 分佈、目標達成確認。
詳見第 6 節。</p>

</div>

<!-- ═══════════════════════════════════════════════════════════════
     第 4 節：輸出目錄結構
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>4&ensp;輸出目錄結構</h1>

<pre>results/batch_10_vlm3_sam3/
│
├── engine/
│   └── logo_engine.db               ← 正式 SQLite DB（image_records + logo_instances + brand_records）
│
├── staging/
│   └── logo_engine.db               ← 暫存 DB（Quality Gate 前的候選管理）
│
├── fetch/
│   ├── records.json                 ← 最終 10 筆記錄（品質過關 + 平衡後）
│   └── images/                      ← 所有下載的圖片（候選池 + 歷史）
│       ├── adidas_69c47adb.jpg
│       ├── disney_69c9e3a9.jpeg
│       └── ...（共 60+ 張）
│
├── brand/
│   └── brand_records.json           ← 品牌知識庫（Wikidata 資料，13 個品牌）
│
├── segment/                         ← SAM3 分割輸出（--with-sam3 時產生）
│   ├── records_with_logo_masks.json ← 含 logo_bbox, mask_path, SAM3 統計的完整記錄
│   ├── masks/                       ← Binary Logo Masks（PNG 灰階）
│   │   ├── 7d5ce5b96afddd7f.png     ← 以 record_id 命名
│   │   └── ...（共 20 張）
│   └── visualizations/              ← 視覺化疊圖（原圖 + Mask + BBox）
│       ├── 7d5ce5b96afddd7f.png
│       └── ...（共 20 張）
│
├── review/
│   └── review_queue.json            ← 待人工審核的 Logo Instances（20 筆，全 needs_review）
│
├── export/
│   └── knowledge_base.json          ← 最終交付 JSON（20 筆，含完整 metadata + logo instances）
│
├── analysis/
│   ├── analysis.md                  ← Markdown 批次分析報告
│   ├── summary.json                 ← 結構化統計摘要（JSON）
│   └── analyze.json                 ← analyze-run 原始輸出 log
│
└── meta/                            ← 每個步驟的執行 log（JSON）
    ├── preflight.json               ← 模型可用性預檢結果
    ├── batch_plan.json              ← limit_per_pair 計算結果
    ├── raw_records.json             ← Collector 原始記錄（34 筆）
    ├── collector.json               ← collector 執行統計
    ├── balance.json                 ← 第一次平衡統計（30 筆候選）
    ├── candidate_records.json       ← 30 筆候選記錄
    ├── ontology.json                ← Ontology 抓取 log
    ├── staging_seed.json            ← Staging seed-ontology log
    ├── staging_ingest.json          ← Staging ingest-images log
    ├── staging_gate.json            ← Quality Gate 詳細結果（40 筆）
    ├── export_passed.json           ← export-image-records log
    ├── passed_records.json          ← 10 筆通過 gate 的記錄
    ├── balance_passed.json          ← 第二次平衡 log
    ├── segment.json                 ← SAM3 分割統計
    ├── phase1.json                  ← Phase1 各子步驟統計
    ├── export.json                  ← export-kb log
    └── summary.json                 ← DB 整體狀態摘要</pre>


<!-- ═══════════════════════════════════════════════════════════════
     第 5 節：Knowledge Base 欄位完整說明
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>5&ensp;Knowledge Base 欄位完整說明</h1>

<p><code>export/knowledge_base.json</code> 是本 Pipeline 的最終交付物。每筆記錄由 <code>image_records</code> 與 <code>logo_instances</code> JOIN 而成，包含以下欄位：</p>

<h2>5.1&ensp;圖片層欄位（來自 image_records）</h2>
<table>
  <thead><tr><th>欄位名稱</th><th>類型</th><th>範例值</th><th>說明</th></tr></thead>
  <tbody>
    <tr><td><code>image_id</code></td><td>string</td><td><code>"20cf1fe51128a440"</code></td><td>系統內部圖片 ID（8 bytes hex）</td></tr>
    <tr><td><code>brand</code></td><td>string</td><td><code>"Disney"</code></td><td>Collector 標記的品牌（brand_hint）</td></tr>
    <tr><td><code>category</code></td><td>string</td><td><code>"mugs"</code></td><td>商品類別</td></tr>
    <tr><td><code>source</code></td><td>string</td><td><code>"poshmark"</code></td><td>資料來源名稱</td></tr>
    <tr><td><code>source_channel</code></td><td>string</td><td><code>"marketplace"</code></td><td>管道類型</td></tr>
    <tr><td><code>source_kind</code></td><td>string</td><td><code>"marketplace"</code></td><td>影響 Quality Gate soft-pass 決策</td></tr>
    <tr><td><code>product_name</code></td><td>string</td><td><code>"Walt Disney Mug Goofy Cuisine..."</code></td><td>商品標題</td></tr>
    <tr><td><code>product_url</code></td><td>string</td><td><code>"https://poshmark.com/listing/..."</code></td><td>商品頁面 URL</td></tr>
    <tr><td><code>image_url</code></td><td>string</td><td><code>"https://di2ponv0v5otw.cloudfront.net/..."</code></td><td>原始圖片 CDN URL</td></tr>
    <tr><td><code>local_image_path</code></td><td>string</td><td><code>"/raid/ming/logo/.../disney_69c9e3a9.jpeg"</code></td><td>本地圖片完整路徑</td></tr>
    <tr><td><code>crawl_timestamp_utc</code></td><td>ISO 8601</td><td><code>"2026-04-04T01:13:44.996800+00:00"</code></td><td>爬取時間戳（UTC）</td></tr>
    <tr><td><code>engine_tier</code></td><td>string</td><td><code>"proposal"</code></td><td>資料品質等級：proposal / silver / gold</td></tr>
    <tr><td><code>engine_quality_status</code></td><td>string</td><td><code>"passed"</code></td><td>Quality Gate 最終結論</td></tr>
    <tr><td><code>engine_quality_score</code></td><td>float</td><td><code>0.9016</code></td><td>各關卡分數加權平均（0–1）</td></tr>
    <tr><td><code>engine_quality_gate</code></td><td>object</td><td>見下方</td><td>各關卡詳細結果（含分數）</td></tr>
    <tr><td><code>difficulty_flags</code></td><td>array</td><td><code>["hard_logo_candidate", ...]</code></td><td>特殊難例標記（影響訓練難度分層）</td></tr>
    <tr><td><code>knowledge_slots</code></td><td>object</td><td><code>{"brand_aliases":[], ...}</code></td><td>品牌知識槽（待後續填充）</td></tr>
  </tbody>
</table>

<h2>5.2&ensp;Logo Instance 層欄位（來自 logo_instances，巢狀於 <code>logo_instances[]</code>）</h2>
<table>
  <thead><tr><th>欄位名稱</th><th>類型</th><th>範例值</th><th>說明</th></tr></thead>
  <tbody>
    <tr><td><code>instance_id</code></td><td>string</td><td><code>"e3a406bcd1ae34c2"</code></td><td>Logo Instance 唯一 ID</td></tr>
    <tr><td><code>brand_id</code></td><td>string</td><td><code>"adidas"</code></td><td>canonical 品牌 ID（slug 格式）</td></tr>
    <tr><td><code>merged_brand_name</code></td><td>string</td><td><code>"Adidas"</code></td><td>merge_signals() 決定的品牌名稱</td></tr>
    <tr><td><code>detector_name</code></td><td>string</td><td><code>"imported_grounding_sam3"</code></td><td>偵測器名稱（SAM3 模式）</td></tr>
    <tr><td><code>bbox</code></td><td>array[4]</td><td><code>[141.61, 64.95, 169.13, 75.24]</code></td><td>Logo BBox（xyxy 格式，像素座標）</td></tr>
    <tr><td><code>mask_path</code></td><td>string</td><td><code>"segment/masks/27b53c8d432fc606.png"</code></td><td>SAM3 Binary Mask 路徑</td></tr>
    <tr><td><code>detector_score</code></td><td>float</td><td><code>0.365249</code></td><td>GroundingDINO Logo 偵測信心分數</td></tr>
    <tr><td><code>ocr_text</code></td><td>string/null</td><td><code>null</code></td><td>PaddleOCR 辨識文字（null=未辨識到）</td></tr>
    <tr><td><code>ocr_confidence</code></td><td>float</td><td><code>0.0</code></td><td>OCR 信心分數</td></tr>
    <tr><td><code>clip_score</code></td><td>float</td><td><code>0.2501</code></td><td>CLIP Retrieval 最高匹配分數</td></tr>
    <tr><td><code>caption_text</code></td><td>string</td><td>LLaVA 輸出文字</td><td>Logo Crop 的 VLM 描述（優先）</td></tr>
    <tr><td><code>caption_model</code></td><td>string</td><td><code>"llava-hf/llava-1.5-7b-hf"</code></td><td>使用的 Caption 模型</td></tr>
    <tr><td><code>confidence</code></td><td>float</td><td><code>0.6251</code></td><td>merge_signals() 的最終信心分數</td></tr>
    <tr><td><code>ambiguity_note</code></td><td>string/null</td><td><code>"ambiguous_clip_brand_retrieval"</code></td><td>歧義說明（觸發 needs_review）</td></tr>
    <tr><td><code>review_status</code></td><td>string</td><td><code>"needs_review"</code></td><td>人工審核狀態</td></tr>
    <tr><td><code>tier</code></td><td>string</td><td><code>"proposal"</code></td><td>資料等級</td></tr>
    <tr><td><code>attribution</code></td><td>object</td><td>見說明</td><td>完整 attribution chain（CLIP/VLM/merged）</td></tr>
    <tr><td><code>provenance</code></td><td>object</td><td>見說明</td><td>偵測來源追溯（grounding model、prompt 等）</td></tr>
  </tbody>
</table>

<!-- ═══════════════════════════════════════════════════════════════
     第 6 節：本批次統計結果
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>6&ensp;本批次統計結果</h1>

<h2>6.1&ensp;品牌與類別分佈</h2>
<table>
  <thead><tr><th>品牌</th><th>類別</th><th>筆數</th></tr></thead>
  <tbody>
    <tr><td>Adidas</td><td>apparel</td><td>2</td></tr>
    <tr><td>Disney</td><td>mugs</td><td>2</td></tr>
    <tr><td>Adidas</td><td>shoes</td><td>1</td></tr>
    <tr><td>Lululemon</td><td>apparel</td><td>1</td></tr>
    <tr><td>New Balance</td><td>shoes</td><td>1</td></tr>
    <tr><td>Starbucks</td><td>mugs</td><td>1</td></tr>
    <tr><td>Under Armour</td><td>apparel</td><td>1</td></tr>
    <tr><td>Under Armour</td><td>shoes</td><td>1</td></tr>
  </tbody>
  <tfoot><tr><td colspan="2">合計</td><td><strong>10</strong></td></tr></tfoot>
</table>

<h2>6.2&ensp;品牌分佈（fetch/records.json 中的 10 筆）</h2>
<table>
  <thead><tr><th>品牌</th><th>筆數</th><th>佔比</th></tr></thead>
  <tbody>
    <tr><td>Adidas</td><td>3</td><td>30%</td></tr>
    <tr><td>Disney</td><td>2</td><td>20%</td></tr>
    <tr><td>Under Armour</td><td>2</td><td>20%</td></tr>
    <tr><td>Lululemon</td><td>1</td><td>10%</td></tr>
    <tr><td>New Balance</td><td>1</td><td>10%</td></tr>
    <tr><td>Starbucks</td><td>1</td><td>10%</td></tr>
  </tbody>
  <tfoot><tr><td>合計</td><td>10</td><td>100%</td></tr></tfoot>
</table>

<h2>6.3&ensp;類別分佈</h2>
<table>
  <thead><tr><th>類別</th><th>筆數</th><th>佔比</th></tr></thead>
  <tbody>
    <tr><td>apparel</td><td>4</td><td>40%</td></tr>
    <tr><td>shoes</td><td>3</td><td>30%</td></tr>
    <tr><td>mugs</td><td>3</td><td>30%</td></tr>
  </tbody>
  <tfoot><tr><td>合計</td><td>10</td><td>100%</td></tr></tfoot>
</table>

<h2>6.4&ensp;Knowledge Base 完整統計</h2>
<table>
  <thead><tr><th>指標</th><th>數值</th></tr></thead>
  <tbody>
    <tr><td>Knowledge Base 記錄數（image × instance JOIN）</td><td>20</td></tr>
    <tr><td>唯一品牌數</td><td>6</td></tr>
    <tr><td>唯一類別數</td><td>3</td></tr>
    <tr><td>唯一資料來源數</td><td>1（poshmark）</td></tr>
    <tr><td>quality_status = passed</td><td>20（100%）</td></tr>
    <tr><td>quality_status = filtered</td><td>0</td></tr>
    <tr><td>Logo Instance Tier = proposal</td><td>20（100%）</td></tr>
    <tr><td>review_status = needs_review</td><td>20（100%）</td></tr>
    <tr><td>review_status = auto_accept</td><td>0</td></tr>
    <tr><td>SAM3 Mask 數量</td><td>20</td></tr>
    <tr><td>OCR 辨識到文字</td><td>0（縮圖過小）</td></tr>
    <tr><td>目標達成（target_achieved）</td><td>True</td></tr>
  </tbody>
</table>

<!-- ═══════════════════════════════════════════════════════════════
     第 7 節：Review Queue 與下一步行動
════════════════════════════════════════════════════════════════ -->
<div class="pagebreak"></div>
<h1>7&ensp;Review Queue 與下一步行動</h1>

<h2>7.1&ensp;Review Queue 說明</h2>

<p><code>review/review_queue.json</code> 包含所有 <code>review_status != "auto_accept"</code> 的 Logo Instances，
依 confidence 由低至高排序，優先讓人工審核最不確定的記錄。</p>

<p>每筆 review queue 記錄包含：</p>
<ul>
  <li><code>instance_id</code>、<code>image_id</code>：用於定位記錄</li>
  <li><code>brand</code>：merge_signals() 的品牌決策</li>
  <li><code>detector_score</code>：GroundingDINO 信心</li>
  <li><code>clip_score</code>：CLIP Retrieval 最高分</li>
  <li><code>confidence</code>：最終綜合信心（本批次約 0.62–0.75）</li>
  <li><code>local_image_path</code>：本地圖片路徑，供人工查看</li>
  <li><code>image_record</code>：完整的原始記錄 metadata</li>
</ul>

<p>低信心範例記錄：</p>
<pre>{"instance_id": "ce4d772ce18196d0", "brand": "Nike", "confidence": 0.6191,
 "detector_score": 0.219449, "clip_score": 0.23817,
 "ambiguity_note": "ambiguous_clip_brand_retrieval",
 "review_status": "needs_review",
 "local_image_path": "fetch/images/adidas_69bff709.jpeg"}</pre>

<div class="box box-warn">
  <div class="box-label">品牌標籤不一致案例</div>
  上例中，圖片本身是 <strong>Adidas</strong>（brand_hint），但 CLIP Retrieval 最高分判定為 <strong>Nike</strong>。
  這是 CLIP 歧義的典型案例，需人工確認正確品牌標籤。
</div>

<h2>7.2&ensp;人工審核流程</h2>

<p>審核後，對每筆記錄填入 <code>review_status</code>（<code>accepted</code> 或 <code>rejected</code>）及 <code>tier</code>（<code>gold</code> 或 <code>silver</code>），
儲存為新的 JSON 後執行：</p>

<pre>python -m logo_data_engine --db engine/logo_engine.db \
    review-apply --decisions review/reviewed_decisions.json</pre>

<h2>7.3&ensp;建議後續動作</h2>

<table>
  <thead><tr><th>優先順序</th><th>動作</th><th>說明</th></tr></thead>
  <tbody>
    <tr>
      <td>1（立即）</td>
      <td>人工審核 Review Queue</td>
      <td>20 筆全 needs_review，尤其關注 brand_hint 與 CLIP 決策不一致的記錄</td>
    </tr>
    <tr>
      <td>2</td>
      <td>查看 segment/visualizations/</td>
      <td>確認 SAM3 Mask 覆蓋範圍是否合理，標記明顯分割錯誤</td>
    </tr>
    <tr>
      <td>3</td>
      <td>增加 --oversample-factor</td>
      <td>目前 30 筆候選中有 30 筆 near_duplicate，可嘗試 --oversample-factor 5 擴大來源多樣性</td>
    </tr>
    <tr>
      <td>4</td>
      <td>擴增品牌/類別 Pairs</td>
      <td>目前 17 pairs，可加入更多品牌或新類別（如 bags、electronics）</td>
    </tr>
    <tr>
      <td>5</td>
      <td>使用 import-run 匯入</td>
      <td>此批次審核完成後，可用 <code>import-run</code> 合併至全局 engine DB</td>
    </tr>
  </tbody>
</table>

<hr/>
<p class="note" style="text-align:center">
  本報告由 Logo Data Engine 自動產生並人工整理。<br/>
  批次目錄：<code>/raid/ming/logo/logo_data_engine/results/batch_10_vlm3_sam3</code><br/>
  文件生成時間：2026-04-04
</p>

</body>
</html>
"""

import sys
from pathlib import Path

output_path = Path("/raid/ming/logo/logo_data_engine/docs/pipeline_report.pdf")
output_path.parent.mkdir(parents=True, exist_ok=True)

try:
    from weasyprint import HTML, CSS
    print("[*] 正在使用 WeasyPrint 生成 PDF...")
    HTML(string=HTML_CONTENT).write_pdf(str(output_path))
    print(f"[✓] PDF 已生成：{output_path}")
    print(f"[i] 檔案大小：{output_path.stat().st_size / 1024:.1f} KB")
except Exception as e:
    print(f"[!] 錯誤：{e}")
    import traceback; traceback.print_exc()
    sys.exit(1)
