FROM node:20-alpine as build-stage

WORKDIR /app
RUN corepack enable
RUN corepack prepare pnpm@10.33.2 --activate

COPY .npmrc package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY ppt-editor/package.json ppt-editor/package-lock.json ./ppt-editor/
RUN npm --prefix ppt-editor ci --ignore-scripts
COPY . .
RUN pnpm build

FROM nginx:stable-alpine as production-stage
RUN apk add --no-cache openssl
ARG APP_BUILD_VERSION=development
LABEL org.opencontainers.image.revision=$APP_BUILD_VERSION

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY 40-award-tls.sh /docker-entrypoint.d/40-award-tls.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-award-tls.sh && chmod +x /docker-entrypoint.d/40-award-tls.sh
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080 8443

CMD ["nginx", "-g", "daemon off;"]
