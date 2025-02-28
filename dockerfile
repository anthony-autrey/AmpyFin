FROM python:3.11-slim

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build TA-Lib
WORKDIR /tmp
RUN wget --no-check-certificate https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz \
    && tar -xzf ta-lib-0.6.4-src.tar.gz \
    && cd ta-lib-0.6.4 \
    && ./configure \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib-0.6.4 ta-lib-0.6.4-src.tar.gz

# Make sure the linker can find the library
RUN ldconfig

# Copy requirements first to leverage Docker cache
WORKDIR /app
COPY requirements.txt .

# Install all dependencies with wheels where possible
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create and set permissions for data directory
RUN mkdir -p /app/data && chmod 700 /app/data

# Initial command
ENTRYPOINT ["python3"]
CMD ["setup.py"]