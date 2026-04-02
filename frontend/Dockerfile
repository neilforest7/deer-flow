# Frontend Dockerfile
# Supports two targets:
#   --target dev   — install deps only, run `pnpm dev` at container start
#   --target prod  — full build baked in, run `pnpm start` at container start (default if no --target is specified)

ARG PNPM_STORE_PATH=/root/.local/share/pnpm/store
ARG NPM_REGISTRY

FROM node:22-alpine AS base
ARG PNPM_STORE_PATH
ARG NPM_REGISTRY
RUN if [ -n "${NPM_REGISTRY}" ]; then \
      export COREPACK_NPM_REGISTRY="${NPM_REGISTRY}"; \
    fi && \
    corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi
WORKDIR /app
COPY frontend ./frontend

FROM base AS dev
RUN cd /app/frontend && pnpm install --frozen-lockfile
EXPOSE 3000

FROM base AS builder
ARG NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api/langgraph
ARG BETTER_AUTH_BASE_URL=http://localhost:2026
ARG BETTER_AUTH_SECRET=6f7d9c19b4c24ef2b3c5d8e1f0a24679c8d1e2f3a4b5c6978d9e0f1a2b3c4d5e
ENV NEXT_PUBLIC_LANGGRAPH_BASE_URL=${NEXT_PUBLIC_LANGGRAPH_BASE_URL}
ENV BETTER_AUTH_BASE_URL=${BETTER_AUTH_BASE_URL}
ENV BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}
RUN cd /app/frontend && pnpm install --frozen-lockfile
RUN cd /app/frontend && SKIP_ENV_VALIDATION=1 pnpm build

FROM node:22-alpine AS prod
ARG PNPM_STORE_PATH
ARG NPM_REGISTRY
RUN if [ -n "${NPM_REGISTRY}" ]; then \
      export COREPACK_NPM_REGISTRY="${NPM_REGISTRY}"; \
    fi && \
    corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi
WORKDIR /app
COPY --from=builder /app/frontend ./frontend
EXPOSE 3000
CMD ["sh", "-c", "cd /app/frontend && pnpm start"]
