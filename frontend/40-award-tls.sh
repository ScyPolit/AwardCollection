#!/bin/sh
set -eu
if [ ! -s /etc/award-tls/server.key ] || [ ! -s /etc/award-tls/server.crt ]; then
  umask 077
  openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 365 -keyout /etc/award-tls/server.key -out /etc/award-tls/server.crt -subj '/CN=192.168.31.12/O=Campus Certificate System' -addext 'subjectAltName=IP:192.168.31.12,DNS:localhost,IP:127.0.0.1'
fi
cp /etc/award-tls/server.crt /usr/share/nginx/html/school-platform.crt
