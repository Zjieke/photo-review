# macOS 浏览器版发布包

最终用户解压 ZIP，打开 `Photo Review.app`，系统默认浏览器便会打开本机页面。`.app` 仅负责启动后台服务；图库、标签、活动、删除和模型管理都在浏览器操作。内置 Python、Apple Vision / PhotoKit 依赖和 MLX 推理环境，不要求用户安装 Python、Ollama、终端工具或运行 pip。模型权重不随应用分发，在页面中按需下载。

目前目标是 Apple Silicon（M 系列）Mac，macOS 14 或更新系统。Intel Mac 和 Windows 不在此包的支持范围。最低系统版本由依赖的官方 wheel 标签约束；本机测试不能替代在所有旧系统上实测。

## 两种签名状态

- `adhoc`：本地临时签名的测试包，macOS Gatekeeper 可能拦截。它用于开发验收，不应宣传成“所有人下载后均无提示打开”。本项目不提供删除隔离属性或关闭 Gatekeeper 的脚本。
- `notarized`：使用维护者的 Developer ID Application 证书签名。提交 Apple 公证并 stapler 后，才适合向普通用户分发。Apple 首次打开提示与照片权限仍由系统和用户控制。只签名未公证的构建会明确标为 `signed-unnotarized`。

当前构建机未配置 Developer ID 身份，因此可实际产出并验证的是 `adhoc` 测试包。获取证书需要项目维护者自己的 Apple Developer 账号。不要将证书私钥、公证密码或 API 密钥提交到 Git。

## 数据和程序分开

程序和运行库位于 `.app/Contents/Resources/`；用户数据默认位于 `~/Library/Application Support/Photo Review/`。应用更新只替换 `.app`，不会覆盖已有标签、识别记录或模型。`PHOTO_REVIEW_DATA_DIR` 可在测试中重定向到临时目录。启动本身不扫描真实照片、不下载模型、不自动删除文件。

启动日志位于数据目录的 `logs/launcher.log`。浏览器标签页关闭后，后台服务仍运行；通过页面内的退出入口停止。再次打开应用会复用当前服务。

## 维护者构建

仅构建机需要 Python 3.12+ 和 Xcode Command Line Tools：

```sh
python3 scripts/build_release.py --version 0.2.0
python3 scripts/smoke_release.py 'dist/Photo Review.app'
```

脚本从 Astral 官方 [python-build-standalone](https://github.com/astral-sh/python-build-standalone/releases/tag/20261021) 下载可重定位 CPython 3.12.15 `install_only_stripped`，验证固定 SHA256 后解包。依赖从 PyPI 安装到新运行库，按 `requirements-bundle-lock.txt` 固定版本。MLX / MLX Metal 固定 macOS 14 的官方 wheel 及其 SHA256，避免在较新构建系统上误装仅支持新系统的 wheel。

打包采用源文件白名单，不复制现有虚拟环境、照片、扫描数据库、识别结果、私钥或模型。构建清单记录运行库校验值、依赖版本和制品校验值。第三方包自己的许可证随运行库保留；上游 wheel 缺少独立许可文件的 PyObjC 与 tokenizers，按对应官方版本补充到 `third_party/licenses/`。构建结果包含：

- `dist/Photo Review.app`
- 带平台、版本与签名状态的 ZIP
- ZIP 的 `.sha256` 与依赖 `.manifest.json`

重新构建相同输出时加 `--replace`。`--cache-dir` 只复用已验证的官方 Python 下载；Python 包由 pip 的正常缓存复用。不会复用私人虚拟环境。

## 正式签名与公证

先通过 Apple 的正常流程在维护者钥匙串中配置 Developer ID Application 证书，并使用 `xcrun notarytool store-credentials` 保存公证配置。然后：

```sh
python3 scripts/build_release.py --version 0.2.0 \
  --sign-identity 'Developer ID Application: YOUR NAME (TEAMID)' \
  --notary-profile 'photo-review-release'
```

脚本依次签名内嵌 Mach-O 库/解释器、PhotoKit 助手与主应用，验证深层签名，提交公证，等待结果，staple 并重新打包。若公证失败则构建失败，不把未公证的制品冒充成可公开发行版本。可用环境变量 `PHOTO_REVIEW_SIGN_IDENTITY` 和 `PHOTO_REVIEW_NOTARY_PROFILE` 代替参数。

GitHub Actions 的 **Build macOS browser launcher** 是手动运行的干净构建与验收流程，默认输出标明 `adhoc` 的测试 artifact，不自动发布正式 Release。正式签名应在有维护者证书的受控构建环境中执行。
