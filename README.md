# 音频切片机
一个简约的 GUI 应用程序，通过静音检测对音频进行切片。

[源项目地址](https://github.com/flutydeer/audio-slicer)

[English README](./README.en.md)

## 截图

![image.png](https://s2.loli.net/2026/02/01/ONARIiVYwbsXgjF.png)

## 当前版本

1.5.0

## Release Notes（1.5.0）

- 新增：设置面板重构为“基础/高级”，高级分组+滚动；预览改为新窗口并支持缩放滑条/滚轮；预设管理支持恢复默认并提示完成；新增参数推荐与一键应用；并行模式与回退策略更完整。
- 修复：预览单位混用、无切片范围为空、CLI 入口参数不匹配、回退临时文件未清理等问题。
- 界面：统一圆角风格与列表选中态、下拉弹层样式。

## 功能

- 基于静音检测的自动切片
- 预览切片区间与长度分布图（新窗口 + 缩放）
- 输出格式：wav / flac / mp3
- 多语言界面
- 支持拖拽导入音频
- 动态阈值与 VAD（语音活动检测）
- 并行切片（多线程 / 多进程）
- 解码回退：询问 / FFmpeg / Librosa / 跳过
- 预设管理（保存 / 删除 / 恢复默认）
- 参数推荐（可一键应用）
- 命名规则与切片清单导出（CSV / JSON）
- 设置标签页（基础 / 高级）与高级分组

## 快速开始

### Windows

- 发行版：在 GitHub Release 中下载并解压后运行 `slicer-gui.exe`。
- 源码运行：双击根目录的 `main.bat`。

### macOS & Linux

```shell
uv sync
uv run python scripts/slicer-gui.py
```
### 命令行

```shell
uv run python scripts/slicer.py path/to/audio.wav
```

## 使用说明

- 通过“Add Audio Files”按钮或拖拽添加音频文件。
- 参数设置在右侧 Settings 面板内，分为“基础 / 高级”。
- 语言切换：主界面右侧 Settings 的 Language 下拉框。
- 勾选“Open output directory when finished”可在完成后自动打开输出目录。
- 智能推荐：选中音频后点击“生成推荐”，可一键应用。
- 预设：在高级页中保存/删除/恢复默认，恢复完成会提示。
- 命名规则：可设置前缀/后缀/时间戳。
- 导出清单：可输出 CSV/JSON 记录切片区间与路径。
- 预览按钮会弹出新窗口；支持缩放滑条与鼠标滚轮缩放；解码失败会提示选择回退方式。
- 高级中包含并行、回退、动态阈值与 VAD 等选项；多进程模式会自动使用“FFmpeg → Librosa”回退。

## 预设与推荐

- 预设保存当前全部切片相关参数（见下方列表）。
- “恢复默认”会覆盖现有预设并重建内置预设。
- 推荐参数基于选中音频分析，可选择是否应用。

## 预设参数

- 阈值、最小长度、最小间隔、步长、最大静音
- 输出格式
- 文件名前缀、文件名后缀、时间戳
- 导出 CSV / JSON
- 动态阈值开关与偏移
- VAD 开关、灵敏度、延迟
- 并行模式与并行数量
- 解码回退策略

## 参数说明

- Threshold（阈值）：RMS 低于此值的区域视为静音，默认 -40 dB。
- Minimum Length（最小长度）：每个切片的最小长度（ms），默认 5000。
- Minimum Interval（最小间隔）：静音段最小长度（ms），默认 300。
- Hop Size（步长）：RMS 帧长度（ms），默认 10。
- Maximum Silence Length（最大静音长度）：切片两端保留的最大静音长度（ms），默认 1000。
- Dynamic Threshold（动态阈值）：根据 RMS 分布自动估计噪声底并应用偏移（dB）。
- Dynamic Offset（动态偏移）：动态阈值的偏移量（dB），值越大越严格。
- VAD（语音活动检测）：对低能量语音进行补偿，减少误切。
- VAD Sensitivity（灵敏度）：值越大越敏感（更容易保留安静语音）。
- VAD Hangover：在语音结束后额外保留的延迟时间（ms）。
- Parallel Mode / Jobs（并行）：选择串行/多线程/多进程及并行数量。
- Decode Fallback（解码回退）：读取失败时的处理策略（询问 / 自动 / 跳过）。

## FFmpeg 说明

解码回退优先顺序如下（满足其一即可自动识别）：

1. 环境变量 `AUDIO_SLICER_FFMPEG` 指向 `ffmpeg.exe`
2. 项目根目录：`ffmpeg.exe`
3. 项目根目录：`ffmpeg/bin/ffmpeg.exe`
4. `tools/ffmpeg.exe`
5. `tools/ffmpeg/ffmpeg.exe`
6. `tools/ffmpeg/bin/ffmpeg.exe`
7. 系统 PATH 中的 `ffmpeg`

## 项目结构

- `src/audio_slicer/`：核心代码
  - `gui/`：主窗口与 UI
  - `utils/`：切片与预览工具
  - `modules/`：多语言文本
- `scripts/`：运行入口脚本
- `tools/`：打包与版本信息
- `assets/`：截图与 UI 文件
## 打包（Windows）

```pwsh
pwsh tools/pack-gui.ps1
```

输出目录：`dist/slicer-gui`，压缩包：`dist/slicer-gui-windows.zip`。

## 故障排查

- 出现 `Illegal Audio-MPEG-Header` 等 mpg123 错误：
  - 多见于损坏/非标准音频或扩展名与实际编码不一致。
  - 建议用 ffmpeg 转为 WAV/FLAC 后再切片。

- 预览失败或切片失败：
  - 请确认文件可被正常解码（能被其他播放器正常播放）。

- 预览图中文显示为方块：
  - 请确保系统安装了 `Microsoft YaHei` 或 `SimHei`。
  - 可尝试重新生成预览图。

日志会写入根目录 `log/` 目录，便于排查问题。

## 许可

本项目遵循仓库中的 LICENSE。
源项目许可证为 MIT。

## 汉化

汉化 by Re-TikaRa
