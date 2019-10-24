# Tutorial aws

## Prerequisite

- install-aws-README.md

# 1. Meta cluster setting

설치를 하고 나면 fbcli가 설치되어 있으나 아직 meta data 저장을 위한 cluster (cluster 0)이
구동되어 있지 않은 상태이고 사용자 역시 생성되지 않은 상태입니다. 최초 fbcli 명령을 내릴 경우에는
필요한 cluster config를 생성하고 cluster를 배포 및 구동하는 과정을 먼저 수행하도록 구현하였습니다.

여기서는 (1) create cluster 0 config (2) deploy cluster 0 (3) create cluster을
수행합니다.

cluster 0번 생성은 ~/.flashbase/cluster/template/config.yaml파일을 이용하고 있습니다.
host list나 deploy 파일명을 변경하고 싶다면 아래와 같이 수행하면 됩니다.

```
vi ~/.flashbase/cluster/template/config.yaml
# change release, nodes info

tsr2_service_dir: /home/ubuntu/tsr2
release: tsr2-installer.bin.flashbase_v1.1.7.2.b.centos
nodes: ['172.31.28.159', '172.31.20.41']
ssd:
  count: 3
master_ports:
  from: 18000
  to: 18002
slave_ports:
  enabled: false
  from: 18050
  to: 18052
prefix:
  redis_data: /sata_ssd/ssd_
  redis_db_path: /sata_ssd/ssd_
  flash_db_path: /sata_ssd/ssd_
```

template을 수정하였다면 아래와 같이 실행합니다.

```
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

# 2. Setting adduser and setting password

2번 과정을 통해서 클러스터를 생성하였습니다. 이제 사용자를 생성할 단계입니다. flashbase는 기본적으로 root
유저 + no password로 구동할 수 있는 정책을 가지고 있습니다. 하지만 만약 사용자를 추가하거나 비밀번호를
설정해서 사용하고자 한다면 아래와 같은 명령을 통해서 쉽게 사용할 수 있습니다.

```
sh> fbcli
root@flashbase:0> adduser shhong
root@flashbase:0> exit

sh> fbcli -ushhong
root@flashbase:0> passwd
asdf
asdf

sh> fbcli -ushhong
asdf

shhong@flashbase:0>
```

# 3. Clone cluster from 0 to 1

이번에는 본격적으로 데이터 적재를 위한 클러스터를 생성하고자 합니다. 기본적인 흐름은 (1) config 생성
(2) deploy (3) create cluster입니다.

```
sh> fbcli -uroot
root@flashbase:0> cluster clone 0 1
root@flashbase:0> deploy
root@flashbase:0> cluster restart --cluster yes --force --reset
root@flashbase:0> cli ping --all
```

- cluster clone명령을 통해서 config를 생성합니다.
  해당 정보는 .flashbase/clusters/[N]에 생성됩니다.
- deploy명령을 통해서 배포합니다. .flashbase/releases아래에 있는 인스톨 파일을 배포합니다.
  배포할 대상은 .flashbase/clusters/1/config.yaml에 'release'에 적혀있는 파일입니다.
- 배포 후에는 redis cluster를 생성합니다. 기존 redis-trib.rb와 비슷한 명령어를 이용합니다.
- redis cluster가 정상적으로 생성되었는지 확인하기 위해서 'cli ping --all' 명령을 이용합니다.

# 4. Explore default commands

fbcli에서 사용할 수 있는 commands를 확인하도록 합니다. help를 이용하고자 할 때에는 '-- --help'
를 이용해서 확인할 수 있습니다. '?'를 이용해서 사용가능한 명령어를 조회하면 아래와 같습니다.

- adduser : 사용자 추가
- c : change cluster shortcut (cluster use N과 동일한 기능인데 단축키로 제공)
- cli : redis-cli command wrapper (cluster, config, info, ping, reset-info, reset-oom)
- cluster : trib.rb cluster command wrapper (clone, create, edit, ls, restart, start, stop, use)
- deploy : flashbase 실행파일 배포
- flashbase : 기존 flashbase shell script를 실행하는 명령어 (추후 제거)
- ll : change log level
- monitor : monitor flashbase logs
- passwd : change password of user
- sql : enter sql mode
- thriftserver : start, stop, monitor, edit thriftserver

각각에 대한 자세한 명령은 해당명령어 --help를 통해서 자세히 확인할 수 있습니다. 예를 들어서 cli cluster에
관한 사용법을 알고 싶다면 'cli cluster --help' 명령을 통해서 확인할 수 있습니다.

! 도움말에서 fbcli를 같이 적어주어야 하는 것처럼 나오고 있습니다. 이는 fire module에서 보여주는 도움말을 이용하면서 생긴 이슈입니다. fbcli를 무시하고 적으면 됩니다. (함께 적어도 작동은 합니다.)

# 5. Tips

## 5.1. 이미 구축한 클러스터와 연동하는 방법: cluster clone + cluster edit

이미 구축한 클러스터를 연동하고자 한다면 cluster clone후 cluster edit을 이용하면 됩니다.
cluster clone이 배포나 재시작을 포함하지 않고 있기 때문에 가능합니다.

예를 들어서 cluster 7번이 이미 구동되어있다면, 아래와 같이 fbcli에 클러스터 메타데이터를 생성합니다.

```
root@flashbase:0>c 0
root@flashbase:0>cluster clone 0 7
Cluster clone from 0 to 7
Please type host list(comma segmented)? default: [172.31.28.159,172.31.20.41]
Ok. 172.31.28.159,172.31.20.41
How many ports do you need per one host? [3]
Ok. 3
Type start port? [18700]
Ok. 18700
Type end port? [18702]
Ok. 18702
Cluster 7 selected.
```

그다음 cluster edit명령을 이용해서 ports, nodes, release등을 알맞게 고쳐줍니다.

```
root@flashbase:7>cluster edit
master_ports:
  from: 18700
  to: 18702
nodes:
- 172.31.28.159
- 172.31.20.41
prefix:
  flash_db_path: /sata_ssd/ssd_
  redis_data: /sata_ssd/ssd_
  redis_db_path: /sata_ssd/ssd_
release: tsr2-installer.bin.flashbase_v1.1.7.2.b.centos
slave_ports:
  enabled: false
  from: 18750
  to: 18752
ssd:
  count: 3
tsr2_service_dir: /home/ubuntu/tsr2
```

이제 cli ping --all 명령을 통해서 잘 연결되었는지 확인합니다.

## 5.2. debug mode

툴이 정상작동하지 않는 경우에는 디버그 모드로 띄우면 더욱 편리할 수 있습니다.

```
sh> fbcli --debug True
```

## next step

