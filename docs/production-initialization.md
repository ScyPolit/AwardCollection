# 从测试环境转入生产

初始化与普通升级是不同操作。普通升级保留全部数据；只有部署方明确决定放弃测试业务后，才执行本页的初始化命令。程序不会在容器启动、数据库迁移或 Release 安装时自动清理数据。

## 保留与清理范围

私有初始化包保留一个指定的有效超管账号（包括原密码哈希）、所有未删除模板的最新可编辑版本、未删除字体、部门、公章及其图片版本、字体排序和查验配置。保留编号计数器，避免新证书重用旧测试证书的编号。模板和字体的维护人统一转为该超管。公章位的部门编号、字体引用和模板画布保持一致。

清理范围为其他账号、部门成员关系、竞赛、批次、获奖名单、证书、会签、生成与下载任务、通知、查验历史和测试审计记录。在线会话全部失效，完成后需用原超管账号重新登录。保留一条生产初始化审计记录。旧证书、ZIP、批次快照和临时文件从当前媒体目录清理，完整历史仍保存在独立备份中。

初始化包不复制部门签名私钥、测试证书、会话、业务历史或环境密钥。迁入新服务器后使用新的部署密钥，首次签发按部门生成新自签证书。现有实例初始化不会更换其部署密钥。自签名的信任范围仍由部署方管理。

## 两种模板包

- **公开模板包**：`python deploy/package_templates.py` 生成三款通用演示模板 ZIP 与 SHA256，默认在 `testTemp/release/`。可附在 GitHub Release，无校章、授权商业字体、账号或真实业务。
- **私有生产初始化包**：下面的 `production_seed export` 生成完整基础资料，包含密码哈希和学校素材。仅在受控服务器或本地私有目录保存；跨网络传输前加密，禁止作为公开 Release 附件。包中的 `templates/template-<id>.json` 可单独导入编辑器，字体和公章则需同时迁移。

## 在现有实例导出、核对及初始化

以下以当前 Compose 项目为例。先完成代码升级，再在维护窗口内暂停外部入口和 Worker，避免导出与清理期间继续提交业务。

```bash
# 在部署目录执行；先暂停入口及后台写入。
docker compose stop web worker

# 完整备份包含数据库、媒体、加密配置和 TLS，必须校验并具备恢复条件。
# 压缩级别 0 可缩短初始化维护窗口，需准备更多可用磁盘。
BACKUP_COMPRESSLEVEL=0 sh deploy/maintenance.sh backup

docker compose exec api python manage.py production_seed export \
  --superuser-id 1 --output /srv/backups/production-seed.zip
```

记录命令返回的 SHA256，并用实际值替换下面的 `<SHA256>`；`<完整备份目录>` 必须包含 `COMPLETE`、`SHA256SUMS` 及备份文件。

```bash
# 默认只预演，输出删除数量和保留数量。
docker compose exec api python manage.py production_seed reset \
  --bundle /srv/backups/production-seed.zip --sha256 <SHA256>

# 明确执行；只读挂载完整备份，程序会再校验全部备份文件。
docker compose run --rm --no-deps \
  -v <完整备份目录>:/verified-backup:ro api \
  python manage.py production_seed reset \
  --bundle /srv/backups/production-seed.zip --sha256 <SHA256> \
  --verified-backup /verified-backup --apply

docker compose restart api
docker compose up -d worker web
```

初始化前程序比较当前基础资料与导出包，模板或素材发生变化会拒绝继续。数据库清理在一个事务中执行；任务仍在运行、备份不完整、校验失败均拒绝清理。数据库成功提交后才清理指定的业务媒体目录；若文件权限导致后续清理失败，应修复权限并重跑同一命令，不得直接删除整个媒体卷。不要执行 `docker compose down -v`。

`maintenance.sh` 属于当前实例运维脚本，默认部署路径、Compose 项目名与备份位置仍沿用 `awardcollection-v1-test` 历史名称。迁入其他路径或项目时，应先按部署文档调整脚本，不能照抄实例专属路径。

## 在新服务器导入

使用 `deploy/init_env.py` 生成新配置并启动容器，先不要创建超管或其他资料。将解密后的私有 ZIP 通过受控方式放入备份卷后执行：

```bash
docker compose exec api python manage.py production_seed inspect \
  --bundle /srv/backups/production-seed.zip --sha256 <SHA256>

docker compose exec api python manage.py production_seed import \
  --bundle /srv/backups/production-seed.zip --sha256 <SHA256> --apply
```

只允许导入到已经执行迁移且没有账号、素材和业务的数据库；有资料时拒绝覆盖。文件路径、清单、大小、SHA256 和模型白名单会检查，失败时回滚数据库并删除本次创建的文件。账号保留原超管密码，部署后可在系统中更换；部署环境密钥和数据库口令由新服务器独立生成。

最后确认：仅超管可登录、模板缩略图和编辑画布正常、中文字体无缺字、公章预览正常、竞赛和证书列表为空、旧证书编号查验无记录、所有容器健康。正式验收可在隔离的数据库运行，不应往干净的生产库重新注入演示账号或测试业务。
