"""Ray Serve application: Qwen2.5-0.5B-Instruct on vLLM (CPU).

Endpoints
  POST /generate              {"prompt": str, "max_new_tokens": int}  ->  {"text": str}
  GET  /v1/models             OpenAI-compatible
  POST /v1/completions        OpenAI-compatible (no streaming)
  POST /v1/chat/completions   OpenAI-compatible (no streaming)

max_new_tokens / max_tokens are clamped to 64 as required by the challenge.
"""
import asyncio
import os
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from ray import serve

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "512"))
MAX_NUM_SEQS = int(os.environ.get("MAX_NUM_SEQS", "4"))
DTYPE = os.environ.get("DTYPE", "auto")
MAX_NEW_TOKENS = 64

api = FastAPI(title="Qwen2.5-0.5B on Ray Serve")


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_new_tokens: int = Field(default=32, ge=1)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = False


class CompletionRequest(BaseModel):
    model: Optional[str] = None
    prompt: str
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = False


def cap(n: Optional[int]) -> int:
    """Clamp the requested number of new tokens to [1, MAX_NEW_TOKENS]."""
    return max(1, min(n or 32, MAX_NEW_TOKENS))


@serve.deployment(
    num_replicas=1,
    max_ongoing_requests=16,
    ray_actor_options={"num_cpus": 1},
)
@serve.ingress(api)
class LLMServer:
    def __init__(self):
        from vllm import LLM

        self.llm = LLM(
            model=MODEL_ID,
            max_model_len=MAX_MODEL_LEN,
            max_num_seqs=MAX_NUM_SEQS,
            dtype=DTYPE,
        )
        self.tokenizer = self.llm.get_tokenizer()

    # Concurrent requests are merged into one batch and handed to vLLM together.
    @serve.batch(max_batch_size=MAX_NUM_SEQS, batch_wait_timeout_s=0.05)
    async def _run(self, items: List[tuple]) -> List[tuple]:
        from vllm import SamplingParams

        prompts = [i[0] for i in items]
        params = [
            SamplingParams(max_tokens=i[1], temperature=i[2], top_p=i[3])
            for i in items
        ]
        loop = asyncio.get_running_loop()
        outs = await loop.run_in_executor(
            None, lambda: self.llm.generate(prompts, params, use_tqdm=False)
        )
        return [
            (o.outputs[0].text, len(o.prompt_token_ids), len(o.outputs[0].token_ids))
            for o in outs
        ]

    def _check(self, prompt: str, max_tokens: int):
        n = len(self.tokenizer.encode(prompt))
        if n + max_tokens > MAX_MODEL_LEN:
            raise HTTPException(
                400, f"prompt too long: {n} + {max_tokens} > {MAX_MODEL_LEN} tokens"
            )

    @api.post("/generate")
    async def generate(self, req: GenerateRequest):
        n = cap(req.max_new_tokens)
        self._check(req.prompt, n)
        text, _, _ = await self._run((req.prompt, n, 0.0, 1.0))
        return {"text": text}

    @api.get("/v1/models")
    async def models(self):
        return {
            "object": "list",
            "data": [{"id": MODEL_ID, "object": "model", "owned_by": "local"}],
        }

    @api.post("/v1/completions")
    async def completions(self, req: CompletionRequest):
        if req.stream:
            raise HTTPException(400, "streaming is not supported")
        n = cap(req.max_tokens)
        self._check(req.prompt, n)
        text, pt, ct = await self._run((req.prompt, n, req.temperature, req.top_p))
        return {
            "id": f"cmpl-{uuid.uuid4().hex}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "text": text,
                    "finish_reason": "length" if ct >= n else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": pt + ct,
            },
        }

    @api.post("/v1/chat/completions")
    async def chat(self, req: ChatRequest):
        if req.stream:
            raise HTTPException(400, "streaming is not supported")
        n = cap(req.max_tokens)
        prompt = self.tokenizer.apply_chat_template(
            [{"role": m.role, "content": m.content} for m in req.messages],
            tokenize=False,
            add_generation_prompt=True,
        )
        self._check(prompt, n)
        text, pt, ct = await self._run((prompt, n, req.temperature, req.top_p))
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "length" if ct >= n else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": pt + ct,
            },
        }


app = LLMServer.bind()
