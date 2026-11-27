# llama.cpp with Vulkan for the Rock 5T's Mali-G610 GPU (RK3588).
#
# The board's own Mesa (25.0, Debian 12) gives the GPU only Vulkan 1.1, and
# llama.cpp needs 1.2. Mesa 26.0 (Ubuntu 26.04) gives Vulkan 1.4 but its GPU
# jobs time out ("panthor ... job timeout") with more than ~8 layers on the
# GPU. Mesa 26.2.7 (kisak PPA) runs the whole model. llama.cpp's prebuilt
# Vulkan release needs glibc 2.38, which Debian 12 also lacks.
#
# Build:  docker build -f models/gpu-vulkan.Dockerfile -t is2-gpu-vulkan:b12633 .
# Run:    models/llamacpp_server.py starts it (see docs/testing/model-vnv-gpu.md).
FROM ubuntu:26.04@sha256:d66b366dac61b575bee2aef07e9c26e8070096fbe84a3d4d3eb0da069b5d76db

ARG LLAMA_TAG=b12633
ARG LLAMA_SHA256=8968356ab4620d6fdd08c45e0a6401c2f9c862aa833d1024f87fd9c39ba5c3e6
ARG MESA_VERSION=26.2.7~kisak1~r

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg software-properties-common \
 && add-apt-repository -y ppa:kisak/kisak-mesa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      mesa-vulkan-drivers=${MESA_VERSION} libvulkan1 vulkan-tools libgomp1 \
 && apt-get purge -y software-properties-common && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/llama.tar.gz \
      https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_TAG}/llama-${LLAMA_TAG}-bin-ubuntu-vulkan-arm64.tar.gz \
 && echo "${LLAMA_SHA256}  /tmp/llama.tar.gz" | sha256sum -c - \
 && mkdir /opt/llama && tar xzf /tmp/llama.tar.gz -C /opt/llama --strip-components=1 \
 && rm /tmp/llama.tar.gz

WORKDIR /opt/llama
ENTRYPOINT ["/opt/llama/llama-server"]
