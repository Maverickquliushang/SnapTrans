# 构建与发布

独立仓库：[Maverickquliushang/SnapTrans](https://github.com/Maverickquliushang/SnapTrans)。

## 构建环境

Windows x64、Python 3.12 x64。每个 PowerShell 进程先初始化项目环境：

```powershell
. ./project-env.ps1
./scripts/bootstrap.ps1
./scripts/build.ps1
./.venv/Scripts/python.exe scripts/build_installer.py
./.venv/Scripts/python.exe scripts/export_source.py
./.venv/Scripts/python.exe scripts/verify_archive.py
./.venv/Scripts/python.exe scripts/verify_installer.py
./.venv/Scripts/python.exe scripts/verify_source.py
```

输出在 output。发布脚本拒绝覆盖同名正式产物。修改后重新发布应更新 snaptrans/__init__.py 和 pyproject.toml 中的版本号。

build.ps1 使用锁定依赖，准备模型和许可，运行测试，打包并执行原生自检。CI 使用 -SkipInteractive 跳过桌面输入检查。GitHub Actions 可手动运行或通过版本标签触发，只生成构建产物，不自动发布 Release。

## 安装器

NSIS 3.11 编译器下载到项目缓存并核对固定 SHA-256，不安装系统工具。安装器无需管理员权限，默认不注册卸载项或创建系统快捷方式；系统集成可主动选择。配置、密钥和缓存保存于程序旁 data。已有空目录可以安装，其他软件或便携版的非空目录会被拒绝。

verify_installer.py 在项目内的独立测试目录验证安装、修复、卸载与数据保留。发现已有注册安装时停止，不修改现有安装；测试可选注册时也不会创建真实快捷方式。

## 公开包检查

scripts/export_source.py 使用文件白名单，排除运行数据、缓存、环境、构建产物和历史诊断。scripts/package_release.py 仅复制当前公开文档与合成 UI 示例。

```powershell
. ./project-env.ps1
./.venv/Scripts/python.exe scripts/audit_public_release.py output/SnapTrans-1.14.0-source.zip
./.venv/Scripts/python.exe scripts/audit_public_release.py output/SnapTrans-1.14.0-win-x64.zip
```

扫描检查常见凭据形状、当前构建目录与用户路径，并检查嵌套许可 ZIP。扫描不能替代人工审查。不要提交 data、浏览器缓存、私有截图、个人日志或真实密钥。公开提交使用 GitHub 提供的 noreply 邮箱。

## Release 文件

- SnapTrans-1.14.0-Setup-x64.exe：安装版。
- SnapTrans-1.14.0-win-x64.zip：完整便携版。
- SnapTrans-1.14.0-source.zip：独立源码，作为可选补充。
- 对应 .sha256：文件完整性校验。

未进行代码签名；签名后必须重新生成校验值。测试范围以 release-validation.md 和实际构建报告为准。
