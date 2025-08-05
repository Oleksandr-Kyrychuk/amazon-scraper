FROM python:3.9-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    xvfb \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    libxss1 \
    libappindicator3-1 \
    libcurl4 \
    fonts-liberation \
    ca-certificates \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver 138.0.7204.183
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/138.0.7204.183/linux64/chromedriver-linux64.zip \
    && unzip chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm chromedriver-linux64.zip

# Verify and set permissions
RUN chmod +x /usr/bin/chromium /usr/bin/chromedriver \
    && ls -l /usr/bin/chromium /usr/bin/chromedriver

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Set Chromium binary path
ENV CHROME_BIN=/usr/bin/chromium

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]