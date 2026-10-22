# 第三方依赖与模型

本仓库只分发自有源码、文档和程序生成的测试样例，不包含第三方安装环境、模型权重或图库内容。项目的 MIT 许可证不替代以下组件的许可证。

| 组件 | 用途 | 上游许可证及来源 |
| --- | --- | --- |
| osxphotos | 读取 macOS Photos 索引 | [MIT](https://github.com/RhetTbull/osxphotos) |
| PyObjC | Python 调用 Apple Vision／Quartz | [MIT](https://github.com/ronaldoussoren/pyobjc) |
| Pillow | 图片缩略图与感知哈希 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| MLX、MLX-VLM | 可选本地视觉推理 | [MLX MIT](https://github.com/ml-explore/mlx)、[MLX-VLM MIT](https://github.com/Blaizzy/mlx-vlm) |
| Transformers、Hugging Face Hub | 可选模型加载与下载 | [Transformers Apache-2.0](https://github.com/huggingface/transformers)、[Hub Apache-2.0](https://github.com/huggingface/huggingface_hub) |
| Qwen3.5-4B MLX 4-bit 权重 | 参考增强模型，单独下载 | [模型卡及 Apache-2.0 声明](https://huggingface.co/lmstudio-community/Qwen3.5-4B-MLX-4bit) |

Apple Photos、Vision、PhotoKit 及开发工具由系统提供，使用需符合 Apple 的相应条款。第三方组件的间接依赖保留自身许可；发布包含二进制依赖的安装包前，需要额外收集所分发版本的完整许可和通知。

项目曾参考照片整理、重复检测工具的一般交互思路；本仓库不包含 PhotoDelete、Immich、PhotoPrism 或 Czkawka 的源码或二进制。
