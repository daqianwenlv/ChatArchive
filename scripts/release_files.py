"""The source distribution allowlist is independent of the developer working directory."""
from pathlib import Path

def source_files(root):
    root=Path(root)
    files=['README.md','README.zh-CN.md','LICENSE','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','CHANGELOG.en.md',
           'requirements.txt','requirements.lock','requirements-dev.txt','.gitignore','.env.example',
           '.dockerignore','Dockerfile','compose.yaml',
           'docs/API.md','docs/DEPLOYMENT.md','docs/BACKUP.md','docs/RELEASE.md','docs/VALIDATION.md','docs/THIRD_PARTY.md','docs/images/overview.jpg',
           'docs/images/group-analysis.jpg','docs/images/message-search.jpg',
           'docs/API.en.md','docs/DEPLOYMENT.en.md','docs/BACKUP.en.md','docs/RELEASE.en.md','docs/VALIDATION.en.md','docs/ROADMAP.en.md',
           'docs/产品原则.md','docs/产品需求.md','docs/架构与接口草案.md','docs/实施清单.md','docs/开源与部署.md',
           'scripts/export_chatlog.py','scripts/package_source.py','scripts/release_files.py',
           'scripts/release_check.py','scripts/verify_docker.py',
           'web/index.html','web/app.js','web/app.css','web/favicon.svg',
           'deploy/chatarchive-api.service','deploy/chatarchive-index.service','deploy/chatarchive-index.timer',
           'deploy/chatarchive-index.env.example','deploy/nginx.conf.example',
           'examples/sample.jsonl','examples/showcase.jsonl','examples/mcp_client.py','.github/workflows/checks.yml',
           '.github/ISSUE_TEMPLATE/bug_report.md','.github/ISSUE_TEMPLATE/feature_request.md',
           '.github/pull_request_template.md']
    for folder in ['chatarchive','tests']:
        files.extend(str(p.relative_to(root)) for p in (root/folder).rglob('*.py') if p.is_file() and '__pycache__' not in p.parts)
    return sorted(set(files))
