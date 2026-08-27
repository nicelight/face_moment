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
