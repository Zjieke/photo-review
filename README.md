# Photo Review · 照片整理

在浏览器里整理本机照片：多维标签、活动分组、重复与相似图片，以及勾选后统一删除。

**当前为 macOS 开发预览版。** 真实图库功能依赖 Apple Photos、Vision 和 PhotoKit；可选 Qwen 增强依赖 Apple Silicon。尚未提供 Windows 图库适配、签名公证安装包或网页一键下载模型。

## 已有功能

- **本地基础识别**：Apple Vision 中英文 OCR、图像分类和规则标签，不要求下载大模型。
- **多维标签**：按类型、场景、平台和内容组合筛选，支持搜索、手动改标签与大图预览。
- **活动分组**：按拍摄日期集中查看照片、视频数量及原始文件体积，可为活动命名。
- **重复与相似**：本地原文件 SHA-256 查重，感知哈希、颜色与比例筛出相似候选；并排查看后自行勾选。
- **统一删除**：照片和视频共享选择，一次确认后自动分批移入 Apple Photos 的“最近删除”。收藏和隐藏项目受保护。
- **独立滚动**：图片区单独滚动，导航、搜索和操作区保持固定；方向键翻图、空格勾选。
- **可选增强**：Qwen／MLX 在本机补充标签，逐项保存结果，重新启动可接着处理。

照片、OCR 和模型推理留在本机。安装依赖和下载模型需要联网；本项目不提供云端照片上传接口。

## 先看演示

安装 Python 3.11 或更新版本后，在项目目录运行：

```sh
python3 launcher.py --demo
```

浏览器会打开本机页面。演示使用程序生成的图片和记录，不读取照片图库，也不执行删除。无需安装模型、Photos 权限或 Python 第三方依赖。终端保持运行，按 Ctrl+C 停止。

## 使用自己的 Mac 图库

这是源码启动流程，仍需要一次环境准备。基础版本不安装 MLX 或下载 Qwen。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launcher.py --scan
.venv/bin/python launcher.py
```

`--scan` 才会读取系统照片图库，依次进行基础识别、活动索引、重复检测和页面生成。首次全库扫描可能耗时较长；已有基础识别缓存会复用。普通启动只打开现有结果，空目录可以先打开空界面。

准备过环境后，也可以双击 `start.command` 打开浏览器。默认地址为 `http://127.0.0.1:8778/`，端口被占用会给出提示；可使用 `--port 8788` 指定其他端口。关闭浏览器标签页不会退出服务，终端中 Ctrl+C 才会停止。

如果系统阻止读取图库，请按 macOS 的提示为运行 Python 的终端授予所需访问权限。没有本地原图或可用预览的 iCloud 照片可能无法分析；本项目不会自动下载整库原件。

### 启用确认删除

需安装 Apple Command Line Tools，随后构建本机 PhotoKit 助手：

```sh
.venv/bin/python launcher.py --build-helper
```

构建后启动页面，点击“授权照片访问”，在系统提示中允许完整访问。助手只在页面明确确认后执行删除，并再次核对资产及收藏／隐藏状态。iCloud 开启时，删除会同步影响其他已同步设备；恢复请在 Photos 的“最近删除”中操作。

本地构建使用临时签名，不是 Apple 公证发行包。不要对真实照片执行自动化删除测试。

## 可选 Qwen 增强

基础整理不依赖大模型。Apple Silicon 用户可按 [本地模型说明](docs/local-model.md) 单独安装推理依赖、下载模型并运行增强。当前网页展示识别进度与结果；模型安装和任务启动仍使用命令行。

## 数据与当前限制

- `outputs/` 保存本机预览、OCR、索引及删除回执；`work/` 的运行时 JSON、数据库和模型目录保存缓存。它们均被 Git 忽略，不属于公开源码。
- 手工标签、活动名称和勾选保存在**当前浏览器、当前访问地址**的 localStorage 中。换浏览器、换端口或清理站点数据不会自动迁移这些记录。
- 活动分组显示原始文件体积，不等于删除后实际释放的磁盘空间；不包含实况附带视频、编辑副本或系统缓存。
- 视频可以分组、预览和勾选，但没有视频内容语义识别。相似图片可能是不同画面，分类结果也可能有误。
- 当前页面仍将整库索引嵌入 HTML；万张图库的首次页面加载较大。按需查询 API 与持久化数据库尚待改造。
- 已移除多设备协作和另一套客户端实现。本仓库只维护这一套浏览器界面。

## 开发与测试

界面为原生 HTML／CSS／JavaScript，无 npm 运行时依赖。Python 负责图库、分析和本机 HTTP 服务；Swift 只负责 PhotoKit 权限及确认删除。

```sh
.venv/bin/python -m unittest discover -s work -p 'test_*.py'
for test in work/test_*.cjs; do node "$test" || exit 1; done
python3 scripts/check_public_tree.py
```

Node.js 仅用于前端逻辑测试。测试使用合成数据和 mock，不需要读取个人图库或调用真实删除。GitHub Actions 的检查范围与真实机器的授权、扫描、推理验证不同。

主要目录：

```text
launcher.py          浏览器启动、演示与显式扫描入口
work/                当前前端、分析、服务与回归测试
work/native/         PhotoKit 助手源码
scripts/             原生构建与发布检查
docs/                模型、架构与后续计划
outputs/             本机生成数据（不提交）
```

后续重点是无终端安装、网页内可选模型管理、统一保存人工标签、增量 API，以及验证 Windows 适配。详见 [后续计划](docs/roadmap.md)。

## 参与和许可

欢迎使用合成样例提交问题或改进，见 [贡献说明](CONTRIBUTING.md)。请勿在 Issue 中上传私人照片、OCR、图库数据库、令牌或删除回执。

项目自有源码使用 [MIT License](LICENSE)。第三方依赖和模型保留各自许可证，见 [第三方说明](THIRD_PARTY_NOTICES.md)。
