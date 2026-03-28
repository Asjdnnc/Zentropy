FROM debian:bookworm-slim AS liboqs-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        cmake \
        ninja-build \
        build-essential \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git

WORKDIR /build/liboqs
RUN cmake -S . -B build \
      -GNinja \
      -DBUILD_SHARED_LIBS=ON \
      -DOQS_BUILD_ONLY_LIB=ON \
    && cmake --build build --parallel


FROM rust:1.88-bookworm AS prover-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        pkg-config \
        cmake \
        clang \
        build-essential \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY zk_prover ./zk_prover

WORKDIR /build/zk_prover
RUN cargo build --release --bin prover


FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LD_LIBRARY_PATH=/usr/local/lib \
    OQS_INSTALL_PATH=/usr/local

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libstdc++6 \
        libgcc-s1 \
        bash \
        curl \
    && curl https://get.starkli.sh | sh \
    && /root/.starkli/bin/starkliup \
    && cp /root/.starkli/bin/starkli /usr/local/bin/ \
    && rm -rf /root/.starkli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=liboqs-builder /build/liboqs/build/lib/liboqs.so /usr/local/lib/liboqs.so
COPY --from=prover-builder /build/zk_prover/target/release/prover /usr/local/bin/prover

COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY . .

RUN chmod +x ./docker/entrypoint.sh

EXPOSE 8000 8001

ENTRYPOINT ["/app/docker/entrypoint.sh"]
