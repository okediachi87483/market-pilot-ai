# syntax=docker/dockerfile:1

FROM node:22-slim AS base
WORKDIR /build

FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm install

FROM base AS builder
COPY --from=deps /build/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM base AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
# node:22-slim already ships a non-root "node" user (uid/gid 1000).
WORKDIR /app
COPY --from=builder /build/public ./public
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD node -e "fetch('http://localhost:3000/dashboard').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
