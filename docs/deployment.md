# 部署指南

本指南区分首次安装与已有实例升级。首次安装不创建演示账号，现有实例更新必须保留数据卷。

## 首次安装

准备 Linux Docker Engine、Docker Compose 插件和 Python 3，在仓库根目录执行：

```bash
python3 deploy/init_env.py --host <服务器IP或域名>
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec api python manage.py createsuperuser
```

浏览器访问 `https://<服务器IP或域名>:18443`。默认 HTTP `18080` 跳转到 HTTPS。初始化工具生成随机密钥及一致的数据库口令，已有 `.env` 或数据库口令文件时拒绝覆盖。

登录后创建部门与账号、上传有权使用的公章、建立并发布模板，再创建竞赛。可导入 [演示模板](../examples/README.md)，正式签发前需增加每个盖章部门的公章位。不要运行测试初始化或一次性测试清理命令来建立正式系统。

## 地址与 HTTPS

| 配置 | 作用 |
| --- | --- |
| `APP_PUBLIC_HOST` | 不含协议和端口的 DNS 名称或 IPv4 地址 |
| `APP_PORT` / `APP_TLS_PORT` | HTTP / HTTPS 宿主机映射端口，默认 18080 / 18443 |
| `DJANGO_ALLOWED_HOSTS` | 允许访问的 Host 列表 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 包含协议及端口的可信来源列表 |
| `APP_BUILD_VERSION` | 健康接口和镜像中显示的源码版本 |

更改访问地址时同步调整 Host、CSRF 及 HTTPS 证书。首次启动会在 TLS 卷中生成自签服务器证书；已有证书不会被自动替换。浏览器默认不信任自签证书，应通过可信渠道核对和分发，或换成本单位认可的证书。服务器公钥证书可从 `/school-platform.crt` 下载，私钥不能公开。

自签 HTTPS 证书与部门 PDF 签名证书用途不同。PNG 不携带 PDF 数字签名；自签 PDF 的身份信任由部署方维护。

## 服务与持久化

服务为 `web`、`api`、`worker`、`db`、`converter`，只有 `web` 映射宿主机端口。PostgreSQL 不对外发布；Office 转换器位于内部网络，以非 root、只读根文件系统和资源限额运行。

为兼容已有实例，项目名保留 `awardcollection-v1-test`；该名称不代表会自动初始化测试业务。

| 命名卷 | 保存内容 |
| --- | --- |
| `awardcollection-v1-test_db_data` | PostgreSQL 数据 |
| `awardcollection-v1-test_media_data` | 证书、模板素材、字体及部门签名密钥 |
| `awardcollection-v1-test_backup_data` | 应用备份目录 |
| `awardcollection-v1-test_tls_data` | HTTPS 服务器证书及私钥 |

`.env`、`secrets/db_password.txt` 和备份加密密钥不进入 Git。不要执行 `docker compose down -v` 或全局卷清理。

## 更新已有实例

先备份并记录源码提交与镜像摘要，再在确认的完整提交上构建。数据库容器及命名卷保持不变。升级后核对健康接口版本、容器状态、登录、会签与小批次生成。

当前验收主机的专用发布器是 `deploy/apply_release.py`：将固定提交下载到独立 release 目录，验证缓存，备份后更新 `api worker web converter`；检查历史模板与文件摘要；失败时尝试回退应用镜像与配置，不自动覆盖数据库。其基础目录、项目名和地址针对已有实例，不是通用安装器。

仅前端改动可使用 `deploy/apply_web_release.py`，参数同样要求固定提交、归档与 SHA256。发布器逐文件核对后端和转换服务源码完全相同，才允许只重建 web；API、worker、数据库和转换容器的身份及创建时间必须保持不变。`WEB_SOURCE_DIR` 和 `WEB_BUILD_VERSION` 仅覆盖 web，未设置时沿用应用配置。全量发布器会同步重置两个 web 配置。

离线源码可通过 `--archive` 与 `--archive-sha256` 指定，要求归档位于该实例的 incoming 目录且摘要匹配。不能以未经核验的同名文件代替依赖。

常规升级保留现有登录会话。只有身份认证变更确实需要主动撤销登录时，使用 `--rotate-sessions`，撤销操作会记入审计。

## 备份与恢复

已有实例使用 `deploy/maintenance.sh backup`。数据库 custom dump、媒体归档、加密配置和加密 TLS 归档保存在实例外层 backups 目录，并写入 `SHA256SUMS` 与 `COMPLETE`。部署配置与 TLS 归档使用受限的 `runtime/backup-encryption.key` 加密，该文件应另行安全备份。

数据库与媒体归档包含敏感材料，应限制访问并在迁移或异机保存时加密。默认同机备份不能防护整机损坏。恢复应先在隔离环境验证数据库、媒体、配置和密钥一致，再决定正式切换。

已有实例的 systemd 维护计时器每日北京时间 02:30 后执行备份及过期临时文件清理，失败记录日志并尝试通知超管。正式证书与业务审计不在日常临时文件清理范围。

## 字体与离线依赖

七款内置字体的来源、许可和摘要见 [字体说明](../backend/font-assets/README.md)。目标主机缓存目录为 `/opt/awardcollection-v1-test/font-cache`，构建时逐文件验证摘要。导入商业字体前必须具备使用、嵌入及转换授权。

Python Linux x86_64 / CPython 3.12 离线 wheel 清单位于 `backend/wheel-assets/manifest.json`。本版 44 个 wheel 的摘要已与 PyPI 官方元数据核对；原始文件不进入 Git。发布器验证缓存后复制到构建上下文，镜像内再次验证，再通过 `pip --no-index` 安装。没有缓存时允许联网安装；更新依赖时需同时更新约束与对应平台的清单。

后端构建使用中科大 Debian HTTPS 镜像，保留 Debian 官方签名验证；运行服务不依赖该镜像站。

## 2026-11-06 历史验收

内网地址为 `https://192.168.31.12:18443`，HTTP 18080 跳转；这不是公开在线演示站。主机为 Ubuntu 24.04、Docker 29.1.2，项目目录 `/opt/awardcollection-v1-test/app`。

运行提交：`3ca6d3870edd77bee12496fcd358d742b0acce19`。发布检查点 `/opt/awardcollection-v1-test/rollback/20261106-131302`；清理前备份 `/opt/awardcollection-v1-test/backups/20261106-131309-3Flhsk` 的数据库、媒体、加密配置与 TLS 四项摘要均通过校验。

75 项目标 PostgreSQL 回归通过。新建两队双部门批次完成 2/2，PDF / PNG 和 ZIP 可下载，两个 PDF 各有两个完整且数学有效的增量签名；自签信任警告符合预期。已核对通知跳转、已读持久化和无需刷新显示生成结果，PPTX 与旧 PPT 导入后可编辑并保存。

测试业务按系统所有者明确要求清理，保留超管、模板 id=4 最新内容及正式素材。旧文档中“永久保留批次 2”属于历史验收要求，已被本次授权替代。编号序列不重置，审计保留。详细结果见 [本轮验收](../artifacts/ppt-release-20261106/REPORT.md)。后续纯文档提交不会改变已运行镜像的版本号。

## 2026-11-07 权限、下载与编辑器更新

后端运行 `6e722dc2f07b78fc8126a0686eb82ea8db677d3e`，前端运行 `49418cf5fce37605494f822d9ea9187f6332b858`。最终前端使用仅 web 发布器，API / worker / db / converter 均未因前端更新重建。线上已产生新的正式业务，必须保留全部现有账号和数据，不能重用上一节的历史清理授权。

完整升级前备份 `/opt/awardcollection-v1-test/backups/20261107-081745-O7Ifmt` 的四项摘要通过；后端回滚检查点 `/opt/awardcollection-v1-test/rollback/20261107-081738`，最终前端检查点 `/opt/awardcollection-v1-test/rollback/web-20261107-084123`。

批量 ZIP 改为服务器后台落盘，再经鉴权由 Nginx 发送；可用 Range 下载，客户端无需整体读取为 Blob。工作进程生成并发默认 1，PNG 像素数量受限。512 MiB、无额外 swap 的只读容器完成实际 300 份 / 600 文件打包及 CRC 检查，进程峰值 RSS 71.61 MiB；这是打包验证，不代表整个数据库、转换器和 Web 应用能够共同运行在 512 MiB 主机上。

目标 PostgreSQL 87 项全量回归及最终 20 项权限 / 通知专项通过，类型检查和生产构建通过，正式模板与历史证书摘要保留。完整证据见 [本轮验收](../artifacts/performance-release-20261107/REPORT.md)。

## 2026-11-08 用章审批、批次档案与批量管理更新

api / worker / web / converter 均运行 `405309b81871c06a65d2ecb17de59c03085c50d5`。迁移0013允许公章引用待定，由各部门管理员在审批详情确认本部门用章；已批准部门不可改章。管理员与超管可审批本人提交或修改的批次，全部部门会签要求保留。证书档案改为按批次延迟展开，业务列表增加权限内批量操作。

目标隔离 PostgreSQL 116 项全量回归通过，未挂载生产媒体，测试数据库已销毁。升级前备份 `/opt/awardcollection-v1-test/backups/20261108-052222-EhBDkv` 四项SHA256全部通过，回滚检查点 `/opt/awardcollection-v1-test/rollback/20261108-052215`。300份正式证书、8个模板版本、全部账号及原数据库容器保持；常规升级没有撤销现有登录会话。

下载链路已显式取消应用限速。服务器到验收客户端经 `eno1`，物理协商100 Mbps / 全双工，理论上限12.5 MB/s；提高到千兆需要排查网线、交换机端口和服务器网卡协商，不能靠增大应用缓冲突破。完整证据见 [本轮验收](../artifacts/workflow-release-20261108/REPORT.md)。

实际Chrome经登录与界面完成2,001,382,026字节原生HTTPS下载，184.72秒、平均10.83 MB/s；300个PDF和300个PNG通过CRC校验，客户端SHA256与服务器原文件摘要一致。下载完成后已删除验收电脑上的真实ZIP。

## 2026-11-08 交付版更新

四个应用服务统一运行 `ebc61342a10cd1b8b1b782ca9d5c456435c835d4`，迁移0014/0015已应用。目标隔离PostgreSQL133项回归全部通过。完整备份 `/opt/awardcollection-v1-test/backups/20261108-075100-e3zIfi` 四项摘要校验通过，检查点 `/opt/awardcollection-v1-test/rollback/20261108-075052`；901份证书、12个模板历史、原数据库容器及所有命名卷保留。

查验改为无验证码、每来源IP滚动60秒60次，共享公开/内部额度。公开字段、脱敏和结果水印由超管在编号查验设置；新证书编号去横线，历史编号兼容。字体顺序可管理，负责人可编辑模板及119×119公章位，真实用章仍由部门管理员确认。提交时缓存首张样张，导入/编辑按钮随状态禁用，进度以流程展示。会签待办有已通过审批；管理员撤回本部门批准后，目标修订已签发证书立即作废并退回，保留原件、意见和审计。

本次使用同一提交已验证的镜像部署，避免重复下载依赖的超时；运行源码、依赖锁文件及完整性检查保持一致。浏览器旧页面刷新一次加载新版，原登录会话保留。841MB现有下载包HEAD200、Range206验证通过；生成并发1及worker2GiB未调优。详见 [交付验收](../artifacts/delivery-release-20261108/REPORT.md)。
