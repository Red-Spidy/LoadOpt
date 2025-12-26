FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies with increased timeout
RUN npm install --legacy-peer-deps --fetch-timeout=600000

# Copy application
COPY . .

# Build the application
RUN npm run build || true

# Expose port
EXPOSE 3000

# Run application in development mode
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
