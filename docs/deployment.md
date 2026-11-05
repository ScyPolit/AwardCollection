# 部署说明

更新日期：2026 年 11 月 6 日。

## 当前状态

- 目标管理入口 `http://192.168.31.12:8888/manager` 实际识别为 **1Panel**。
- `192.168.31.12:8888` 与 SSH `22` 可达；候选应用端口 `18080` 未占用。
- 计划 Compose 项目为 `awardcollection-v1-test`，计划目录为 `/opt/awardcollection-v1-test`。
- 远端应用 URL 尚未产生。文档指定的 DPAPI 凭据文件不存在，SSH 也没有可用公钥，因而无法登录 1Panel、盘点主机、上传项目或启动容器。

缺失文件：`C:/Users/SCY-Polit/AppData/Local/AwardCollection/agent-handoff/first-release-20261106-8a1e/docker-manager.credential.xml`

恢复该文件后可继续部署，口令不应写入聊天、Git、镜像或本文档。

## 配置与启动

1. 将仓库放入独立目录并复制 `.env.example` 为 `.env`。
2. 在 `secrets/db_password.txt` 写入与 `POSTGRES_PASSWORD` 相同的随机数据库密码。
3. 为 `DJANGO_SECRET_KEY`、`SIGNING_KEY_PASSWORD`、`INITIAL_ADMIN_PASSWORD` 生成互不相同的随机值。
4. 执行 `docker compose -p awardcollection-v1-test up -d --build`。
5. 执行 `docker compose exec api python manage.py seed_demo --password '<独立测试密码>'`。
6. 使用 `http://192.168.31.12:18080` 验收。正式入口具备 HTTPS 后再开启 Secure Cookie、HSTS 和强制 HTTPS。

服务为 `web`、`api`、`worker`、`db`。PostgreSQL 不发布宿主机端口；数据库、正式文件、签名密钥和备份使用持久化卷。

## 备份与恢复

`deploy/backup.sh` 生成数据库 dump、受保护媒体归档、SHA256 清单和完成标记。`deploy/restore-drill.sh` 强制使用独立数据库 URL 和媒体目录，避免覆盖在线数据。

当前仅设计同机备份，未在目标服务器执行恢复演练。即使演练通过，也不能防护整机或同一存储整体损坏。

## 自签限制

各测试部门使用独立自签证书，PDF 以增量更新方式追加签名。数学签名完整不等于身份受信；学校需分发并管理信任根。图片不携带 PDF 数字签名，签名 PDF 原件必须长期保留。
