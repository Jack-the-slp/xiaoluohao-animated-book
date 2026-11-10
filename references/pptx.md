# 动画书 PPT 直出

本技能默认输出本地 `.pptx`。沿用 presentations skill 的 Artifact Tool、本地 finalizer 和画面检查，不先建在线演示文稿。

1. 用 `load_workspace_dependencies` 获得实际 Node 和库路径，读取当前 presentations skill 的本地构建、排版与验收指导。
2. 工程通常使用 `book.json`：角色、封面、动作 WebP、场景与原 HTML 格式相同。每个动作可加 `scene`，或配置 `pptx.sceneByAction`；否则取 `defaultScene`。游泳使用已批准的水面背景。绘本 GIF 是一次播放，不能用单张截图代替。
3. 执行以下命令。脚本内完成一次 operation marker、动画转换、原生文字排版、全页预览、媒体去重、跳转修复、转场写入、文件 finalizer 和实际输出回读。不要在外部重复运行 marker。

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
python "<skill>/scripts/pptx.py" build "<项目>" --out "<项目>/output/书名_动画书.pptx" --node "<load_workspace_dependencies返回的Node.exe>" --presentations-skill "<当前presentations技能目录>"
```

已维护的旧 PPT 工程也可用 `--manifest <项目>/source/book.json`，其结构为 `roles`、`actions`、逐角色动作 `pages`（`role`、`key`、`subject`、`place`、`word`、`note`、`gif`、可选 `background`）、`logo`、`footer` 和可选 `coverLines`。所有资源必须位于工程内。

输出文件已存在时换新版本名。构建目录在项目 `.pptx-build/<成品名>/`，画面和报告在 `review/<成品名>/`。`book.py init` 会复制 PPT 和 HTML 所需脚本，便于后续维护。

默认一张封面、一张角色目录及每个角色的动作页。角色不超过 8 个、动作不超过 8 个时提供直接跳转文字；更多内容仍保留目录和前后翻页。数量与称呼来自配置，不写死七角色八动作。PPT 固定每页场景，避免默认生成所有场景组合。

基准布局：1280×720，主内容左右 80 px，导航上下至少 44 px；右图 528×528，位于 `(672,100)`。句式三行、页脚与 Logo 沿用品牌要求。原生转场为左向覆盖 550 ms，封面和目录淡入，不自动计时翻页，不加翻页声。按本次用户要求可进一步改版，但调整后同步修改几何验收。

验收需区分层次：脚本证明页数、文字、媒体、字节对应、转场 XML、链接目标和安全区；预览用于逐页看排版和图词一致；PowerPoint 放映用于实际看动作、转场和目录跳转。首次与末页、最长动作词、青少年角色和游泳页应纳入放映抽查。未实际测到的播放器不要声称兼容。

完成后保留正式 PPTX、维护用源稿与最少报告/预览，清理本任务原始导出包、候选包和临时逐页渲染。先核对真实路径与成品；不删除用户原件或其他任务文件，不绕过已被自动审核拒绝的清理。

## 公开分发边界

本仓库包含项目脚本，不包含 `@oai/artifact-tool`、presentations 技能或 Codex 私有运行时。PPT 构建只在这些依赖实际可用的环境执行。不要把运行时拷贝进仓库或从不明来源下载。HTML 路径不需要这些依赖。
