# 开发接续上下文

更新：2026-11-06，Asia/Shanghai。当前用户体验、全员字体导入、文字样式、绘图及校徽改进均已完成开发、测试和无损部署。应用 http://192.168.31.12:18080 ，仓库 https://github.com/ScyPolit/AwardCollection 。

## 当前运行

实际运行 `246348db2092261433cfe2f8bafc338f62f03a64`，api/worker/web标签和健康接口一致，DEBUG=false。完整50项回归运行于623c35f，447.454秒；最终仅收紧图形空缺字段和调整授权文字，在当前版本运行3项相关专项，26.073秒。前端类型检查、2.34MB构建通过。本地50项103.137秒通过，随后输入校验3项再次通过。

所有登录用户可导入和预览授权TTF/TTC，字体管理重命名/启停仍仅超管；负责人在只读模板也能导入，但不能编辑模板。字体SHA256固定内容，停用保留历史文件。字形和排版共用后端布局，渲染进程预解析字体路径，不查询字体ORM。

文字bold/italic/underline可组合，图形支持rect/ellipse/line/freehand、颜色、尺寸、线宽、填充和层级。每条1000点、全模板5000点、80图层限制，缺失几何被拒绝。SVG和PDF几何一致；PNG从PDF渲染。

商城沿用Pure Admin官方CardList，源文件和MIT许可位于docs/upstream/pure-admin-card-list。全局校徽来自用户PNG左侧，school-emblem.svg嵌入原图并以68×68视口截取，加白底保证深色可见。

负责人为competition_owners全局组，无部门绑定；旧OWNER行只保留历史/回滚，不参与授权。超管继承管理员，普通审批保留本人回避。竞赛废止阻止新业务、保留原证书。信息详情和账号提交均已修复。

## 数据与禁止操作

禁止重排队、重签发或重新编号批次2：issued、5000条、5000PDF和5000PNG，原样本摘要一致。批次3/4为上轮原件，批次5为本轮早期字体与权限验收（5007/5008），继续保留。

最终样式批次6：竞赛4、模板3的版本ID6（第3版）、两队、编号5009/5010，2/2会签、done=2/2、attempts=1、无错误。模板含三种文字样式、四类图形和负责人导入的Mono字体；两PDF四个签名intact/valid=true，self-signed trusted=false，ZIP一致。PDF包含5条以上矢量路径和加粗轮廓。

TEST ONLY部门id4/id5、公章id5/id6、负责人test_v2_owner_20261106和管理员test_v2_adminb_20261106为隔离验收数据。负责人无部门成员行。测试竞赛和导入字体均恢复/保持启用。签发审批由超管普通批准A、部门B管理员批准B。

## 部署与工具

Ubuntu24.04、Docker29.1.2，Compose项目awardcollection-v1-test。稳定目录/opt/awardcollection-v1-test/app；APP_SOURCE_DIR指向releases，不能将稳定目录旧源码当当前镜像源码。原db/media/backup三个命名卷与数据库容器保留。

最终备份 `/opt/awardcollection-v1-test/backups/20261106-071107-wdlX9W`，回滚检查点 `/opt/awardcollection-v1-test/rollback/20261106-071101`。备份晚于样式批次完成，包含新字体、模板和证书。字体离线缓存/opt/awardcollection-v1-test/font-cache按manifest校验；启动时缓存到媒体卷protected/font-library/builtin。timer active/enabled，日志10m×5。

凭据仅在用户本机受限目录的DPAPI XML：application-test.credential.xml、v2-target-qa.credential.xml等；密码不写仓库/报告。已有更新器apply-release-current.py只重建api/worker/web，不删除卷或重建数据库。

agent-browser使用命名会话并保持NO_PROXY/no_proxy=192.168.31.12,localhost,127.0.0.1；原生exe支持stdin。页面加载、弹窗动画和绘图后的排版完成后再操作。部署后刷新加载新资源；异步wait函数可能只返回一次false，读取真实任务状态后再认定完成。

## 证据和边界

最新报告artifacts/usability-v2-20261106/REPORT.md，target-final-audit.json、postgres-regression-final.txt和postgres-focused-final.txt；新输出target-5009/5010.pdf/.png、target-batch-6.zip和target-styles-signatures-fonts-zip.json。旧首期证据保留在artifacts/release-20261106。

没有重跑5000队或补测其历史生成期延迟；未对最新worker额外做中断、租约抢占和大包内存峰值注入。CLI原生下载事件受限，以同一认证会话核实正式HTTP接口。自签信任、同机备份、图片不含数字签名和后期独立防伪范围保持明确。
