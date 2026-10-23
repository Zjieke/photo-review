# 发布包补充许可证

以下文件按对应版本从官方源码原样复制，用于补足上游 wheel 未附带的独立许可证文件。PyObjC 12.2.2 的 core、Vision、Photos 等框架使用相同许可文本。

- `pyobjc-12.2.2-LICENSE.txt`：https://raw.githubusercontent.com/ronaldoussoren/pyobjc/v12.2.2/pyobjc-core/License.txt
  SHA256：`0ca04b07928d4872b9d9bb22187ca0426dd8bfab08f26eada0999a71dc81aaff`
- `tokenizers-0.23.3-LICENSE.txt`：https://raw.githubusercontent.com/huggingface/tokenizers/v0.23.3/LICENSE
  SHA256：`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`

## Windows 增补

- `llama-cpp-b11829-LICENSE.txt` 来自 https://raw.githubusercontent.com/ggml-org/llama.cpp/b11829/LICENSE ，SHA256 `94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d`。Windows 引擎原包中的 LLVM OpenMP 许可证一并保留。
- `ffmpeg-7.1-COPYING.*.txt` 来自 [FFmpeg n7.1 官方源码](https://github.com/FFmpeg/FFmpeg/tree/n7.1)。实际分发二进制的许可通知与构建选项，在构建时通过 `ffmpeg -L`、`ffmpeg -buildconf` 写入同目录；实际二进制 SHA256 见 build-manifest。
- Windows FFmpeg 来自固定的 [imageio-ffmpeg v0.6.0](https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0) wheel，二进制上游为 [imageio-binaries/ffmpeg](https://github.com/imageio/imageio-binaries/tree/master/ffmpeg)。FFmpeg 7.1 对应源代码可在 [n7.1 源码归档](https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n7.1.tar.gz) 获取；外部编码库的配置见构建选项，[x264 源码](https://code.videolan.org/videolan/x264) 与各组件保留其许可。项目通过独立进程调用该程序，项目 MIT 许可证不替代 FFmpeg 及其组件许可。
