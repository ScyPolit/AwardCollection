# 当前交付上下文

更新时间：2026-11-08。应用地址为 https://192.168.31.12:18443，HTTP 18080 跳转 HTTPS；源码仓库为 https://github.com/ScyPolit/AwardCollection。

## 生产初始化已完成

用户已经确认本次清理范围，初始化已执行成功。不能再次把这份授权用于清理后续正式业务。当前仅保留原超管、标准模板及字体、公章、部门和配置；竞赛、批次、证书、通知和非超管账号均已清理。原超管密码不变，旧登录会话已撤销，需重新登录。

保留模板 id=4「标准模板」及最新版本记录 id=21，画布摘要与初始化前一致。旧模板版本已收敛到该最新版本；2 款导入字体（华文行楷、宋体）、7 款内置字体、2 个部门、1 枚公章及其图片版本保留。字体与模板维护人统一为超管。编号计数器保留，避免再次使用旧证书编号。

Docker 项目名 `awardcollection-v1-test` 只是历史名称。应用目录 `/opt/awardcollection-v1-test/app`；原数据库容器创建于 `2026-11-05T19:20:01.632110387Z`，原 db_data / media_data / backup_data / tls_data 卷保持不变。后续更新必须保留正式数据，不得删除卷或操作其他应用。

## 功能与版本

v1.0.0 的业务代码以 `e6764c490e203e1c8d58a3e0f1c1d4da70de99d3` 为验收基础。随后的运维和文档提交不改变 backend、frontend、converter 或 Compose 业务配置。正式发布时四个应用服务统一使用 Release 标签对应的完整提交，实际版本以健康接口、镜像 revision 标签与 `runtime/release-status.json` 为准。

负责人只能直接编辑自己的个人模板；其他人的共享模板必须复制，副本默认私有，作者可决定共享。部门模板由当前有效部门管理员管理，创建人身份不能绕过已撤销的部门权限。列表、详情、保存、缩略图、下载和批次模板选择共用服务端权限规则。超管可管理全部模板。

编辑器顶部的格式导入说明已移除；工具栏换行时，画布占满剩余空间。复制后地址同步到新模板。原有多页面、导入导出和编辑功能保留。

临时脚本、日志、下载和构建证据集中在 `testTemp/`；根目录 `.tmp-*` 已移入 `testTemp/history/`。私有素材位于 `resources/private/`，默认本地 SQLite 与媒体位于 `testTemp/development/`。这些资料不进入 Git；正式自动化测试仍在 `backend/awards/test_*.py`。

## 初始化、交付包与备份

- 清理前完整停机快照：`/opt/awardcollection-v1-test/backups/20261108-090825-DL3xsu`。包含数据库、媒体、加密部署配置和加密 TLS。TLS 最初因 Web 暂停被旧脚本跳过，已从同一未变更的卷补齐，证书指纹一致。
- 清理后完整基线：`/opt/awardcollection-v1-test/backups/20261108-093147-mUtCTg`。实际暂停 Web 后完成备份，四项摘要通过，TLS 身份不变。
- 私有包：`/opt/awardcollection-v1-test/private/production-20261108/production-seed.zip`；同目录存加密副本 `production-seed.p7m`。目录 700、文件 600。本地位于 `testTemp/production-release-20261108/private/`，仅当前 Windows 用户可访问。
- 初始化记录：`runtime/production-release-20261108/initialization-status.json` 及前后盘点、预演、实际报告，最终状态为 `done`。

私有包包含原超管密码哈希、学校模板、授权字体及公章图片，禁止提交 Git 或上传公开附件。它不含业务、会话、部署密钥或公章签名私钥。加密传输后已在本机解密并核对 ZIP CRC 与 SHA256。公开 Release 仅附三款通用示例模板及校验文件。

`production_seed` 支持导出、校验、预演、现有实例清理和全新数据库导入。清理要求完整备份且基础资料指纹不变；新环境导入拒绝覆盖已有资料。见 [生产初始化指南](production-initialization.md)。不要复用历史硬编码测试 ID 的清理命令。

`deploy/maintenance.sh` 已修复暂停 Web 时遗漏 TLS：通过不启动 Nginx、不发布端口的一次性容器读取现有卷，TLS 缺失或归档验证失败不能标记备份成功。备份解密密钥应独立保管，单机备份不能防护整机损坏。

## 验证与后续部署

目标 PostgreSQL 隔离数据库 145 项测试全部通过，测试库已销毁，测试容器未挂载生产媒体。覆盖模板权限、角色撤销、初始化包完整性、事务清理、新环境导入及编号计数器。两个前端类型检查、生产构建、Compose 配置及迁移一致性检查通过。本地浏览器验证了复制、私有保存、共享切换、刷新定位及编辑器布局。

初始化后线上只读验收：原超管登录成功；模板 1、字体 9、竞赛/批次/证书均 0。不应为验收重新注入测试业务。完整记录见 [v1.0.0 生产交付](production-delivery-v1.md)。

完整发布器 `deploy/apply_release.py` 要求固定提交及经过 SHA256 验证的源码归档。`--verified-backup-path` 可复用已验证完整备份；`--web-build-network host` 仅用于构建阶段。常规升级保留会话，不自动清库。仅前端更新可用 `apply_web_release.py`，会核对后端源码未变。

生成算法和速度未调优：渲染并发 1、Worker 2 GiB 保持不变。ZIP 在服务器准备后由 Nginx 下载，客户端不构造整包 Blob。应用不限下载速度；服务器链路协商 100 Mbps，历史实际浏览器下载约 10.83 MB/s。提高物理链路速率需要排查网络设备，不应擅自改网卡配置。

## 凭据与开源

凭据仅在 Windows 私密 agent-handoff 目录的 DPAPI 文件及浏览器 auth profile 中，禁止打印或提交密码、会话、真实证书包及私钥；不要擅自重置超管密码。首次安装由 `deploy/init_env.py` 生成独立私密配置。

原创业务代码采用 MIT，修改版 PPTist 遵循 AGPL-3.0，不可把完整发行物描述为全 MIT。自签证书不提供公共信任链；生产部署应配置可信 HTTPS、限制管理入口并维护可恢复备份，不承诺绝对安全。

此前 11-06 至 11-08 的业务验收数据已按本次授权清理，历史报告不表示当前还有那些账号或证书。
