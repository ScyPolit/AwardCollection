# AwardCollection 校赛电子证书系统

团队获奖电子证书的名单导入、部门会签、自动生成、数字签名、归档和编号查验系统。

## 技术栈

- 前端：Pure Admin Thin 6.2.0（上游提交 `f0ff132561ab684bb78379239adf29f9a38ac7f1`）、Vue 3、TypeScript、Element Plus。
- 后端：Python 3.12、Django 5.2.7、Django REST Framework 3.16.1、PostgreSQL。
- 文件：openpyxl、ReportLab、PyMuPDF、pyHanko。
- 部署：Nginx、Gunicorn、独立数据库 worker、Docker Compose。

Pure Admin 的 MIT 许可保留在 `frontend/LICENSE`。M0 中文排版和双增量签名验证产物在 `artifacts/first-release/m0-probe`。

## 本地验证

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
.\.venv\Scripts\python backend\manage.py migrate
.\.venv\Scripts\python backend\manage.py test awards
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend typecheck
pnpm --dir frontend build
docker compose config --quiet
```

测试数据由调用者提供独立密码，不在仓库保存：

```powershell
.\.venv\Scripts\python backend\manage.py seed_demo --password '<临时测试密码>'
```

部署现状、阻塞和 A01-A30 实际结果见 [部署说明](docs/deployment.md) 与 [实现状态](docs/implementation-status.md)。
