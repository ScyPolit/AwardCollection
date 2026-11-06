# 校赛电子证书系统

使用 Pure Admin、Django 和 PostgreSQL 的校赛团队电子证书管理系统，支持整批获奖名单会签、自签 PDF、图片输出和证书编号查验。

## 功能

- 超管、部门管理员、负责人，多部门授权及多人协作。
- 统一 Excel 导入、版本冻结、并行会签、本人回避及应急操作。
- 全校共享模板库，背景、文字字段、公章位置、编号水印及图层拖放。
- 各部门独立管理多枚公章，按批准的模板和公章快照签发。
- 后台任务、全局唯一编号、签名 PDF、PNG、单张和整批下载。
- 编号查验、验证码、公开字段及脱敏、作废会签、站内消息。
- Docker 部署、版本标识、加密配置备份和每日维护调度。

## 文档

| 文档 | 内容 |
| --- | --- |
| [需求说明](docs/requirements.md) | 首期范围和业务规则 |
| [技术方案](docs/technical-plan.md) | 服务结构、权限、签名及任务设计 |
| [部署说明](docs/deployment.md) | 当前环境、升级、备份与恢复 |
| [实现与测试状态](docs/implementation-status.md) | 按需求和验收项记录的结果 |
| [接续记录](docs/agent-resume-context.md) | 开发过程与最新进度 |
| [开发任务](docs/roadmap.md) | 首期与后期任务 |

## 本地开发

后端安装 backend/requirements.txt，执行 backend/manage.py migrate 后启动开发服务器。前端在 frontend 目录安装 pnpm 依赖，运行 pnpm dev。账号初始化使用管理命令，口令通过私密环境配置提供，不使用部署面板口令。

本地 SQLite 可用于便捷开发；涉及事务与并发的验收应使用 PostgreSQL。前端生产构建和类型检查分别使用 pnpm build 与 pnpm typecheck。

## Docker 部署

提供 compose.yaml，服务为 web、api、worker、db。部署前准备 .env 和 secrets/db_password.txt，值参考 .env.example，私密文件不提交。

已有测试环境的安全更新使用 deploy/apply_release.py，按完整 Git 提交下载源码到独立 release 目录，备份后只替换 api、worker、web。APP_SOURCE_DIR 指定构建源码目录，APP_BUILD_VERSION 同时写入健康接口和镜像版本标签。三个现有命名卷保持不变。

本机无需运行 Docker daemon 来更新远端服务器，构建在目标 Docker 主机完成。具体执行方式见部署说明。

## 限制

首期仅校内访问、团队每队一张。个人证书、学生领取下载和独立防伪能力列为后期。图片不携带 PDF 数字签名，自签 PDF 的身份信任需由学校维护。备份仍在同机，不提供整机存储损坏后的灾备保证。

## 开源组件

前端基于 [vue-pure-admin](https://github.com/pure-admin/vue-pure-admin) 的官方精简版 [pure-admin-thin](https://github.com/pure-admin/pure-admin-thin)，沿用其组件及布局。保留上游 MIT 版权与许可，后端和其他依赖遵循各自许可证。
