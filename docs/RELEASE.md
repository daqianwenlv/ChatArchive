# 开源预览版发布流程

[English](RELEASE.en.md) · **简体中文**

首次公开以单工作空间查询预览版交付。源代码、登录、导入、查询、MCP、备份恢复属于本轮范围；原始事件仓库、采集连接管理、分级成员权限、钉钉采集和模型分析仍是后续功能。

## 本地验证

```sh
python -m pip install -r requirements.lock
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pytest tests -q
node --check web/app.js
python scripts/package_source.py
python scripts/release_check.py
python -m pip_audit -r requirements.lock --no-deps --disable-pip --strict
python scripts/verify_docker.py --report docker-verification.json
```

Docker 验收要求 Docker Engine 和 Compose v2。脚本创建随机命名的独立项目、数据卷和本机端口，只使用自带虚构样例，结束时清理自己创建的容器与卷。它不使用现有 `.env` 的管理员令牌，不读取生产数据。

`.github/workflows/checks.yml` 会执行上述检查；依赖扫描失败会阻断流程。Actions 依赖固定到提交 SHA。远端结果见 [GitHub Actions](https://github.com/daqianwenlv/ChatArchive/actions/workflows/checks.yml)；存在工作流文件不代表对应提交已经通过。

## 检查发布物

源码 ZIP 由显式清单生成；内部材料、运行数据、备份、登录凭据、采集脚本私有配置和工作目录历史不进入包。`.gitignore` 也包含在包中。固定文件时间和权限使同一份源代码重复打包得到相同哈希。

`release_check.py` 验证文件清单、SHA-256、凭据模式、Python 语法及虚构样例 ID。可用 `--deny-file` 指向本机私有 JSON，额外确认其中的长字符串值未进入发布包，检查结果不打印这些值。此检查不能替代人工审阅或独立安全审计。

运行依赖锁文件含官方 PyPI 发行文件哈希，pip 会启用哈希校验；容器构建显式要求 `--require-hashes`。开发检查工具单独安装，避免把未锁定哈希的检查工具混入运行锁文件。镜像源配置与本版实测条件见 [VALIDATION.md](VALIDATION.md)。

从 ZIP 解压后的目录建立干净仓库；不要把开发工作目录整体上传。首次发布应提供：源码包、SHA256SUMS、版本记录、安装说明、已知限制和验证报告。演示截图必须使用虚构样例。

## 发布前需由维护者配置

- 官方仓库：[daqianwenlv/ChatArchive](https://github.com/daqianwenlv/ChatArchive)。
- 保持 README 项目地址与 SECURITY 私密漏洞报告方式准确。
- 启用私密漏洞报告、依赖更新检查与适用的凭据保护功能。
- 运行首次仓库 CI，检查产物后再打预览版本标签。

## 版本与兼容性

0.2.3-preview.1 保持 0.2.2 查询、账号与密钥数据库结构不变，新增维护命令及发布验证。安装新版本前先备份，再保留旧代码或镜像，复核后切换。旧系统快照桥接的 0.2.1 配置变更仍需按照 DEPLOYMENT.md 显式设置，不能直接覆盖生产环境文件。

回退代码不会自动回退数据；数据库恢复到独立目录或卷后核对再切换。后续涉及数据结构的版本必须随附迁移和兼容说明。
