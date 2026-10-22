# 可选本地模型

当前增强脚本适配 Apple Silicon 上的 MLX-VLM。基础 OCR、标签、活动及重复检测不依赖这个步骤。

## 安装与下载

在已准备的 Python 虚拟环境中安装可选依赖：

```sh
.venv/bin/python -m pip install -r requirements-model.txt
```

参考模型为 [lmstudio-community/Qwen3.5-4B-MLX-4bit](https://huggingface.co/lmstudio-community/Qwen3.5-4B-MLX-4bit)，模型卡标注 Apache-2.0；具体使用遵循上游许可证。模型权重不包含在本仓库中。下载需要数 GB 空间，内存需求取决于图片尺寸、上下文和推理库版本。

```sh
.venv/bin/python -c 'from huggingface_hub import snapshot_download; snapshot_download("lmstudio-community/Qwen3.5-4B-MLX-4bit", local_dir="work/models/Qwen3.5-4B-MLX-4bit")'
```

此命令仅从模型仓库下载文件。下载与推理分开：先完成 `launcher.py --scan` 生成可用照片预览，再执行本地识别：

```sh
.venv/bin/python work/qwen_local_labeler.py
```

增强脚本启用离线模式、关闭 Hugging Face telemetry，并且不信任仓库远程代码。图片及 OCR 不发往云端。结果写入本地 SQLite，每次启动跳过已成功项；失败项可以下次重试。页面会读取最新进度与标签，人工编辑优先于自动建议。

已有兼容模型目录时，可以显式指定路径：

```sh
PHOTO_REVIEW_MODEL_PATH="/path/to/local-model" .venv/bin/python work/qwen_local_labeler.py
```

更换模型目录会建立独立的模型版本缓存；旧的成功标签会保留，直到新模型给出成功结果。同一目录内替换权重不会自动切换版本，请为不同权重使用不同目录。

只选择 MLX-VLM 支持的视觉模型。任意文本模型或其他引擎的量化文件不保证兼容。不同模型的速度、标签质量与内存需求需实际测量；本仓库不承诺换模型后更快或更准确。

## 验证边界

原项目在本机运行过 Qwen／MLX 图片识别；开源整理新增的队列、缺模型处理及缓存测试使用合成数据。首次下载后的推理仍需在你的机器上确认。没有预置私人标注集，也没有把程序生成的格式检查称为模型准确率验证。

网页一键安装推理环境、下载进度、暂停及启动任务属于后续工作。当前不会在打开页面时自动下载模型。
