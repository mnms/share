# Offline install

- 1. Copy flashbase into server:/home/nvkvs/fbcli
- 2. Unzip flashbase
- 3. Run code below.

```

# centos (9th)
cd /home/nvkvs/yums
sudo yum localinstall ./cyrus-sasl-devel-2.1.26-20.el7_2.x86_64.rpm
cd /home/nvkvs/fbcli/flashbase/cli
sudo ./install.sh # If you install hiredis twice, you got seg fault
edit /home/nvkvs/fbcli/flashbase/cli/.flashbase/cluster/template/config.yaml
fbcli
```
