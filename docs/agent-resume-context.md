# 首版开发接续上下文

更新：2026-11-06，Asia/Shanghai。本文件为当前状态，早先“凭据缺失、尚未部署”的结论已经失效。

## 当前结果

本轮无损部署、目标回归和 GitHub 代码推送已完成。应用为 http://192.168.31.12:18080 ，GitHub 为 https://github.com/ScyPolit/AwardCollection 。实际运行代码提交为 `b136df831171bb6bbb64a948411c41c7b8ad3808`；其后的提交只补交测试证据和文档。

- api、worker、web 的镜像版本标签与健康接口一致；DEBUG=false，三个应用容器配置每文件 10 MB、最多 5 文件的日志轮换。
- 目标 PostgreSQL 32 项测试全部通过，288.775 秒。最初一次回归暴露测试中直接关闭流式响应导致事务连接被关闭；已改为通过 Django 测试客户端读取完整流后清理，最终完整重跑通过。
- 前端 pnpm typecheck、生产构建、Compose 配置验证通过。Pure Admin 模板继续作为前端基础。
- 浏览器真实完成复制模板、上传背景、文字拖放和字号修改、双部门测试公章上传、负责人创建竞赛与批次、Excel 导入、服务端预览、两位管理员会签及自动签发。
- 最终批次 4：两队，done=2/2，一次尝试，无错误；编号 2026-AC-00005005、2026-AC-00005006。PDF/PNG 均存在，全部发布时刻一致。四个增量签名 intact/valid=true，信任为预期的自签状态。
- 图片下载扩展名修正为 .png；批次详情提供下载整批 ZIP。ZIP 超过 8 MB 后使用临时磁盘，实测四个文件与单张下载逐字节一致。
- PDF 数字签名使用不可见字段，画面保留模板配置的实际部门公章，不再叠加签名库默认说明框。
- 负责人可读取本部门启用公章的版本元数据以选章，不能取得原图或修改公章。超管可新建部门，管理员可关联已有负责人且不重置密码，越权授权有测试。

## 禁止重置的历史数据

批次 2 仍为 issued，5000/5000，5000 条证书、5000 PDF、5000 PNG，三份原样本摘要与记录一致。不得重跑、重排队或重新分配编号。所有更新均保留三个现有命名卷，不重建数据库容器。

批次 3 为本轮首次浏览器验收数据，编号 5003/5004，保留其原件；其默认签名说明框的问题已在后续代码修复。批次 4 是最终版输出证据。所有素材和数据均明确为 TEST ONLY。

## 部署与维护

- 主机 Ubuntu 24.04，Docker 29.1.2；1Panel http://192.168.31.12:8888/manager 。
- Compose 项目 awardcollection-v1-test，稳定目录 /opt/awardcollection-v1-test/app 。
- 源码目录由 APP_SOURCE_DIR 指向独立 releases 目录，不能假定稳定目录内的旧源码就是当前镜像源码。
- 命名卷 awardcollection-v1-test_db_data、awardcollection-v1-test_media_data、awardcollection-v1-test_backup_data。
- 本轮最后部署前备份：`/opt/awardcollection-v1-test/backups/20261106-022637-DnI6Wx`，三个文件 SHA256 校验通过，有 COMPLETE。
- 本轮最后回滚检查点：`/opt/awardcollection-v1-test/rollback/20261106-022631`。升级失败会回退应用镜像和配置，不自动覆盖数据库。
- awardcollection-maintenance.timer 已 active/enabled，每日北京时间 02:30 后随机延迟最多五分钟执行本机备份及七天前临时文件清理。维护日志有 logrotate；清理实跑删除 0 个过期临时文件。
- 私密配置与部署账号均不进 Git。已恢复面板 DPAPI 凭据，并在相同受限目录保存应用测试账号 DPAPI 凭据 application-test.credential.xml；不在日志回显口令。

## 证据与验证边界

最终审计：artifacts/release-20261106/target-final-audit.json 。目标测试全文：postgres-regression-final.txt 。签名检查：signature-verification.json 。最终输出：issued-5005/5006.pdf、.png 及 batch-4-certificates.zip 。浏览器截图与可复核脚本保存在同目录。

浏览器自动化的原生下载事件在本机被取消，已通过相同已认证浏览器会话读取原下载接口，核实 HTTP 200、附件头、文件内容及 ZIP 一致性；不将该 CLI 事件当作人工浏览器下载行为已经测完。管理员免验证码和访客验证码查验已在浏览器实际成功。

A29 仍为部分验证：旧 5000 队生成确已完成，生成期间查询延迟没有历史测量数据；本轮没有重跑 5000 队。新 worker 的强制中止、租约抢占及大包下载内存峰值也没有在本轮额外做故障注入/压力实测。不能把普通小批次成功写成全部并发、恢复和安全场景均已验收。

当前仍为同机备份、自签身份和校园网测试环境；图片本身不携带 PDF 数字签名。独立防伪、学生凭编号下载及商业签章等继续按原后期任务管理。

## 工具接续

agent-browser 使用独立命名会话，每次保持 NO_PROXY/no_proxy=192.168.31.12,localhost,127.0.0.1 。页面路由变化、API 异步加载和弹窗动画后，先等实际目标元素再操作；应用更新后刷新页面以加载新资源。Windows npm 包装器不传 stdin 时，使用原生 agent-browser-win32-x64.exe。

后续只在有新需求、失败或证据缺口时扩大验证，不要为了恢复上下文而重复签发历史批次。
