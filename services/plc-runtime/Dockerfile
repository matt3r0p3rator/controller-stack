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
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir "cmake>=3.30"

WORKDIR /src

RUN git clone --depth=1 --branch ${FORTE_REF} https://github.com/eclipse-4diac/4diac-forte.git

WORKDIR /src/4diac-forte

RUN cmake -S . -B build \
      -DCMAKE_BUILD_TYPE=Release \
      -DFORTE_ARCHITECTURE=Posix \
      -DFORTE_COM_ETH=ON \
      -DFORTE_MODULE_CONVERT=ON \
    && cmake --build build -j"$(nproc)" \
        && cp build/forte /usr/local/bin/forte

FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/bin/forte /usr/local/bin/forte

EXPOSE 61499

ENTRYPOINT ["/usr/local/bin/forte"]
CMD ["-c", "0.0.0.0:61499"]
