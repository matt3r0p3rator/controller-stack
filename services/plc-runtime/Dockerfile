FROM ubuntu:24.04 AS build

ARG DEBIAN_FRONTEND=noninteractive
ARG FORTE_REF=release

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        g++ \
        git \
        make \
        python3 \
        python3-pip \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir "cmake>=3.30"

WORKDIR /src

RUN git clone --depth=1 https://github.com/eclipse-paho/paho.mqtt.c.git

WORKDIR /src/paho.mqtt.c

RUN cmake -S . -B build \
      -DPAHO_WITH_SSL=FALSE \
      -DPAHO_BUILD_STATIC=FALSE \
      -DPAHO_BUILD_SHARED=TRUE \
    && cmake --build build -j"$(nproc)"

WORKDIR /src
RUN git clone --depth=1 --branch ${FORTE_REF} https://github.com/eclipse-4diac/4diac-forte.git

WORKDIR /src/4diac-forte

RUN cmake -S . -B build \
      -DCMAKE_BUILD_TYPE=Release \
      -DFORTE_ARCHITECTURE=Posix \
      -DFORTE_COM_ETH=ON \
      -DFORTE_MODULE_CONVERT=ON \
      -DFORTE_COM_PAHOMQTT=ON \
      -DFORTE_COM_PAHOMQTT_INCLUDE_DIR=/src/paho.mqtt.c/src \
      -DFORTE_COM_PAHOMQTT_LIB_DIR=/src/paho.mqtt.c/build/src \
      -DFORTE_COM_PAHOMQTT_LIB=paho-mqtt3a \
    && cmake --build build -j"$(nproc)" \
    && cp build/forte /usr/local/bin/forte

WORKDIR /app

COPY sine_mqtt.cpp /app/sine_mqtt.cpp

RUN g++ -std=c++17 -O2 /app/sine_mqtt.cpp -o /usr/local/bin/sine-mqtt \
      -I/src/paho.mqtt.c/src \
      -L/src/paho.mqtt.c/build/src \
      -lpaho-mqtt3a \
      -lpthread

FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        libstdc++6 \
        libssl3 \
        libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/bin/forte /usr/local/bin/forte
COPY --from=build /usr/local/bin/sine-mqtt /usr/local/bin/sine-mqtt
COPY --from=build /src/paho.mqtt.c/build/src/libpaho-mqtt3a.so* /usr/local/lib/
COPY start_with_sine.sh /usr/local/bin/start_with_sine.sh

RUN chmod +x /usr/local/bin/start_with_sine.sh \
    && ldconfig

EXPOSE 61499

ENTRYPOINT ["/usr/local/bin/start_with_sine.sh"]
