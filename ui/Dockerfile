# syntax=docker/dockerfile:1
# Build the Vite/React SPA, then serve it from a small, non-root Nginx image.

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
# Upstream the SPA proxies /api to. Compose: app:8000. In K8s the ingress routes
# /api to the API service, so this is only used for direct/compose access.
ENV API_UPSTREAM=app:8000
# Templates are env-substituted on container start (only listed vars are replaced,
# so nginx's own $host/$uri are left intact).
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
