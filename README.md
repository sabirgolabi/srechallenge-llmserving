# سرویس LLM روی Kubernetes (Ray Serve + vLLM روی CPU)

مدل `Qwen/Qwen2.5-0.5B-Instruct` روی کلاستر kubeadm سه‌نودی با KubeRay، Ray Serve و vLLM (فقط CPU) راه اندازی شده است . مانیتورینگ با kube-prometheus-stack و لود تست با k6 است.

راهنمای استفاده از مدل و محدودیت‌ها: [ai.md](ai.md)

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


## آدرس‌ها

| سرویس | آدرس |
|---|---|
| مدل (`/generate`، `/v1/...`) | `http://88.121.110.178:30800` |
| داشبورد Ray | `http://88.121.110.178:30265` |
| Grafana | `http://88.121.110.178:30300` (کاربر `admin`، رمز در Secret `kps-grafana`) |
| Prometheus | `http://88.121.110.178:30900` |


