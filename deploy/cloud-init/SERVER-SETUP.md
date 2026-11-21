# Deploying the cloud-init version on a server (Incus VM)

How Varsis was deployed on the course server `devops-sk-33.lrk.si`: an Ubuntu 24.04 host runs an **Incus** VM,
and [`user-data.yaml`](user-data.yaml) sets up everything inside that VM at first boot. Caddy gets a valid
Let's Encrypt certificate.

```
internet ──▶ host 88.200.24.30 :80/:443 ──(Incus proxy, NAT)──▶ VM 10.182.95.10 :80/:443 ──▶ Caddy ──▶ backend, PostgreSQL, Mailpit
                                  └── incusbr0 10.182.95.1/24 (DHCP, DNS, NAT to the internet for the VM)
```

Values used on our server (replace with yours):

| What | Value |
|---|---|
| Domain | `devops-sk-33.lrk.si` (DNS A record → the host's public IP) |
| Host public IP | `88.200.24.30` |
| Incus bridge subnet | `10.182.95.1/24` (chosen by `incus admin init`) |
| VM IP (fixed) | `10.182.95.10` |

## 1. Host requirements

- Ubuntu 24.04, ports **80 and 443 reachable from the internet** (Let's Encrypt checks the domain through them).
- **KVM** for VMs. On a VM host (nested virtualization) check it exists:
  ```bash
  ls -l /dev/kvm
  ```
  Without it Incus can only run containers.
- Disk space: the storage pool needs room for the VM disk (15 GB here) plus the Ubuntu image.

## 2. Install Incus and QEMU

```bash
sudo apt install incus qemu-system-x86 ovmf qemu-utils
sudo usermod -aG incus-admin $USER && newgrp incus-admin
```

| Package | Why |
|---|---|
| `incus` | Manages instances, storage, the network bridge |
| `qemu-system-x86` | Runs the VMs. Ubuntu's `incus` package doesn't pull it in; without it: *"Instance type virtual-machine is not supported on this server: QEMU command not available"* |
| `ovmf` | UEFI firmware Incus VMs boot with |
| `qemu-utils` | Disk image tools (`qemu-img`) |

`incus-admin` group: lets the user talk to the Incus daemon without sudo (`newgrp` applies it to the current shell).

## 3. Initialize Incus

```bash
incus admin init
```

| Question | Answer | Why |
|---|---|---|
| Clustering | no | One server |
| New storage pool | yes, name `default`, backend **btrfs**, new loop device, size ≥ 15 GiB | Copy-on-write: a new VM is a thin copy of the cached image, so launching is fast. The loop device is a file on the existing disk |
| MAAS | no | |
| New network bridge | yes, `incusbr0`, IPv4 `auto`, IPv6 `auto` | Gives VMs addresses (DHCP via dnsmasq) and internet (NAT) |
| Available over the network | no | Would expose the Incus management API |
| Update stale images | yes | |

The same setup as a preseed (`incus admin init --preseed < incus-preseed.yaml` reproduces it without questions):

```yaml
config: {}
networks:
- name: incusbr0
  type: ""
  config:
    ipv4.address: auto
    ipv6.address: auto
storage_pools:
- name: default
  driver: btrfs
  config:
    size: 15GiB
profiles:
- name: default
  devices:
    eth0: {name: eth0, network: incusbr0, type: nic}
    root: {path: /, pool: default, type: disk}
```

The subnet `auto` picked:

```bash
incus network get incusbr0 ipv4.address        # 10.182.95.1/24
```

`.1` is the host's own address on the bridge (the VM's gateway). The VM gets a different one, e.g. `.10`.

## 4. Firewall (ufw) on the host

The host had ufw active with only SSH and 80/443 allowed. That **blocks DHCP and DNS on the bridge**: the VM came up
with an IPv6 address (from router advertisements) but **no IPv4**, and cloud-init failed without internet.

```bash
sudo ufw allow in on incusbr0          # VM → host: DHCP, DNS
sudo ufw route allow in on incusbr0    # forwarded traffic from the VM (to the internet)
sudo ufw route allow out on incusbr0   # forwarded traffic to the VM (the port forwards below)
sudo ufw allow 80,443/tcp              # visitors and Let's Encrypt (already there on our host)
```

## 5. Settings for this server

```bash
cp deploy/cloud-init/user-data.yaml varsis.yaml
vim varsis.yaml
```

In the `/etc/varsis/deploy.env` block:

```
DOMAIN=devops-sk-33.lrk.si     # Caddy requests a Let's Encrypt certificate for it
ADMIN_EMAILS=you@example.com
MAILPIT=true                   # no mail provider: mails are caught by Mailpit (https://<domain>/mailpit/)
SITE=                          # leave empty; only for port-forwarded test VMs (run-qemu.sh)
```

`varsis.yaml` contains no generated secrets (the VM creates those itself). If you put a real `SMTP_PASS` in it, don't
commit it.

## 6. Launch the VM

```bash
incus launch images:ubuntu/24.04/cloud varsis --vm \
  -c limits.cpu=2 -c limits.memory=2GiB -d root,size=15GiB \
  -d eth0,ipv4.address=10.182.95.10 \
  -c cloud-init.user-data="$(cat varsis.yaml)" \
  -c boot.autostart=true
```

| Option | Why |
|---|---|
| `images:ubuntu/24.04/cloud` | The `/cloud` variant includes cloud-init |
| `--vm` | A full VM instead of a system container |
| `limits.memory=2GiB` | The frontend build (`npm run build`) needs it |
| `-d eth0,ipv4.address=…` | Fixed IP (a DHCP reservation on the bridge), so the port forwards always reach the VM. Must not be the bridge's own `.1` |
| `cloud-init.user-data` | Incus hands the file to cloud-init inside the VM (NoCloud data source) |
| `boot.autostart=true` | Starts the VM when the host reboots |

Check it got its IPv4 (if not: step 4):

```bash
incus list varsis
```

## 7. Forward ports 80/443 to the VM

```bash
incus config device add varsis http  proxy nat=true listen=tcp:88.200.24.30:80  connect=tcp:10.182.95.10:80
incus config device add varsis https proxy nat=true listen=tcp:88.200.24.30:443 connect=tcp:10.182.95.10:443
```

`nat=true` makes Incus add DNAT firewall rules instead of running a proxy process, so the VM sees each visitor's
**real IP** (the backend's rate limits and Caddy's access log depend on it). In NAT mode the listen address must be
the host's real IP (not `0.0.0.0`), and the VM must have a fixed IP (step 6).

Ports must match on both sides (80 → 80, 443 → 443): Caddy listens on 80 (ACME HTTP challenge, redirect to https)
and 443.

## 8. Follow the setup

```bash
incus exec varsis -- tail -f /var/log/cloud-init-output.log
```

Ends with (about 2.5 minutes on our server):

```
[varsis-setup] done: https://devops-sk-33.lrk.si
Varsis cloud-init finished after 148.83 s.
```

## 9. Certificate

Caddy requests the certificate as soon as it starts. If the port forwards didn't exist yet, the first attempts
fail and Caddy retries with growing pauses. Restart it to retry immediately:

```bash
incus exec varsis -- systemctl restart caddy
incus exec varsis -- journalctl -u caddy --no-pager | grep -iE "certificate obtained|error" | tail -5
# ... "certificate obtained successfully","identifier":"devops-sk-33.lrk.si","issuer":"acme-v02.api.letsencrypt.org-directory"
```

Check from **another machine** (connections from the host to its own public IP may bypass the NAT rules):

```bash
curl -sI https://devops-sk-33.lrk.si | head -1                    # HTTP/2 200, no certificate error
curl -sI http://devops-sk-33.lrk.si | head -3                     # 308 redirect to https://
echo | openssl s_client -connect devops-sk-33.lrk.si:443 2>/dev/null | openssl x509 -noout -issuer -dates
```

Caddy renews the certificate itself (about 30 days before expiry).

## 10. Use it

| | |
|---|---|
| App | `https://devops-sk-33.lrk.si` |
| Mailpit | `https://devops-sk-33.lrk.si/mailpit/`, user `mailpit`, password: `incus exec varsis -- grep MAILPIT_PASSWORD /etc/varsis/secrets.env` |

Register with the address in `ADMIN_EMAILS`, open the verification mail in Mailpit, click the link: the account is
an admin and approved.

## Operating it

```bash
incus list                                                    # state, IPs
incus shell varsis                                            # root shell in the VM
incus exec varsis -- systemctl status varsis-backend caddy postgresql mailpit --no-pager
incus exec varsis -- journalctl -u varsis-backend -f           # backend log
incus exec varsis -- tail -f /var/log/caddy/varsis-access.log  # requests (JSON)
incus config device show varsis                               # port forwards, fixed IP
```

Update to a newer commit of the app:

```bash
incus exec varsis -- sh -c 'git -C /opt/varsis pull && /usr/local/sbin/varsis-setup'
```

Start over (cloud-init only runs on a VM's first boot, so changed settings need a new VM; the port forwards are
part of the VM and must be added again):

```bash
incus delete -f varsis        # then steps 6 and 7
```

## Problems we hit

| Symptom | Cause | Fix |
|---|---|---|
| `incus network get incusbr0 …`: *Network not found* | `incus admin init` not run yet | Step 3 |
| *QEMU command not available for CPU architecture* | QEMU not installed | `apt install qemu-system-x86 ovmf qemu-utils` |
| *IP address "10.182.95.1" is assigned to parent managed network device* | Gave the VM the bridge's own `.1` address | Use another address in the subnet, e.g. `.10` |
| VM has IPv6 but no IPv4; cloud-init fails (no internet) | ufw blocks DHCP/DNS/forwarding on `incusbr0` | Step 4, then delete and relaunch the VM |
| `bash: server-ip: No such file or directory` | `<server-ip>` placeholder pasted literally (`<` is input redirection) | Put the real IP in |
| Certificate: `authorization failed … tls: internal error` | Let's Encrypt couldn't reach the VM: port forwards were missing | Step 7, then restart Caddy |
| `http://` doesn't redirect | Port 80 forwarded to the wrong VM port (8080) | Forward 80 → 80 |
| `cat: varsis.yaml: No such file or directory` | Settings copy not created | Step 5 |
