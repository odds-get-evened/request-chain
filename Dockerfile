# using Docker to build executable for Linux via pyinstaller
# in docker terminal run:
# docker build -t request-chain-builder .
# then (on Windows only):
# docker run -v ${PWD}/dist/linux:/dist/linux request-chain-builder

FROM ubuntu:22.04

RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    apt-get clean && \
    pip3 install pyinstaller

WORKDIR /app
COPY . .

RUN pip3 install -r requirements.txt
RUN pyinstaller --onefile peer_ui.py

CMD ["cp", "-r", "/app/dist/", "/dist/linux/"]