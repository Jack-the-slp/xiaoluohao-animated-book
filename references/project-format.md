# 工程格式与命令

`book.py init` 复制模板、Logo、HTML/PPT 所需脚本和 `book.json`，建立 `source/`、`review/`、`output/`。配置示例是一个哥哥角色、跑步/跳远两动作、简洁/公园两场景。素材需按本次任务绘制或从有权复用的正式源稿复制。

```text
项目/
  book.json
  source/
    book.py, atlas_to_webp.py, book-template.html
    brand/xiaoluohao-logo.png
    atlases/角色/动作.png
    animations/角色/动作.webp
    covers/角色.png
    scenes/场景.jpg
  output/
    书名.html
    书名_绘本/index.html, assets/, 使用说明.txt
    书名_绘本.zip
  review/build-report.json, verification.json, 必要预览与浏览器验收记录
```

## 配置字段

| 字段 | 用法 |
|---|---|
| `title` | 网页与交付书名；文件名自动替换 Windows 禁用字符 |
| `coverLines` | 封面标题分行数组，内容由本次题材确定 |
| `logo` | 项目相对路径，默认原版 Logo；明确无需 Logo 时设 `null` |
| `footerText`, `footerAddress` | 默认平台名称和 `TC-SLP.top` |
| `defaultCharacter`, `defaultScene`, `autoPlay` | 首次打开的角色/场景和播放状态 |
| `coverHoldMs`, `pageHoldMs` | 封面停留、动画结束后额外停留的毫秒数 |
| `characters` | `id`、`name`、可选句中称呼 `subject`、颜色 `dot`、本地 `cover`；`age` 可记录角色约束 |
| `scenes` | `id`、`name`、句中位置 `location`、本地 `image` 或 `null`、自然水面 `water` |
| `pages` | `key`、动作词 `word`、提示 `note`、是否需辅助水池 `pool`、按角色 ID 映射的 `animations` |

所有素材路径相对于项目根目录，且必须在项目内。ID 使用英文字母、数字、连字符或下划线；不可重复。每个动作页必须提供全部角色的动画。`cover` 是独立静帧，可从已验收动画中选合适姿态并配纸底；确保与该角色一致。

构建逐项读取 WebP 的真实播放时长，模板按当前角色计时。构建会拒绝缺资源、重复 ID、非一次播放的 WebP、非方形/静态/不透明的角色动画，以及输出文件夹里不在本次清单中的额外文件。修订后素材清单缩减时，先核实并清理本任务过期的派生成品，或采用独立版本目录，保护其他文件。

## 导出图集

```powershell
python "<项目>/source/atlas_to_webp.py" "<图集.png>" "<动作.webp>" --columns 3 --rows 3 --indices 0,1,2,3,4,5,6,7 --size 620 --fill 0.86 --duration-ms 170 --first-hold-ms 500 --last-hold-ms 1000 --review "<检查.jpg>"
```

索引从 0 开始，按行读取；未指定时使用全部格。`--fill` 是整组可见内容占画布的最大比例；所有帧同一缩放，不逐帧重心对齐。`--repeat 2` 复制选中姿态序列形成一次有限动画；文件仍只播放一次。`--gif <路径>` 可额外输出米白纸底 GIF，供课件使用；本书 HTML 仍使用透明 WebP。生成的 JPG 只供查看，不进入交付包。

```powershell
python "<项目>/source/book.py" build "<项目>"
python "<项目>/source/book.py" verify "<项目>"
```

`build` 生成两版 HTML 和 ZIP，写入 `review/build-report.json` 并运行文件一致性核验。`verify` 可在复制、修订或打包后重新回读。报告只记录它实际检查的项目；浏览器、画面自然度和真实硬件另记。重建后旧 `verification.json` 会被本次结果替换。
