---
name: component-static-assets
overview: 把 PageComponent 编辑区从“仅图片”升级为“通用静态资源（含所有文件类型）”，并在 Monaco 编辑器中提供可切换的快捷插入（智能模板/仅URL）。方案默认兼容现有图片数据与现有上传 API。
todos:
  - id: model-asset
    content: 设计并新增通用组件资产模型，生成迁移并做历史图片数据迁移
    status: pending
  - id: admin-inline
    content: 把 PageComponent 内联从图片专用升级为资源专用
    status: pending
  - id: upload-api
    content: 扩展上传/媒体 API 为全文件类型并补充安全限制
    status: pending
  - id: editor-quick-insert
    content: 在 Monaco 媒体库加入插入模式切换与按类型模板插入
    status: pending
  - id: tests-validate
    content: 补充 API/迁移测试并完成后台手工验收
    status: pending
isProject: false
---

# 扩展组件静态资源与快捷插入

## 目标

- 在你截图这块（`Page Component Images`）支持图片以外的静态资源。
- 在下方动态编辑区（Monaco HTML 编辑器）支持“快捷插入”，并提供两种模式：
  - 智能模板插入（按资源类型生成标签）
  - 仅插入 URL

## 现状与约束

- 当前组件内联模型是图片专用：`[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/models/pages/page_component.py](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/models/pages/page_component.py`)` 中 `PageComponentImage.image = ImageField(...)`。
- 上传接口现在强制图片：`[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/views/upload.py](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/views/upload.py`)` 里对 `content_type.startswith("image/")` 做了硬限制。
- 编辑器里的媒体库也只拉图片：`[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/templates/admin/pages/pagecomponent/change_form.html](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/templates/admin/pages/pagecomponent/change_form.html`)` 请求 `GET /api/pages/media/?type=image`，并只走 `insertImageTag(...)`。
- 但底层 `MediaAsset.file = FileField(...)` 已经是通用文件模型：`[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/models/media.py](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/models/media.py`)`。

## 实施方案

### 1) 把组件内联从“图片行”扩展为“资源行”

- 在 `[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/models/pages/page_component.py](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/models/pages/page_component.py`)` 新增通用资产模型（建议 `PageComponentAsset`），字段建议：
  - `component`（FK）
  - `file`（FileField）
  - `asset_type`（从 MIME 推断，可人工修正）
  - `order`, `title`, `caption`, `link`
- 生成迁移（预计 `0004_*`），并保留现有 `PageComponentImage` 兼容读取（避免历史数据直接失效）。
- 在 `[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/admin/page_component.py](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/admin/page_component.py`)` 增加/替换 inline：把当前 `PageComponentImageInline` 升级为资源 inline（文件、类型、顺序、描述）。

### 2) 升级上传与媒体列表 API 为全文件类型

- 修改 `[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/views/upload.py](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/views/upload.py`)`：
  - 去掉“仅图片”硬限制，改为“允许全部文件类型 + 安全限制”（文件大小上限、可选扩展名 denylist）。
  - 返回统一元数据：`url`, `name`, `type`, `is_image`, `extension`。
- 继续复用 `MediaAsset`，不拆接口路径（`/pages/upload/`, `/pages/media/` 不变），确保现有调用可平滑过渡。

### 3) 在 Monaco 工具栏加入“快捷插入”双模式

- 修改 `[/Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/templates/admin/pages/pagecomponent/change_form.html](` /Users/hongzhe/Code/Innovate-To-Grow-Website/src/pages/templates/admin/pages/pagecomponent/change_form.html`)`：
  - 上传按钮改为支持全部文件（`input[type=file]` 去掉 `accept="image/*"`）。
  - 媒体库改为全资源浏览（保留按类型筛选）。
  - 新增“插入模式”切换：`智能模板` / `仅URL`。
- 新增插入生成器逻辑（同文件 JS 或抽到静态 JS）：
  - 图片 -> `<img src="..." alt="..." />`
  - 视频 -> `<video controls src="..."></video>`
  - 音频 -> `<audio controls src="..."></audio>`
  - CSS -> `<link rel="stylesheet" href="...">`
  - JS -> `<script src="..."></script>`
  - 其他 -> `<a href="..." target="_blank" rel="noopener">filename</a>`
- 双击资源默认按当前模式插入，按钮插入也遵循当前模式。

### 4) 数据兼容与迁移策略

- 增加一次性数据迁移：把已有 `PageComponentImage` 记录复制到新资产表（类型标记为 image），避免编辑页出现“老数据不可见”。
- 保留旧模型读取一段时间（仅兼容，不再作为主写入目标），后续可再做清理迁移。

### 5) 测试与验收

- 新增/扩展测试：
  - 上传 API：可上传非图片文件、返回字段正确、权限正确。
  - 媒体列表：`type` 筛选和分页行为正常。
  - 迁移：旧图片数据可在新资源 inline 中看到。
- 手工验收路径：
  - `admin/pages/pagecomponent/<id>/change/` 上传 `pdf/js/css/mp4`。
  - 在媒体库选择资源，分别验证“智能模板”和“仅URL”插入结果。
  - 保存后前端页面组件渲染时可正确引用资源 URL。

## 交付顺序

1. 模型 + 迁移 + admin inline
2. 上传/媒体 API 扩展
3. 编辑器快捷插入 UI 与模板生成
4. 测试与手工回归

