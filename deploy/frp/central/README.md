# Face Moment central FRP client

The generated bundle contains the pinned `frpc` binary, configuration, systemd
unit, and the shared token. Transfer the complete bundle directory to the
central Kubuntu machine, then run:

```bash
chmod 700 install.sh
sudo ./install.sh face.example.com
```

Replace `face.example.com` with the public hostname configured on the VPS.

Verification after installation:

```bash
sudo systemctl --no-pager --full status frpc
sudo journalctl -u frpc -n 80 --no-pager -o cat
```

The configuration publishes two VPS-loopback-only endpoints:

- `127.0.0.1:18443` on the VPS forwards to the central application edge;
- `127.0.0.1:10022` on the VPS forwards to central OpenSSH on port `22`.

The SSH endpoint is deliberately not bound to the VPS public interface. Access
it from an administrator workstation through the VPS SSH connection with an
OpenSSH `ProxyJump` entry:

```sshconfig
Host facecentral
    HostName 127.0.0.1
    Port 10022
    User face
    ProxyJump igornskprod
```
