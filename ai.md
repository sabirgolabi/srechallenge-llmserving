# راهنمای استفاده از سرویس مدل (ai.md)


## خلاصه

| مورد | مقدار |
|---|---|
| مدل | `Qwen/Qwen2.5-0.5B-Instruct` (مدل کوچک، حدود ۰.۵ میلیارد پارامتر) |
| موتور | vLLM `0.29.0` روی **CPU** (بدون GPU)، پشت Ray Serve |
| آدرس از بیرون کلاستر | `http://188.121.110.178:30800`
| آدرس داخل کلاستر | `http://qwen-llm-serve-svc.llm-serving.svc.cluster.local:8000` |
| احراز هویت و TLS | **ندارد** (HTTP ساده، بدون کلید) |
| حداکثر توکن خروجی | **۶۴** در هر درخواست |
| حداکثر طول کل (پرامپت + خروجی) | **۵۱۲ توکن** |
| streaming | **پشتیبانی نمی‌شود** |
| سرعت تقریبی | حدود ۶ ثانیه برای ۳۲ توکن با یک کاربر؛ حدود ۰.۱۶ درخواست در ثانیه |
| تعداد replica | ۱ (بدون HA) |

## اندپوینت‌ها

### `POST /generate`:

پرامپت **خام** به مدل داده می‌شود (بدون قالب چت)، پس مدل متن را ادامه می‌دهد و لزوماً مثل یک دستیار جواب نمی‌دهد. خروجی همیشه یکسان است (greedy، `temperature=0`).

```bash
curl -s -X POST http://188.121.110.178:30800/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "What is Kubernetes?", "max_new_tokens": 32}'
```

```json
{"text": " Kubernetes is an open-source container orchestration platform ..."}
```

| فیلد | نوع | توضیح |
|---|---|---|
| `prompt` | string | الزامی، حداقل یک کاراکتر |
| `max_new_tokens` | int | پیش‌فرض ۳۲، حداقل ۱. مقدار بیشتر از ۶۴ **بدون خطا** روی ۶۴ بسته می‌شود |

پاسخ فقط فیلد `text` دارد (بدون شمارنده‌ی توکن).

### `POST /v1/chat/completions`: چت (سازگار با OpenAI)

برای پرسش و پاسخ و دستور دادن به مدل، این اندپوینت مناسب‌تر است. پیام‌ها با قالب چت خود Qwen به مدل می‌رسند.

```bash
curl -s http://188.121.110.178:30800/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
        "messages": [
          {"role": "system", "content": "You are a concise assistant."},
          {"role": "user", "content": "Explain DNS in one sentence."}
        ],
        "max_tokens": 48,
        "temperature": 0.2
      }'
```

فیلدهای پشتیبانی‌شده: `messages`، `max_tokens` (پیش‌فرض ۳۲)، `temperature` (پیش‌فرض ۰.۷)، `top_p` (پیش‌فرض ۱.۰) و `stream` (فقط `false`). فیلد `model` پذیرفته می‌شود ولی نادیده گرفته می‌شود.

پاسخ ساختار استاندارد OpenAI دارد: `choices[0].message.content`، `choices[0].finish_reason` و `usage` (`prompt_tokens`، `completion_tokens`، `total_tokens`).

- `finish_reason: "length"` یعنی خروجی به سقف توکن رسید و **ممکن است وسط جمله قطع شده باشد**.
- `finish_reason: "stop"` یعنی مدل خودش تمام کرد.

### `POST /v1/completions`: تکمیل متن (سازگار با OpenAI)

مثل `/generate` ولی با قالب OpenAI و با `temperature` و `top_p` قابل تنظیم. `prompt` فقط یک رشته است (لیست پشتیبانی نمی‌شود).

```bash
curl -s http://<NODE_IP>:30800/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Once upon a time", "max_tokens": 40}'
```

### `GET /v1/models`

فهرست مدل‌ها (فقط یک مدل). برای بررسی سریع اینکه سرویس بالاست مناسب است.

```bash
curl -s http://<NODE_IP>:30800/v1/models
```

## استفاده با کتابخانه‌ها

**OpenAI SDK** (پایتون): کلید هر رشته‌ای می‌تواند باشد، چون بررسی نمی‌شود.

```python
from openai import OpenAI

client = OpenAI(base_url="http://<NODE_IP>:30800/v1", api_key="not-needed", timeout=180)

resp = client.chat.completions.create(
    model="Qwen/Qwen2.5-0.5B-Instruct",
    messages=[{"role": "user", "content": "Give me one tip for learning Python."}],
    max_tokens=48,
)
print(resp.choices[0].message.content)
```

**requests:**

```python
import requests

r = requests.post(
    "http://<NODE_IP>:30800/generate",
    json={"prompt": "What is a container image?", "max_new_tokens": 32},
    timeout=180,
)
r.raise_for_status()
print(r.json()["text"])
```

## محدودیت‌ها

### محدودیت‌های سخت (از سرویس)

- **حداکثر ۶۴ توکن خروجی.** `max_new_tokens` و `max_tokens` بالاتر از ۶۴ بی‌صدا به ۶۴ کاهش می‌یابند. مقدار `0` برای `max_tokens` مثل «تنظیم‌نشده» رفتار می‌کند و ۳۲ می‌شود.
- **حداکثر ۵۱۲ توکن برای مجموع پرامپت و خروجی.** اگر پرامپت به‌اضافه‌ی سقف خروجی از ۵۱۲ بیشتر شود، خطای `400` با پیامی مثل `prompt too long: N + M > 512 tokens` می‌گیرید.
- **بدون streaming.** `stream: true` خطای `400` می‌دهد.
- **بدون حافظه‌ی مکالمه.** سرویس state ندارد؛ در چت باید کل تاریخچه را هر بار در `messages` بفرستید (و در سقف ۵۱۲ توکن بماند).
- **پارامترهای دیگر OpenAI** (`n`، `stop`، `seed`، `presence_penalty`، `frequency_penalty`، `logprobs`، `tools`، `response_format` و ...) **بدون خطا نادیده گرفته می‌شوند**، پس اثری ندارند.
- **توکن، کلمه نیست.** ۶۴ توکن تقریباً ۴۰ تا ۵۰ کلمه‌ی انگلیسی است. برای فارسی معمولاً توکن بیشتری برای همان متن مصرف می‌شود، پس متن کوتاه‌تری به دست می‌آید.

### محدودیت‌های عملکرد (اندازه‌گیری‌شده با k6 روی همین کلاستر)

- یک درخواست ۳۲ توکنی: حدود **۶.۲ ثانیه** (حدود ۵ توکن بر ثانیه). ۶۴ توکن تقریباً دو برابر می‌شود.
- **throughput ثابت است:** حدود ۰.۱۶ درخواست بر ثانیه، چه یک کاربر باشد چه هشت کاربر. بیشتر شدن همزمانی فقط latency را بالا می‌برد.
- با ۸ کاربر همزمان: میانگین حدود ۲۱ ثانیه و p95 حدود ۴۳ ثانیه (بدون خطا).
- سرویس **صف می‌کند و رد نمی‌کند**: درخواست اضافه خطای `429` نمی‌گیرد، فقط دیرتر جواب می‌دهد. پس **timeout سمت کلاینت لازم است** (پیشنهاد: حداقل ۱۸۰ ثانیه).
- موتور حداکثر ۴ درخواست را با هم پردازش می‌کند و سقف درخواست‌های در حال اجرا در Ray Serve برابر ۱۶ است.

### محدودیت‌های کیفیت (مدل)

- مدل خیلی کوچک است: ممکن است اشتباه یا بی‌ربط جواب بدهد و اطلاعات را از خودش بسازد (hallucination). به خروجی برای واقعیت‌ها، محاسبه و کد حساس تکیه نکنید.
- **فارسی ضعیف است.** در تست، جواب‌های فارسی اغلب بی‌معنی بودند. انگلیسی معقول‌تر است.
- به‌خاطر سقف ۶۴ توکن، پاسخ‌های بلند قطع می‌شوند.
- `/generate` پرامپت را ادامه می‌دهد و مثل دستیار پاسخ نمی‌دهد. برای دستور و سؤال از `/v1/chat/completions` استفاده کنید.
- فیلتر یا moderation اضافه‌ای جز رفتار خود مدل وجود ندارد.


## کدهای خطا

| کد | علت معمول |
|---|---|
| `200` | موفق |
| `400` | پرامپت بیش از حد بلند (مجموع بیشتر از ۵۱۲ توکن) یا `stream: true` |
| `422` | بدنه نامعتبر: `prompt` خالی یا نبودن، `max_new_tokens` کمتر از ۱ یا غیرعددی، `messages` نامعتبر |
| `5xx` یا timeout | خطای موتور، یا سرویس در حال بالا آمدن/ری‌استارت |
