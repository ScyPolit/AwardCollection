# 参与贡献

欢迎修复问题、改进交互、补充测试和完善文档。提交问题时说明版本、部署方式、操作步骤、预期行为与实际结果；截图和日志请先移除学生信息、印章、口令、会话及私钥。安全问题请按 [安全报告流程](SECURITY.md) 私下报告。

## 开发环境

- Python 3.12、Node.js 20、pnpm 10.33.2。
- PostgreSQL 17 用于事务、权限和并发验收；SQLite 仅用于便捷开发。
- Chromium 运行依赖由 Playwright 安装；Office 格式转换由 `converter` 服务提供。

以下命令在仓库根目录执行。Python 虚拟环境需先按当前操作系统的方式激活。

```bash
python -m venv .venv
# Linux / macOS：source .venv/bin/activate
# PowerShell：.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt -c backend/constraints.txt
python backend/tools/prepare_fonts.py
python -m playwright install chromium
python backend/manage.py migrate
python backend/manage.py cache_builtin_fonts
python backend/manage.py createsuperuser
```

```bash
corepack enable
corepack prepare pnpm@10.33.2 --activate
pnpm --dir frontend install --frozen-lockfile
npm --prefix frontend/ppt-editor ci --ignore-scripts
```

分别在三个终端启动后端、子编辑器和管理界面：

```bash
# 终端 1：后端，默认 SQLite 和开发配置
python -m uvicorn config.asgi:application --app-dir backend --host 127.0.0.1 --port 8000

# 终端 2：编辑器，18850 端口
npm --prefix frontend/ppt-editor run dev

# 终端 3：管理界面；8848 与后端默认 CSRF 来源一致
pnpm --dir frontend exec vite --host 127.0.0.1 --port 8848
```

批量生成原生模板还需要运行 Worker，并将 `PPT_RENDER_URL` 设置为同一管理界面的 `/ppt-editor/render.html`。Office 导入依赖转换服务；生产联调优先使用 Docker Compose，不能用 `vite preview` 替代完整业务服务。

## 提交前验证

根据改动选择相关检查。涉及审批、签名或权限时，补充能复现业务问题的测试，并在 PostgreSQL 上验证。

```bash
python backend/manage.py test awards
pnpm --dir frontend typecheck
npm --prefix frontend/ppt-editor run type-check
pnpm --dir frontend build
docker compose config --quiet
```

界面改动应检查浅色、深色和窄屏效果。编辑器改动还应检查预览与最终 PDF 的文字、字体、空格和布局是否一致。不要提交真实学生数据、测试账号口令或部门公章原图。

## Pull Request

请说明解决了什么问题、修改后的行为及验证方式。尽量让一次改动围绕一个明确目标；新增配置需同步 `.env.example` 与部署文档。

保持上游版权和许可证，PPTist 修改需同步其 [修改说明](frontend/ppt-editor/MODIFICATIONS.md)。提交代码前请确认对代码及素材拥有贡献权限。
