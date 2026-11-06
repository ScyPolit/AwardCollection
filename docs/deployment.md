# 部署说明

更新日期：2026 年 11 月 6 日。

## 已部署环境

| 项目 | 实际值 |
| --- | --- |
| 应用地址 | `http://192.168.31.12:18080` |
| 管理面板 | 1Panel v2.0.13，`http://192.168.31.12:8888/manager` |
| 操作系统 | Ubuntu 24.04 LTS，x86_64，Linux 6.8.0-147 |
| 主机资源 | 32 逻辑核，约 252 GB 内存 |
| Docker | 29.1.2，linux/amd64 |
| Compose 项目 | `awardcollection-v1-test` |
| 项目目录 | `/opt/awardcollection-v1-test/app` |
| 入口端口 | `18080`，部署前确认未占用 |

服务为 `web`、`api`、`worker`、`db`。PostgreSQL 不发布宿主机端口；项目使用独立网络和命名卷，没有修改现有容器、网络、卷、80/443 或 1Panel 端口。

## 持久化与配置

- 数据库卷：`awardcollection-v1-test_db_data`
- 正式文件、字体和签名密钥卷：`awardcollection-v1-test_media_data`
- 备份卷：`awardcollection-v1-test_backup_data`
- 私密配置：项目目录 `.env`、`secrets/db_password.txt`、`runtime/test-password.txt`，权限限制为部署管理员可读，均不进入 Git。
- 中文字体：项目媒体卷 `/srv/media/fonts/wqy-zenhei.ttc`，运行时不访问外部字体服务。

## 运维命令

```bash
cd /opt/awardcollection-v1-test/app
docker compose -p awardcollection-v1-test ps
docker compose -p awardcollection-v1-test logs --tail 100 api worker web
docker compose -p awardcollection-v1-test up -d --no-build
```

升级前先备份，记录当前 Git 提交和镜像摘要，再构建更新。不能删除命名卷或全局清理 Docker。

构建前设置 `APP_BUILD_VERSION` 为待部署提交号。新版本健康接口返回该值，部署后应分别核对 `api` 健康响应和 `api/worker` 镜像标签。涉及后端与前端修改时使用 `docker compose build api worker web` 后再 `docker compose up -d --no-deps api worker web`；不要使用 `down -v`，不要删除或重建 `db_data`、`media_data`、`backup_data`。

当前执行环境已找到原加密面板凭据，正在执行无损更新。最终部署状态以健康接口与三个镜像的版本一致性核对为准。批次 2 及其 5000 对 PDF/PNG 保持原状，不重排任务或重新分配编号。

## 备份与恢复

2026-11-06 已在目标服务器执行本机备份：

- PostgreSQL custom dump：约 121 KB（首个体验批次时）
- 媒体、字体和密钥归档：约 9.0 MB（首个体验批次时）
- 包含 `SHA256SUMS` 与 `COMPLETE` 标记

随后使用独立临时 PostgreSQL 17.6 容器和独立临时卷恢复，核对到：`batches=1`、`certificates=2`、`approvals=2`，媒体归档包含两份签名 PDF 及两个部门 P12 密钥。演练后临时容器和临时卷已删除。

当前仍是同机备份，不能防护整机或同一存储整体损坏。正式使用前应配置异机备份。

## 自签限制

测试部门使用独立自签证书，PDF 以增量更新方式追加签名。数学签名完整不等于公共 CA 身份信任；正式部署需由学校维护和分发信任根。图片不携带 PDF 数字签名，签名 PDF 原件必须长期保留。

## 发布脚本与维护

apply_release.py 使用完整 Git 提交号定位公开源码。构建来自独立 releases 目录；稳定 app 目录保存 Compose、私密配置及 runtime。更新前记录回滚镜像并备份，更新时只重建 api、worker、web，不重建数据库容器。失败时回退应用镜像和配置，不自动覆盖数据库。

maintenance.sh 通过现有数据库容器的 pg_dump 备份，避免客户端版本不兼容。数据库、媒体和加密的部署配置保存于 /opt/awardcollection-v1-test/backups。配置加密口令保存在受限的 app/runtime/backup-encryption.key，不能提交或公开。恢复配置时需要该文件，整机损坏仍属于当前恢复限制。

install-maintenance.sh 安装本项目独立的 systemd 服务和计时器，每日北京时间 02:30 后执行备份与七天前临时文件清理。失败写入 app/runtime/maintenance.log，并尝试向超管发送站内消息。正式证书和业务审计不在清理范围。
