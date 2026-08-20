FROM node:20-alpine

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm install

COPY apps/web .

EXPOSE 5173

# Compose bind-mounts the source over /app and keeps node_modules in a named volume, so
# the volume outlives package.json changes: a new dependency would otherwise be missing
# until someone knew to delete the volume by hand. `npm install` is a no-op when the
# lockfile is already satisfied, so this costs a second on an unchanged tree.
CMD ["sh", "-c", "npm install --no-audit --no-fund && npm run dev -- --host 0.0.0.0"]
