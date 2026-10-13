# سرویس LLM روی Kubernetes (Ray Serve + vLLM روی CPU)

مدل `Qwen/Qwen2.5-0.5B-Instruct` روی کلاستر kubeadm سه‌نودی با KubeRay، Ray Serve و vLLM (فقط CPU) اجرا می‌شود. مانیتورینگ با kube-prometheus-stack و لود تست با k6 است.
راهنمای استفاده از مدل و محدودیت‌ها: [ai.md](ai.md)

فقط دو ابزار لازم است: `kubectl` (که kustomize را دارد) و `helm`.

## ساختار

```
app/serve_app.py       کد Ray Serve (به‌صورت ConfigMap به پادها می‌رسد)
docker/Dockerfile      ایمیج vLLM CPU + Ray
k8s/                   همه‌ی YAMLها؛ با یک دستور اعمال می‌شود (kubectl apply -k k8s/)
  namespaces/          namespaceها، ResourceQuota، LimitRange
  llm-serving/         RayService و Serviceها
  monitoring/          PodMonitor مربوط به Ray
helm/kps-values.yaml   تنظیمات Prometheus و Grafana
loadtest/              اسکریپت و Job لود تست k6
.gitlab-ci.yml         pipeline
```

## راه‌اندازی از صفر

**۱. فقط یک‌بار (کلاستر)**

```bash
kubectl apply -k k8s/namespaces

kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.31/deploy/local-path-storage.yaml

helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kuberay-operator kuberay/kuberay-operator \
  --version 1.3.0 -n kuberay-system --create-namespace

helm upgrade --install kps prometheus-community/kube-prometheus-stack \
  --version 92.3.0 -n monitoring -f helm/kps-values.yaml --timeout 10m
```

**۲. ساخت ایمیج و رساندنش به نودها** (نودها رجیستری ندارند)

```bash
docker build --platform linux/amd64 -f docker/Dockerfile -t vllm-ray-cpu:0.1 docker/
for n in node1 node2 node3; do
  docker save vllm-ray-cpu:0.1 | ssh root@$n 'ctr -n k8s.io images import -'
done
```

اگر PyPI در دسترس نیست، به دستور build این را اضافه کنید:
`--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple`

**۳. استقرار (هر بار که چیزی عوض شد)**

```bash
kubectl apply -k k8s/
```

بالا آمدن اولین بار چند دقیقه طول می‌کشد (دانلود مدل). وضعیت:

```bash
kubectl get pods -n llm-serving
kubectl get rayservice -n llm-serving
```

**۴. تست**

```bash
HEAD=$(kubectl get pod -n llm-serving -l ray.io/node-type=head -o name | head -1)
kubectl exec -n llm-serving $HEAD -- curl -s -X POST http://qwen-llm-serve-svc:8000/generate \
  -H 'Content-Type: application/json' -d '{"prompt":"What is Kubernetes?","max_new_tokens":32}'
```

## آدرس‌ها

| سرویس | آدرس |
|---|---|
| مدل (`/generate`، `/v1/...`) | `http://<node-ip>:30800` |
| داشبورد Ray | `http://<node-ip>:30265` |
| Grafana | `http://<node-ip>:30300` (کاربر `admin`، رمز در Secret `kps-grafana`) |
| Prometheus | `http://<node-ip>:30900` |

## تغییرها

| چه چیزی را عوض کردید | چه کنید |
|---|---|
| کد `app/serve_app.py` | `kubectl apply -k k8s/`، حدود یک دقیقه صبر کنید تا فایل به پاد برسد، بعد عدد `APP_VERSION` را در `k8s/llm-serving/rayservice.yaml` یکی زیاد کنید و دوباره `apply` بزنید. Serve بدون ساخت مجدد کلاستر replica را دوباره بالا می‌آورد |
| ایمیج (تگ جدید) یا منابع پادها | `kubectl delete rayservice qwen-llm -n llm-serving` و بعد `kubectl apply -k k8s/`. تغییر مشخصات RayCluster کلاستر دومی می‌سازد که در quota جا نمی‌شود |
| تنظیمات Prometheus یا Grafana | `helm/kps-values.yaml` را عوض کنید و دستور `helm upgrade --install kps ...` را دوباره بزنید |

## لود تست

```bash
JOB=$(kubectl create -f loadtest/job.yaml -o name)
kubectl logs -n monitoring -f $JOB
```

۱ تا ۸ کاربر همزمان، حدود ۶ دقیقه. نتایج baseline (`max_new_tokens=32`):

| سناریو | throughput | میانگین latency | p95 | خطا |
|---|---|---|---|---|
| ۱ کاربر | ۰.۱۶ req/s | ۶.۲۵s | ۶.۴s | ۰٪ |
| ۱ تا ۸ کاربر | ۰.۱۵۶ req/s | ۲۰.۸s | ۴۳s | ۰٪ |

با بیشتر شدن کاربرها throughput بالا نمی‌رود و فقط latency زیاد می‌شود.

### بهینه‌سازی (انجام نشده)

مقایسه‌ی قبل و بعد هنوز انجام نشده. مشاهدات تا اینجا:

- نودها ماشین مجازی KVM با CPU عمومی «Haswell» و فقط `avx2` هستند و مدل با `bfloat16` لود می‌شود.
- Throttling روی worker دیده نشد.
- آزمایش `float32` با کمبود حافظه موقع تخصیص KV cache شکست خورد. ۱ گیگ KV cache فعلی خیلی بیشتر از نیاز است و کم کردنش ساده‌ترین قدم بعدی است.

## داشبوردهای Ray در Grafana (اختیاری)

```bash
HEAD=$(kubectl get pod -n llm-serving -l ray.io/node-type=head -o name | head -1)
D=/tmp/ray/session_latest/metrics/grafana/dashboards
for f in default serve serve_deployment; do
  kubectl exec -n llm-serving $HEAD -- cat $D/${f}_grafana_dashboard.json > k8s/monitoring/${f}_grafana_dashboard.json
done
```

بعد خط‌های کامنت‌شده‌ی `configMapGenerator` را در `k8s/monitoring/kustomization.yaml` از حالت کامنت دربیاورید و `kubectl apply -k k8s/` بزنید.

## CI/CD (GitLab)

فایل `.gitlab-ci.yml` سه مرحله دارد و همه روی runner داخلی با تگ `k8s` (که به کلاستر دسترسی دارد) اجرا می‌شوند:

| مرحله | کار |
|---|---|
| `validate` | `kubectl apply -k k8s/ --dry-run=server`: API server همه‌ی YAMLها را بررسی می‌کند، بدون تغییر. روی merge request و شاخه‌ی اصلی |
| `deploy` | `kubectl apply -k k8s/` (فقط شاخه‌ی اصلی) |
| `smoke` | `/generate` را صدا می‌زند و تا ۲۰ دقیقه منتظر می‌ماند (فقط شاخه‌ی اصلی) |
| `loadtest` | دستی؛ k6 را اجرا می‌کند و خروجی را artifact می‌کند |

kubeconfig فقط روی runner است و چیز محرمانه‌ای در مخزن نیست. ساخت ایمیج و helm در pipeline نیستند و دستی انجام می‌شوند.

