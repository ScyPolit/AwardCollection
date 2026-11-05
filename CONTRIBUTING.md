# Contributing to AwardCollection

感谢你愿意参与 AwardCollection。

## 开始之前

1. 先阅读 [README](README.md)、[需求说明](docs/requirements.md) 和[实现状态](docs/implementation-status.md)。
2. 对较大的功能或业务规则变更，请先创建 Issue 讨论范围。
3. 不要在 Issue、Pull Request、测试数据或提交记录中包含真实姓名、公章、证书、私钥或部署凭据。

## 开发流程

1. Fork 仓库并从 `main` 创建功能分支。
2. 保持修改范围集中，遵循现有 Django、Vue 和 Pure Admin 结构。
3. 权限、会签、编号、任务恢复和签名相关修改必须补充自动化测试。
4. 提交 Pull Request 前运行：

```powershell
.\.venv\Scripts\python backend\manage.py check
.\.venv\Scripts\python backend\manage.py test awards
pnpm --dir frontend typecheck
pnpm --dir frontend build
docker compose config --quiet
```

## 提交与 Pull Request

- 建议使用清晰的 Conventional Commit，例如 `feat: add batch archive download`。
- Pull Request 需要说明变更目的、业务影响、测试结果和截图（如涉及界面）。
- 不要在同一个 Pull Request 中夹带无关格式化或大范围重构。

## 测试材料

只使用明显标记“测试专用”的虚构部门、名单、公章和证书。任何真实材料都不应进入公开仓库。
