# frontend/Dockerfile

# --- Builder: build static files ---
FROM node:20-alpine AS builder
WORKDIR /app

# Provide the exact Vite var your app reads
# Example value points to FastAPI at :8000 with your tasks route
ARG VITE_API_BASE=http://localhost:8000/api/v1/tasks
ENV VITE_API_BASE=${VITE_API_BASE}

# Install deps (cache-friendly)
COPY ui/package*.json ./
RUN npm ci --registry=https://registry.npmjs.org/

# Build
COPY ui/ ./
RUN npm run build

# --- Runner: Nginx to serve the build ---
FROM nginx:alpine

# Serve the SPA
COPY --from=builder /app/dist /usr/share/nginx/html

# Minimal SPA config (Docker BuildKit heredoc; requires DOCKER_BUILDKIT=1)
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

    # (Optional) If you reverse proxy API via Nginx instead of CORS:
    # location /api/ {
    #     proxy_pass http://api:8000/;
    #     proxy_set_header Host $host;
    #     proxy_set_header X-Real-IP $remote_addr;
    #     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    #     proxy_set_header X-Forwarded-Proto $scheme;
    # }
}
NGINXCONF

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
