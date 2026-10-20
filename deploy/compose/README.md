# rrotor with Docker

One machine: rrotor, and Caddy in front of it for HTTPS. The full guide is https://docs.glyphh.ai/docker-compose.

1. Register the runtime on the platform (https://platform.glyphh.ai, Runtimes, Add a runtime): it gives the runtime
   id and token, and shows the line below filled in.
2. Point the public host's DNS at this machine, with ports 80 and 443 open to it.
3. Run the installer (it needs Docker with Compose):

```sh
curl -fsSL https://glyphh.ai/install.sh | RROTOR_RUNTIME_ID=<id> RROTOR_RUNTIME_TOKEN=<token> RROTOR_PUBLIC_HOST=rrotor.acme.com sh
```

It writes `./rrotor` (`docker-compose.yml`, `Caddyfile`, `.env`) and starts it; `RROTOR_SIZE=small|medium|large`
sets its size, and running it again updates the settings. The installer fetches those two files from this folder,
the source it is built from: nothing here needs cloning. `.env.example` lists every setting `.env` takes.

The runtime's connector is then at `https://<public host>/mcp`. Linux hosts on Ubuntu 23.10 or later first need
`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` (kept in `/etc/sysctl.d/`), or the sandbox cannot start.

**HTTPS already in front** (your own load balancer or proxy, sending the public host to port 7777): the image alone,

```sh
docker run -d --name rrotor --restart unless-stopped \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined \
  --read-only --tmpfs /tmp:exec,mode=1777 -v rrotor-data:/data -p 7777:7777 \
  -e RROTOR_MODE=self -e RROTOR_RUNTIME_ID=<id> -e RROTOR_RUNTIME_TOKEN=<token> -e RROTOR_PUBLIC_HOST=rrotor.acme.com \
  ghcr.io/glyphh-ai/rrotor:latest
```

The variants below each take two more files from this folder, fetched into `./rrotor` beside the installer's:

```sh
cd rrotor && curl -fsSLO https://raw.githubusercontent.com/glyphh-ai/glyphh/main/deploy/compose/<file>
```

**Air-gapped:** fetch `docker-compose.airgap.yml` and `Caddyfile.airgap`; put the licence key in `.env` as
`GLYPHH_LICENSE_KEY`, your certificate and key in `certs/tls.crt` and `certs/tls.key`, and start with the overlay,
which turns the link off:

```sh
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d
```

**A cluster** (a licence key with cluster sync; `RROTOR_CLUSTER_SECRET` in `.env`, `openssl rand -base64 32`): to
try one, fetch `docker-compose.cluster.yml` and `Caddyfile.cluster`, for three nodes and Caddy balancing over them on
this machine,

```sh
docker compose -f docker-compose.cluster.yml up -d
```

For high availability, fetch `docker-compose.node.yml` on each of several machines and run it with `-f`, with
`RROTOR_NODE_ID`, `RROTOR_CLUSTER_ADVERTISE` and `RROTOR_CLUSTER_PEERS` in each `.env`, port 7778 open between them
only and your load balancer in front of port 7777. See https://docs.glyphh.ai/docker-compose, "A cluster".
