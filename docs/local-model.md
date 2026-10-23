# 可选本地模型

Mac 使用 Apple Silicon 上的 MLX-VLM；Windows 使用随包分发的 llama.cpp CPU 引擎。基础 OCR、标签、活动及重复检测不依赖这个步骤。

## 在网页中使用

使用双击启动包时不需要安装推理环境。打开“图库与模型”，按平台下载模型：Mac 为 Qwen3.5 4B 4-bit（约 3.1 GB），Windows 为 Qwen3-VL 2B Q8（含视觉投影，约 2.3 GB）；下载后选择“开始识别”。可以暂停下载、断点续传、失败重试和暂停识别。识别暂停会先完成当前图片并保存标签，可能需要等待数十秒。开始扫描或识别都需要你主动点击，不会自动删除照片。

下载使用固定上游版本，逐文件检查大小和摘要，全部校验成功后才标为可用。模型文件保存在本机数据目录的 `work/models/`；应用更新不删除这些文件。下载需要联网，看图与 OCR 推理保持离线。

Windows 当前以 CPU 运行，不要求安装显卡驱动或 CUDA；建议至少 8 GB 内存，大图库的识别耗时取决于处理器。Windows 引擎与 Mac MLX 权重格式不同，不能直接共用模型文件。

## Mac 源码环境安装与下载

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

发布包已用内置 Python、内置推理依赖和一张人工合成图片完成真实 Qwen 推理，系统沙盒强制禁网。含模型加载首次约 7.6 秒，再次运行通过缓存约 0.07 秒；这是单张功能验收，不代表全库平均速度或模型准确率。队列、缺模型、暂停、下载和缓存回归也使用合成数据。没有预置私人标注集。

双击启动包已验证内置运行环境的导入、网页模型管理与首次启动；人工合成样例和临时目录用于回归，模型标签仍不构成自动删除依据。
