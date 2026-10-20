# rrotor Helm chart

One rrotor per release: a StatefulSet of one replica, its `/data` on its own volume, an Ingress at the one public
host; or, with `cluster.enabled=true` and a licence key with cluster sync, `replicas` nodes (default 3) of one
runtime behind the same Service and Ingress. The full guide, with what the cluster must allow for the sandbox, is
https://docs.glyphh.ai/helm.

Install the packaged chart from its release; nothing needs cloning:

```sh
helm install rrotor https://github.com/glyphh-ai/glyphh/releases/download/rrotor-chart-0.2.0/rrotor-0.2.0.tgz \
  -n rrotor --create-namespace \
  --set publicHost=rrotor.acme.com \
  --set runtime.id=<runtime id> --set runtime.token=<runtime token> \
  --set ingress.className=nginx --set ingress.certManagerClusterIssuer=letsencrypt
```

The connector is then at `https://<publicHost>/mcp`.

This folder is the chart's source: a push to `main` that raises `version` in `Chart.yaml` packages it as the release
`rrotor-chart-<version>` (`.github/workflows/chart.yml`).
