# 部署配置

正式部署使用根目录 `compose.yaml`，为兼容已有数据卷，Compose 项目名保留 `awardcollection-v1-test`。首次安装执行 `python3 deploy/init_env.py --host <服务器IP或域名>`，自动生成 `.env` 和 `secrets/db_password.txt`，不会覆盖现有配置。所有实际密钥均不得提交 Git。

`web` 是唯一映射宿主机端口的服务；数据库仅存在于项目内部网络。首次启动前检查 HTTP 18080 与 HTTPS 18443 未占用。启动后执行 `docker compose exec api python manage.py createsuperuser` 创建自己的超管，无默认管理口令。

`APP_PUBLIC_HOST` 是不带协议或端口的 DNS 名称或 IPv4 地址，`APP_TLS_PORT` 决定 HTTPS 映射及 HTTP 跳转目标。HTTPS 首次启动生成自签证书；变更地址时应更新 `.env` 中的允许主机与 CSRF 来源，并自行维护证书的域名和有效期。已有 TLS 卷的证书不会被自动覆盖。
