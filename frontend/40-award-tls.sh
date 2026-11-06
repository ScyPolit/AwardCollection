#!/bin/sh
set -eu
public_host="${APP_PUBLIC_HOST:-localhost}"
case "$public_host" in
  ''|*[!a-zA-Z0-9.-]*) echo 'APP_PUBLIC_HOST must be a DNS name or IPv4 address' >&2; exit 1 ;;
esac
case "$public_host" in
  *[!0-9.]*) public_san="DNS:$public_host" ;;
  *) public_san="IP:$public_host" ;;
esac
if [ ! -s /etc/award-tls/server.key ] || [ ! -s /etc/award-tls/server.crt ]; then
  umask 077
  openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 365 -keyout /etc/award-tls/server.key -out /etc/award-tls/server.crt -subj "/CN=$public_host/O=AwardCollection" -addext "subjectAltName=$public_san,DNS:localhost,IP:127.0.0.1"
fi
cp /etc/award-tls/server.crt /usr/share/nginx/html/school-platform.crt
chmod 644 /usr/share/nginx/html/school-platform.crt
