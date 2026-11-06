> 本轮更新：用户已明确要求清理 ICAN 和全部测试业务，只保留超管、模板 id=4 最新内容及正式素材。旧文档中“永久保留批次 2”的描述属于历史验收记录，不适用于本轮授权清理。新入口为 HTTPS 18443，HTTP 18080 在升级后自动跳转。实际部署结果将在本轮验收完成后补写。

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
- 字体：七款固定版本免费字体，摘要见 backend/font-assets/manifest.json；启动时缓存到媒体卷 protected/font-library/builtin。授权导入文件保存在 protected/font-library。历史 wqy-zenhei.ttc 保留供旧版兼容，运行时不访问字体服务。

## 运维命令

```bash
cd /opt/awardcollection-v1-test/app
docker compose -p awardcollection-v1-test ps
docker compose -p awardcollection-v1-test logs --tail 100 api worker web
docker compose -p awardcollection-v1-test up -d --no-build
```

升级前先备份，记录当前 Git 提交和镜像摘要，再构建更新。不能删除命名卷或全局清理 Docker。

构建前设置 `APP_BUILD_VERSION` 为待部署提交号。新版本健康接口返回该值，部署后应分别核对 `api` 健康响应和 `api/worker` 镜像标签。涉及后端与前端修改时使用 `docker compose build api worker web` 后再 `docker compose up -d --no-deps api worker web`；不要使用 `down -v`，不要删除或重建 `db_data`、`media_data`、`backup_data`。

已完成无损更新，实际运行提交 `246348db2092261433cfe2f8bafc338f62f03a64`。健康接口与 api、worker、web 三个镜像标签一致，DEBUG=false。批次 2 及其 5000 对 PDF/PNG 已核实保持原状，不重排任务或重新分配编号。最新审计见 artifacts/usability-v2-20261106/target-final-audit.json；首轮审计保留在 artifacts/release-20261106。

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

## 首轮交付记录（历史）

最终部署前备份为 `/opt/awardcollection-v1-test/backups/20261106-022637-DnI6Wx`，数据库、媒体及加密配置三个文件校验均通过。最后应用回滚检查点为 `/opt/awardcollection-v1-test/rollback/20261106-022631`。现有数据库容器保持运行，三个原命名卷保持不变。

目标 PostgreSQL 32 项测试通过，288.775 秒；最终批次 4 两队签发完成，两个 PDF、两个 PNG 和整批 ZIP 下载接口核实一致，四个 PDF 增量签名完整且数学有效。样张均为 TEST ONLY。

三个应用容器的 json-file 日志限制为每文件 10 MB、最多五份。维护日志由 /etc/logrotate.d/awardcollection 轮换，systemd 计时器已启用并处于 active。

升级已有环境可在目标主机执行：

```bash
python3 /opt/awardcollection-v1-test/app/runtime/apply-release-current.py <完整提交号>
cat /opt/awardcollection-v1-test/app/runtime/release-status.json
```

首次安装应按 .env.example 和 Compose 准备配置；该升级脚本明确依赖当前环境与受保护历史批次 2，并非通用初始化器。文档与测试证据的后续提交不会改变已运行镜像版本。

## 2026-11-06 交互与字体升级

模板商城复用 Pure Admin 官方 CardList 页面，固定源码和 MIT 许可见 docs/upstream/pure-admin-card-list。字体库入口为 /#/business/fonts，所有登录用户可导入、预览授权静态 TTF/TTC；重命名、停用和启用仅超管可用。内置黑体、宋体、楷体、仿宋和三个英文家族使用免费替代字体；学校指定的商业字体需由学校提供已有授权文件。

构建支持目标主机 /opt/awardcollection-v1-test/font-cache 的离线字体缓存。apply_release.py 逐文件验证 SHA256 后复制到源码构建目录；prepare_fonts.py 在全部文件匹配时无需外网下载。网络隔离部署应提前准备这七个 manifest 指定的文件，禁止用未经核验的同名字体替换。当前主机缓存已核验；不将缓存或私密配置推送到 Git。

最新升级备份 `/opt/awardcollection-v1-test/backups/20261106-071107-wdlX9W`，回滚检查点 `/opt/awardcollection-v1-test/rollback/20261106-071101`。完整50项PostgreSQL回归通过（447.454秒），最终图形空值与全员导入专项3项通过（26.073秒）。新增文字样式、绘图和校徽均已部署，完整验收见 artifacts/usability-v2-20261106/REPORT.md。


## 经过校验的离线 Python 依赖

backend/wheel-assets/manifest.json 固定本版 Linux x86_64 / CPython 3.12 的 wheel 文件名及 SHA256。每个摘要已与 PyPI 官方版本元数据核对；二进制文件不进入 Git。

可将完整缓存放在 /opt/awardcollection-v1-test/wheel-cache/linux-cp312-amd64。发布脚本先按该版本清单逐文件验证，再复制到构建目录并写 READY 标记；Docker 构建再次校验后使用 pip --no-index。没有缓存的首次环境仍支持联网安装。约束更新时需同步重建对应平台的清单和缓存，不得跳过校验或改用同名未核实文件。

大文件 FileResponse 在 ASGI 下采用 64 KB 异步分块读取，避免将整个证书 ZIP 载入 API 内存。

本版后端构建使用中科大 Debian HTTPS 镜像，继续保留 Debian 官方签名验证；镜像说明：https://mirrors.ustc.edu.cn/help/debian.html 。运行服务不依赖该镜像站。
