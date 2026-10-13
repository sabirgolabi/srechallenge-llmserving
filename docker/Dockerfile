# vLLM CPU image + Ray Serve, so the same image can be used for Ray head and workers.
ARG VLLM_CPU_IMAGE=vllm/vllm-openai-cpu:v0.29.0-x86_64
FROM ${VLLM_CPU_IMAGE}

ARG RAY_VERSION=2.59.0
# Override with a mirror when PyPI is unreachable, e.g.
#   --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

# Pin everything already installed so Ray can never silently replace vllm/torch.
RUN pip freeze > /tmp/constraints.txt && \
    pip install -i "${PIP_INDEX_URL}" -c /tmp/constraints.txt "ray[serve]==${RAY_VERSION}" && \
    pip check

# KubeRay starts `ray start ...` itself; drop the base image's `vllm serve` entrypoint.
ENTRYPOINT []
