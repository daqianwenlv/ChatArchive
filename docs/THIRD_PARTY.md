# Third-party dependencies / 第三方依赖

The source is licensed under MIT. Runtime dependencies are pinned, with official distribution hashes, in `requirements.lock`. Their upstream license declarations are listed below; installed distributions retain their own license files. Optional development tools are listed separately in `requirements-dev.txt`. This inventory does not grant rights to platform SDKs, third-party data or services. No vendor binary SDKs are bundled.

项目源码使用 MIT License。运行依赖版本固定在 requirements.lock，容器安装时保留各发行包附带的许可证。开发检查工具列于 requirements-dev.txt，不会额外安装到运行镜像。

以下依赖清单由已安装发行包的元数据生成。许可证字段描述上游声明，不构成对平台 SDK、第三方数据或服务条款的授权。当前源码包不包含飞书、微信、企业微信或钉钉的二进制 SDK。

| Package / 依赖 | Version / 版本 | Upstream license / 上游许可证声明 |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.143.0 | MIT |
| h11 | 0.16.0 | MIT License |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httpx | 0.28.1 | BSD License |
| httpx2 | 2.13.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| jieba | 0.42.1 | MIT License |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| mcp | 2.3.0 | MIT License |
| mcp-types | 2.3.0 | MIT License |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | MIT License |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.0 | MIT |
| pydantic_core | 2.50.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| PyJWT | 2.15.1 | MIT |
| pytest | 9.1.1 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| sse-starlette | 3.5.0 | BSD-3-Clause |
| starlette | 1.7.0 | BSD-3-Clause |
| truststore | 0.10.4 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uvicorn | 0.54.0 | BSD-3-Clause |
