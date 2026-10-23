# 第三方依赖与模型

Git 仓库包含项目源码、文档和程序生成的测试样例，不包含模型权重或图库内容。Release 启动包另附 CPython 和运行依赖，其许可证文件随运行环境保留，完整版本列表见制品的 manifest。项目的 MIT 许可证不替代这些组件的许可证。

| 组件 | 用途 | 上游许可证及来源 |
| --- | --- | --- |
| CPython / python-build-standalone | 发布包内置、可重定位的 Python 运行环境 | [Python PSF License](https://docs.python.org/3/license.html)、[构建项目](https://github.com/astral-sh/python-build-standalone) |
| osxphotos | 读取 macOS Photos 索引 | [MIT](https://github.com/RhetTbull/osxphotos) |
| PyObjC | Python 调用 Apple Vision／Quartz | [MIT](https://github.com/ronaldoussoren/pyobjc) |
| Pillow | 图片缩略图与感知哈希 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| MLX、MLX-VLM | 可选本地视觉推理 | [MLX MIT](https://github.com/ml-explore/mlx)、[MLX-VLM MIT](https://github.com/Blaizzy/mlx-vlm) |
| Transformers、Hugging Face Hub | 可选模型加载与下载 | [Transformers Apache-2.0](https://github.com/huggingface/transformers)、[Hub Apache-2.0](https://github.com/huggingface/huggingface_hub) |
| llama.cpp | Windows 本地视觉推理引擎 | [MIT](https://github.com/ggml-org/llama.cpp/blob/b11829/LICENSE)，原包 OpenMP 通知保留 |
| ImageIO-FFmpeg / FFmpeg 7.1 | Windows 视频缩略图与兼容预览 | [ImageIO BSD-2-Clause](https://github.com/imageio/imageio-ffmpeg/blob/v0.6.0/LICENSE)、FFmpeg 与外部编码库保留 GPL/LGPL 许可；完整许可、运行时通知及来源见 `third_party/licenses/` |
| Microsoft C++ Runtime | Windows 应用本地运行库 | 来自构建工具随附的 Microsoft Visual C++ 可再分发文件；使用一组匹配的 x64 CRT，适用微软许可，不受本项目 MIT 许可替代 |
| Send2Trash / PyWinRT | Windows 回收站与系统 OCR | 上游及 wheel 自带许可证，固定版本见 Windows manifest |
| Tokenizers | 本地模型分词 | [Apache-2.0](https://github.com/huggingface/tokenizers/blob/v0.23.3/LICENSE) |
| Qwen3.5-4B MLX 4-bit 权重 | 参考增强模型，单独下载 | [模型卡及 Apache-2.0 声明](https://huggingface.co/lmstudio-community/Qwen3.5-4B-MLX-4bit) |

Apple Photos、Vision、PhotoKit 及开发工具由系统提供，使用需符合 Apple 的相应条款。发布包保留 CPython 的 `LICENSE.txt` 和依赖安装目录中原有的 license／notice 文件（包括 OpenCV 的第三方通知、NumPy 的 LAPACK 许可及 cryptography 的多份许可）。上游 PyObjC 12.2.2 与 tokenizers 0.23.3 wheel 缺少独立许可证文件的部分，在 `third_party/licenses/` 中按对应官方版本补充；来源与校验值见其中的 `SOURCES.md`。更新或增加依赖时，应一并核对所分发版本的许可与通知。

项目曾参考照片整理、重复检测工具的一般交互思路；本仓库不包含 PhotoDelete、Immich、PhotoPrism 或 Czkawka 的源码或二进制。
