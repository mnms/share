# kubernetes local multi node cluster 구성 하기

## 0. 사전 준비

1. docker ce 18.06.1-ce-mac73 (26764) 이상의 버전을 준비합니다.
   [docker-ce-download](https://docs.docker.com/docker-for-mac/install/)
2. Docker 설정에서 Kubernetes를 Enable하고 Apply를 누릅니다.
   [docker-foc-mac-kubernetes](https://blog.alexellis.io/content/images/2018/01/Screen-Shot-2018-01-07-at-09.39.57.png)
3. kubectl이 작동하는지 체크

```bash
$ which kubectl
```

5. flashbase.tar 파일을 원하는 위치(이 문서에서는 ~/work로 가정)에 압축을 풉니다.

6. 아래를 실행하여 필요한 도커 이미지를 빌드합니다

```
> cd ~/cli_output/dockerfiles/flashbase
> ./build.sh v2
```

## 1. 폴더의 구성

주요 폴더의 구성은 다음과 같습니다.

```
flashbase
├── cli
│   ├── build
│   ├── dist
│   ├── fbcli
│   ├── fbcli.egg-info
│   ├── fire
│   ├── packages
│   ├── tsr2-assembly-1.0.0-SNAPSHOT
│   └── xxx_resources
├── dockerfiles
│   ├── cli
│   └── flashbase
├── docs
│   ├── from_skt
│   └── pipeline
├── exports
├── pipeline
│   ├── example-machine-learning
│   ├── iris
│   ├── sandbox
│   ├── scripts
│   └── telco-churn
├── sandbox
└── scripts

```

## 2. import

cli_output/dockerfiles/k8s-pv-cli.yaml.template 복사

```bash
$ cd ~/cli_output/dockerfiles
$ cp k8s-pv-cli.yaml.example k8s-pv-cli.yaml
```

- 그리고 파일 내용 중 아래 한 줄을 본인 경로에 맞게 수정해줍니다. (절대경로를 적어줍니다!)
  **path: "/PATH/TO/CLI/DIR/.../cli_output/cli"**

- 여기서 적어준 경로에 볼륨이 생성되고 도커 컨테이너에 마운트됩니다.
  만약 /home/user1/cli_output 경로에 코드를 설치했다면 /home/user1/cli_output/cli를 적어주면 됩니다.

[k8s-pv-cli.yaml.template](dockerfiles/k8s-pv-cli.yaml.example)

```yaml
kind: PersistentVolume
apiVersion: v1
metadata:
  name: local-cli-volume
  labels:
    type: local
spec:
  storageClassName: manual
  capacity:
    storage: 2Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: "/PATH/TO/CLI/DIR/.../cli_output/cli"
---
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: local-cli
spec:
  storageClassName: manual
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
```

이제 생성하면 하면 됩니다. 일단 따라해 주세요

```bash
$ cd ~/cli_output
$ kubectl apply -f ./dockerfiles/k8s-pv-cli.yaml

persistentvolume/local-cli-volume created
persistentvolumeclaim/local-cli created
```

잘 생성됬는지 확인

```bash
$ kubectl get pv

NAME               CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS    CLAIM               STORAGECLASS   REASON    AGE
local-cli-volume   2Gi        RWO            Retain           Bound     default/local-cli   manual                   2m
```

```bash
$ kubectl get pvc
NAME        STATUS    VOLUME             CAPACITY   ACCESS MODES   STORAGECLASS   AGE
local-cli   Bound     local-cli-volume   2Gi        RWO            manual         2m
```

이제 node들을 만들어 보겠습니다.

```bash
$ cd ~/cli_output
$ kubectl apply -f ./dockerfiles/k8s-cluster.yaml

statefulset.apps/fb-cli created
statefulset.apps/fb-node created
service/fb-node-svc created
```

처음 실행하면 시간이 조금 걸립니다.  
모두 running 상태가 될때까지 기다려주세요.

```bash
$ kubectl get pods

NAME        READY     STATUS    RESTARTS   AGE
fb-node-0   1/1       Running   0          1m
fb-node-1   1/1       Running   0          1m
fb-node-2   1/1       Running   0          58s
```

이제 아래 명령을 실행하면 interective sessions이 생깁니다.

```bash
$ kubectl exec -it fb-node-0 bash

(app-root)root@fb-node-0:~$
```

이제 이 세션안에서 아래 명령을 실행합니다.

```bash
ssh fb-node-0.fb-node-svc
```

접속이 됬습니다.

```bash
(app-root)root@fb-node-0:~$ ssh fb-node-1.fb-node-svc

Warning: Permanently added lib (RSA) to the list of known hosts.
root@fb-node-0:~#
```

숫자만 바꿔주면 각 노드로 접속할 수 있습니다.

```bash
ssh fb-node-0.fb-node-svc
ssh fb-node-1.fb-node-svc
ssh fb-node-2.fb-node-svc
```

ip도 한번 확인해보세요.

```bash
root@fb-node-0:~# ifconfig
eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.1.1.11  netmask 255.255.0.0  broadcast 0.0.0.0
        ether 42:0b:dd:c5:2d:6e  txqueuelen 0  (Ethernet)
        RX packets 56  bytes 6925 (6.7 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 31  bytes 5687 (5.5 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
        inet 127.0.0.1  netmask 255.0.0.0
        loop  txqueuelen 1  (Local Loopback)
        RX packets 0  bytes 0 (0.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 0  bytes 0 (0.0 B)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

root@fb-node-0:~#
```

그리고 fb-node-0 에 cli 소스들이 잘 mount됬는지도 확인해주세요.

```bash
(app-root)root@fb-node-0:~$ ls
anaconda-ks.cfg  local-cli

(app-root)root@fb-node-0:~$ tree local-cli/
local-cli/
├── fbcli.py
├── __init__.py
├── packages
│   ├── flashbase.py
│   └── __init__.py
└── README.md

1 directory, 5 files
(app-root)root@fb-node-0:~$
```

## cheatsheet

- \$SR2_HOME # flashbase 설치 경로
- /sata_ssd/ # 데이터 저장소
