# syntax=docker/dockerfile:1.7

############################
# 1) Builder: Node 22+ (glibc)
############################
FROM node:22-bookworm-slim AS builder
WORKDIR /app

# Optional: pass Vite env at build-time (baked into bundle)
#   docker build --build-arg VITE_API_BASE=http://localhost:8000/api/v1/tasks ...
ARG VITE_API_BASE=/api/v1/tasks
ENV VITE_API_BASE=${VITE_API_BASE}

# Copy ONLY package.json so we install from scratch (no lockfile)
# If your project is under ./ui, change to: COPY ui/package.json ./
COPY ui/package.json ./

# Use public npm registry; cache npm to speed up rebuilds
RUN --mount=type=cache,target=/root/.npm \
    npm config set registry https://registry.npmjs.org/ \
 && npm --version \
 && npm install --no-audit --no-fund

# Now bring in the rest of your sources and build
# If your app is inside ./ui, change to: COPY ui/ ./
COPY ui/ ./
# Build your app (expects "build" script in package.json → e.g., "vite build")
RUN npm run build

###################################
# 2) Runner: Nginx to serve /dist
###################################
FROM nginx:alpine
# Remove default and add a minimal SPA config
RUN rm /etc/nginx/conf.d/default.conf
COPY <<'NGINXCONF' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri /index.html;
    }
}
NGINXCONF

# Copy static build output
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
