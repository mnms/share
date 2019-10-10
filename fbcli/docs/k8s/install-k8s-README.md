# Install (host)

## Prerequisite

- k8s-local-cluster-setting-README.md

# Install cli in container : fb-node-0

```
# (k means kubectl)
host-sh> alias k=kubectl
host-sh> k exec -it fb-node-0 bash

# in container
sh> cd local-cli
sh> ./install.sh
```

- 'host-sh>'은 도커 외부 shell을 의미합니다.
- 'sh>'은 컨테이너 안 shell을 의미합니다.

# Meta cluster setting : fb-node-0

설치를 하고 나면 fbcli가 설치되어 있으나 아직 meta data 저장을 위한 cluster (cluster 0)이
구동되어 있지 않은 상태이고 사용자 역시 생성되지 않은 상태입니다. 최초 fbcli 명령을 내릴 경우에는
필요한 cluster config를 생성하고 cluster를 배포 및 구동하는 과정을 먼저 수행하도록 구현하였습니다.

여기서는 (1) create cluster 0 config (2) deploy cluster 0 (3) create cluster을
수행합니다.

```
sh> export FBPATH=/root/local-cli/.flashbase
sh> fbcli

# create cluster 0 config
Do you want to create META CLUSTER config folder? (y/n) y
Please type host list(comma segmented)? default: [fb-node-0.fb-node-svc,fb-node-1.fb-node-svc]
How many ports do you need per one host? [3]

# deploy
[tsr2-installer.bin.flashbase_v1.1.10.centos] to cluster #0, deploy now? (y/n) [y]

# create cluster
Do you want to restart cluster? (y/n)
```

- FBPATH는 flashbase config가 존재하는 경로입니다. 환경변수로 정의해줍니다.
  (docs/dot-flashbase-structure-README.md 참조)
- .flashbase/clusters/template/ 아래에 기본값이 적혀 있고 이를 바탕으로 cluster 0이 생성됩니다.
  만약 기본값을 변경하고 싶으면 template 아래 파일을 수정하면 됩니다.
  
