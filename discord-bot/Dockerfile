# Abakos Discord Bot — container image (for console.abakos.ai / any Docker host).
FROM node:20-alpine
WORKDIR /app

# Install prod deps first (better layer caching)
COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

# Register slash commands once on boot, then run the bot.
# .env is provided at runtime (env file / secrets), not baked into the image.
CMD ["sh", "-c", "node --env-file=.env register-commands.mjs && node --env-file=.env bot.mjs"]
