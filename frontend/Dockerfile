# ─── Stage 1: build ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies (uses package-lock.json for reproducibility)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# ─── Stage 2: serve ──────────────────────────────────────────────────────────
FROM nginx:alpine

# Replace default nginx config with our SPA + proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Writes the real client IP snippet from REAL_IP_FROM at container start
# (the image's entrypoint runs /docker-entrypoint.d/*.sh before nginx).
COPY docker-entrypoint.d/40-stocktrack-real-ip.sh /docker-entrypoint.d/40-stocktrack-real-ip.sh
RUN chmod 0755 /docker-entrypoint.d/40-stocktrack-real-ip.sh

# Copy the built assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
