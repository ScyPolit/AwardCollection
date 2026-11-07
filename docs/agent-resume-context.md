# 当前交付上下文

更新时间：2026-11-07。应用地址为 https://192.168.31.12:18443，HTTP 18080 跳转 HTTPS；GitHub 为 https://github.com/ScyPolit/AwardCollection。

## 当前实例与数据保护

线上已有正式业务。必须保留全部当前账号、竞赛、批次、证书、模板与素材；不要再次执行 `clear_demo_business`、初始化测试业务、重置数据库或 `docker compose down -v`。2026-11-06 的清理授权已执行完毕，不适用于之后新增的数据。

本轮基线包括账号 id 1、13、14，以及批次 10 的 300 份已发布证书。模板 id=4 为“标准模板”，用户已在上次发布后继续编辑；禁止使用 11-06 的旧版本或旧摘要覆盖当前画布。发布器已比较全部模板版本摘要及历史证书样本，确认内容保留。当前部门、公章、导入字体和编号序列均保留。

Docker 项目名 `awardcollection-v1-test` 是历史名称，不表示允许清理测试数据。目录 `/opt/awardcollection-v1-test/app`；原数据库容器创建于 `2026-11-05T19:20:01.632110387Z`，原 db_data / media_data / backup_data / tls_data 命名卷保持不变。不要删除其他应用、镜像或数据卷。

## 本轮代码与运行版本

- 后端 / worker / converter：`6e722dc2f07b78fc8126a0686eb82ea8db677d3e`。
- 前端：`49418cf5fce37605494f822d9ea9187f6332b858`。
- 后续仅验收文档的提交不会改变镜像版本；健康接口显示后端版本，web 镜像标签显示前端版本。

502 已确认为旧打包接口重复加载大型模板快照，导致 1 GiB API 容器 OOM。现在后台任务分块准备并持久保存 ZIP，状态和通知提供服务器下载链接，由 Nginx 传输；客户端不构造整包 Blob。图片尺寸及生成并发受限，缺失 PNG 可从原签名 PDF 补生成而不重写 PDF。

权限统一到后台查询范围：竞赛负责人禁用公章 / 字体接口；部门管理员仅访问本部门公章及其参与审批的冻结批次、证书、下载与通知。历史审批范围不会给予重新分配竞赛的编辑 / 删除权限。前端路由同步隐藏无权菜单，列表、预览、表单选项和详情具有独立加载及失败提示。

证书编辑器已去除右上角 GitHub 图标、演示入口和“幻灯片”文案，预置四款常用奖状排版；保留添加页面、撤销、可视化编辑及格式导入导出。新增排版直接复用仓库演示模板和 PPTist 卡片组件，不修改线上标准模板。AGPL 许可和源码获取入口仍保留在菜单及开源声明中。

## 验证与回滚

本地及目标 PostgreSQL 各 87 项完整后端回归通过；最终后端 20 项权限 / 通知 / 作废专项通过。两个前端工程类型检查及生产构建通过。实际 300 份批次、600 个文件在禁用额外 swap 的 512 MiB 只读容器中完成 ZIP 打包与 CRC 检查，进程峰值 RSS 71.61 MiB，OOM 计数为 0。RSS 不包含全部容器文件缓存，不等同于容器总内存。

最终服务器链接完整 HTTPS 下载 2,001,382,026 字节，SHA256 与服务器一致，600 个 PDF / PNG 条目的 CRC 全部通过。原生浏览器自动保存被工具取消，不能宣称这一步成功；同一链接的完整传输已验证。真实证书 ZIP 与临时 cookie 已从本地验证目录删除，服务器正式下载包保留。

最后完整发布的备份：`/opt/awardcollection-v1-test/backups/20261107-081745-O7Ifmt`，数据库、媒体、加密配置与加密 TLS 的 SHA256 全部通过。后端检查点：`/opt/awardcollection-v1-test/rollback/20261107-081738`；最终前端检查点：`/opt/awardcollection-v1-test/rollback/web-20261107-084123`。

完整发布器为 `deploy/apply_release.py`。仅前端发布使用 `deploy/apply_web_release.py`，先比较 backend / converter 源码完全相同，再仅替换 web，并核对其余容器身份、命名卷和历史内容。不要因健康版本与文档提交不同而重复全量发布。

本轮证据见 [性能与权限验收](../artifacts/performance-release-20261107/REPORT.md)；11-06 的格式导入、签名与清理结果仅作历史参考，见 [历史验收](../artifacts/ppt-release-20261106/REPORT.md)。

## 凭据与开源

凭据仅在 Windows 私密 agent-handoff 目录的 DPAPI 文件及浏览器 auth profile 中；禁止打印、提交密码、会话、真实证书 ZIP、公章私钥或学生名单。`application-test.credential.xml` 保存当前应用超管凭据，`docker-manager.credential.xml` 用于 1Panel。不要擅自重置正式用户密码。

首次安装用 `deploy/init_env.py` 生成随机私密配置。PPTist 为 AGPL-3.0，完整发行物不能描述为全部 MIT。公开证据仅使用本地演示内容或脱敏统计。
