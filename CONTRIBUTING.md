# Contributing / 参与贡献

## English

ChatArchive is a query preview. Describe the problem, resulting behavior, validation and compatibility of each change. Keep planned capabilities separate from implemented functionality.

### Development

Follow the [README](README.md) to create a Python 3.12 environment and import the fictional sample. Run `python -m pytest tests -q` and `node --check web/app.js`. Tests must not contact real platforms, open production archives or read personal credentials. `python scripts/verify_docker.py` exercises isolated Docker projects with fictional records and removes its own test volumes.

### Records and adapters

Describe each connector's actual platform capabilities and access limits. Use entirely fictional fixtures; renaming people in real messages does not make those records suitable for publication. Preserve provenance, timestamp precision, types and missing values. Identical display names across platforms do not establish identity.

Provide regression tests for changes to permissions, imports, deduplication or protocol behavior. Schema changes need migration, recovery and reconciliation instructions. Verify affected pages for copy and style changes.

### Contributions

Update code, configuration examples and documentation together. Keep English and Chinese instructions aligned. Never commit archives, credentials, production screenshots or private configuration. Package with `python scripts/package_source.py` and inspect the actual ZIP; Git ignore rules alone are not a distribution boundary.

The project uses MIT; dependencies keep their own licenses. Check redistribution terms before introducing a platform SDK or binary. Report vulnerabilities according to [SECURITY.md](SECURITY.md), not in public issues.

## 简体中文

当前代码是查询预览版，目标架构位于 [服务器架构](docs/架构与接口草案.md)。提交变更时说明问题、行为变化、验证和兼容性，不把规划能力写成已实现。

## 本地开发

按 [README](README.md) 创建 Python 3.12 环境并导入虚构样例。运行 `python -m pytest tests` 和 `node --check web/app.js`。测试不能连接真实平台、真实数据库或读取个人凭据。Docker 验收运行 `python scripts/verify_docker.py`，使用独立项目及虚构数据，结束时清理自己的测试卷。

## 数据与连接器

连接器声明实际平台能力和范围限制。样例及失败用例使用完全虚构的数据，不能把真实记录替换姓名后当作公开样例。保留事件出处、时间精度、类型和缺失状态；跨平台同名不构成身份依据。

修复权限、导入、去重或协议行为应提供回归测试。数据模型变化同时给出迁移、回退与对账方式；文案和样式调整进行对应页面验证。

## 提交与发布

程序、配置示例和文档一起更新。不要提交运行数据、访问令牌、密钥、聊天截图和内部路径配置。打包使用 `python scripts/package_source.py`，检查实际 ZIP 文件清单，不依赖 Git 忽略规则保证安全。

项目源码采用 MIT 许可证；第三方依赖遵循各自许可证。引入平台 SDK 或二进制前确认分发条件。安全问题按 [SECURITY](SECURITY.md) 处理，不公开真实记录或利用细节。
