FROM ubuntu:latest
WORKDIR /app
COPY . .

# Install system packages
RUN apt-get update
RUN apt-get install git -y
RUN apt-get install python3 -y
RUN apt-get install pip -y
RUN apt-get install wget -y

# Build and install ta-lib dependency:
RUN wget https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz
RUN tar -xzf ta-lib-0.6.4-src.tar.gz
WORKDIR /app/ta-lib-0.6.4
RUN ./configure --prefix=/usr
RUN make
RUN make install
WORKDIR /app

# Install AmpyFin dependencies
RUN pip install --break-system-packages -r requirements.txt

# Initial command
ENTRYPOINT ["python3"]
CMD ["setup.py"]