# 当前交付上下文

2026-11-06 本轮代码已完成、测试并部署。应用为 https://192.168.31.12:18443，HTTP 18080 跳转。运行提交 `3ca6d3870edd77bee12496fcd358d742b0acce19`，发布状态 done，数据库健康。

已完成 PPTist 编辑与格式导入、权限内 CRUD、结构化详情、实时通知 / 已读 / 深链接 / 进度、菜单图标、深色布局、上传与完整性防护、受限转换容器和自签 HTTPS。目标 PostgreSQL 75 项回归通过；实际新建两队双部门批次签发、四枚增量签名及导入流程通过。结果见 artifacts/ppt-release-20261106/REPORT.md。

按用户确认清理了全部测试业务，包括 ICAN 和全部非超管账号。只保留 superadmin、模板 id=4（已改名“标准模板”）及正式部门 / 公章 / 字体素材。模板最新版本 4，画布摘要 `5a84ce02e79ac548da11fb419f7df420f316969d4a5d2a2b6fc92f6b2e6a9fed` 未变。正式部门 6、公章 7 与导入字体文件摘要验证通过。编号序列 next_value=5613，审计保留；数据库断言各业务表为零。历史文档中保留批次 2 的要求已被本轮明确清理授权替代。

清理前备份 `/opt/awardcollection-v1-test/backups/20261106-131309-3Flhsk`，数据库、媒体、加密配置、加密 TLS 摘要均通过；回滚检查点 `/opt/awardcollection-v1-test/rollback/20261106-131302`。原数据库容器和三个旧命名卷保留。所有登录会话在清理后撤销。

开源首页已重写，原创 Logo / 封面在 docs/brand，截图在 docs/images，三款无真实素材的演示模板在 examples。GitHub 已推送，包括最新截图与验收文档。首次安装使用 deploy/init_env.py 创建随机私密配置，不使用测试初始化命令。PPTist 为 AGPL-3.0，不能将完整发行物描述为全部 MIT。

凭据只在 Windows 私密 agent-handoff 目录的 DPAPI 文件及浏览器 auth profile 中。application-test.credential.xml 已更新为用户指定的当前超管口令。禁止打印或提交任何密码、会话或私钥。

清理后备份：`/opt/awardcollection-v1-test/backups/20261106-132438-dWcAzt`。HTTPS 公钥证书下载 200，HTTP 跳转地址正确；api/web/db 健康，worker/converter 运行。清理后重新登录，模板库仅显示“标准模板”，视口无横向溢出。
