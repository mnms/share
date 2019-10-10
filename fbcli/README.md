# Fbcli Guide

[Installing Prerequisites](#installing-prerequisites)

[Fbcli Install](#fbcli-install)

[Fbcli 실행하기](#fbcli-실행하기)

[Deploy](#deploy)

[클러스터 생성](#클러스터-생성)

[Version Update](#version-update)

[Logging in file](#logging-in-file)



## Installing Prerequisites

* [Installing prerequisites for flashbase](https://github.com/mnms/share#installing-prerequisites)

* Python 2.7



## Fbcli Install

 

```
$ cd ~/fbcli
$ sh install.sh


    ________    ___   _____ __  ______  ___   _____ ______
   / ____/ /   /   | / ___// / / / __ )/   | / ___// ____/
  / /_  / /   / /| | \__ \/ /_/ / __  / /| | \__ \/ __/
 / __/ / /___/ ___ |___/ / __  / /_/ / ___ |___/ / /___
/_/   /_____/_/  |_/____/_/ /_/_____/_/  |_/____/_____/

Start to install FlashBaseCLI
Obtaining file:///home/dudaji/fbcli

...

Complete to install FlashBaseCLI!

To start using fbcli, you should set flashbase path in env FBPATH and PATH
ex)
export FBPATH=$HOME/fbcli/.flashbase
export PATH=$PATH:$HOME/.local/lib/python2.7/site-packages/
```

정상적으로 설치에 성공하면 "Complete to install FlashBaseCLI!" 메세지가 나타납니다.

환경변수 FBPATH와 PATH를 설정이 필요합니다. 설정값은 실행환경마다 다를 수 있습니다.

FBPATH: <설치 경로>/fbcli/.flashbase

PATH: [링크](https://pip.pypa.io/en/stable/user_guide/#user-installs) 참조



## Fbcli 실행하기

fbcli 설치 후 다음과 같이 `fbcli` 명령어를 통해 fbcli에 접속할 수 있습니다.

```
$ fbcli
```



fbcli 최초접속시 base_directory를 물어봅니다. base_directory는 flashbase의 root path 입니다.

> 대괄호 안의 값은 default value이며 아무값도 입력하지 않으면 default value가 선택됩니다.
>
> 질의에 따라 default value가 없을 수도 있습니다.

```
Type base directory of flashbase [~/tsr2]
~/tsr2
OK, ~/tsr2
```

존재하지 않는 디렉토리인 경우 자동적으로 생성됩니다.  `edit` 명령어를 이용하여 base_directory 를 수정할 수 있습니다.



정상적으로 접속이 되면 가장 최근에 접속했던 cluster에 접속되며 없는 경우 `-` 로 표시됩니다.

fbcli 접속 시 prompt 형식은 `<user-name>@flashbase:<cluster-id>>` 입니다.

```
root@flashbase:->
```



만약 기존에 flashbase가 운영중인 환경에서 fbcli를 설치하는 경우 `import-conf` 명령어를 사용하세요.

```
root@flashbase:-> import-conf
Diff fb and cli conf folders.
+------------+------------------+
| cluster_id | state            |
+------------+------------------+
| 1          | IMPORT           |
+------------+------------------+
| 2          | SKIP(dest_exist) |
+------------+------------------+
| 3          | SKIP(broken)     |
+------------+------------------+
Do you want to import conf? (y/n)
y
Save config.yaml from redis.properties
Cluster - selected.
root@flashbase:->
```



`import-conf` 의 state의 종류는 다음과 같습니다.

* IMPORT: import가 가능한 클러스터 입니다. flashbase의 설정을 fbcli로 가져옵니다.

* SKIP(dest_exist): 이미 import 되어있는 클러스터 입니다.

* SKIP(broken): 설치 중 중단 등의 이유로 정상적인 상태가 아닌 클러스터 입니다.



import가 가능한 cluster가 있는 경우 import 진행 여부를 물어봅니다. `y` 를 선택하는 경우 import가 진행됩니다.



## Deploy

deploy는 flashbase를 실행시키기 위한 설치과정입니다. 클러스터마다 deploy가 이루어져야 합니다.

```
root@flashbase:-> deploy 32
```

cluster id를 생략하는 경우 현재 접속중인 cluster를 기준으로 진행합니다.



#### installer 선택

```
Select installer

    [ INSTALLER LIST ]
    (1) tsr2-installer.bin.flashbase_v1.1.10.centos
    (2) tsr2-installer.bin.flashbase_v1.1.09.centos
    (3) tsr2-installer.bin.flashbase_v1.1.08.centos

Please enter the number or the path of the installer you want to use
1
```

installer를 선택합니다. 목록에 추가하고 싶은 경우  `$FBPATH/releases` 경로 아래에 installer를 복사하세요.

숫자입력을 통해 선택할 수 있으며, 만약 목록 외에서 선택하고 싶다면 installer의 절대경로를 입력하세요. 

ex)  `~/tsr2-installer.bin.flashbase_v1.1.10.centos`



#### node 입력

```
Please type host list. (separate by comma) [localhost]
nodeA, nodeB, nodeC, nodeD
OK, ['nodeA', 'nodeB', 'nodeC', 'nodeD']
```

ip주소 혹은 hostname을 입력합니다. 여러 개를 입력하는 경우 쉼표(,)를 구분자로 사용하세요.

가장 최근에 입력했던 값을 default value로 보여줍니다.

현재 입력하는 값이 default value로 저장되지 않도록 하려면 deploy시 `--save=False` 옵션을 주세요.



#### master 정보 입력

```
How many masters would you like to create on each node? [1]
1
OK, 1
Please type ports. Use hyphen(-) for range. [21200]
21200
OK, ['21200']
```

각 노드에 몇 개의 master 를 생성할지 입력합니다. 만약 5개 노드를 선택했고 1를 입력한다면 총 5개의 master 가 생성됩니다. 범위로 입력하는 경우 하이픈(-)을 사용하세요 ex) `21200-21202`

port 번호는 cluster id를 기반으로 추천해줍니다.



#### slave 정보 입력

```
How many replicas would you like to create on each master? [2]
2
OK, 2
Please type ports. Use hyphen(-) for range. [21250-21251]
21250-21251
OK, ['21250-21251']
```

각 master 마다 몇 개의 slave를 생성할 지 입력합니다. 만약 5개의 마스터를 생성하고 2를 입력한다면 총 10개의 slave가 생성됩니다.

port 번호는 cluster id를 기반으로 추천해줍니다.



#### 그 외 정보 입력

```
How many sdd would you like to use? [3]
3
OK, 3
Type prefix of redis_data_path [~/ssd_]
/sata_ssd/ssd_
Type prefix of redis_db_path [~/ssd_]
/sata_ssd/ssd_
Type prefix of flash_db_path [~/ssd_]
/sata_ssd/ssd_
```

가장 최근에 입력했던 값을 default value로 보여줍니다.

현재 입력하는 값이 default value로 저장되지 않도록 하려면 deploy시 `--save=False` 옵션을 주세요.



#### 정보확인

```
+-----------------+---------------------------------------------+
| NAME            | VALUE                                       |
+-----------------+---------------------------------------------+
| installer       | tsr2-installer.bin.flashbase_v1.1.10.centos |
| nodes           | nodeA                                       |
|                 | nodeB                                       |
|                 | nodeC                                       |
|                 | nodeD                                       |
| master ports    | ['21200']                                   |
| slave ports     | ['21250-21251']                             |
| ssd count       | 3                                           |
| redis data path | /sata_ssd/ssd_                              |
| redis db path   | /sata_ssd/ssd_                              |
| flash db path   | /sata_ssd/ssd_                              |
+-----------------+---------------------------------------------+
Do you want to proceed with the deploy accroding to the above information? (y/n)
y
```

모든 정보입력이 완료되면 위와 같이 입력한 정보들을 확인합니다. `n` 을 선택하면 deploy가 취소됩니다.



#### Deploy 진행

```
Check status of nodes...
+-----------+--------+
| NODE      | STATUS |
+-----------+--------+
| nodeA     | OK     |
| nodeB     | OK     |
| nodeC     | OK     |
| nodeD     | OK     |
+-----------+--------+
Check lagacy...
Transfer install and execute...
Set up info...
Complete to deploy cluster 32
Cluster 32 selected.
root@flashbase:32>
```

deploy가 성공적으로 진행되면 위와 같은 메세지들과 함께 완료된 후 클러스터에 접속이 됩니다.

deploy가 완료되었다면 `import-conf` 명령어를 통해 import 를 진행해주세요.



```
root@flashbase:32> import-conf
Diff fb and cli conf folders.
+------------+--------+
| cluster_id | state  |
+------------+--------+
| 32         | IMPORT |
+------------+--------+
Do you want to import conf? (y/n)
y
Save config.yaml from redis.properties
```



#### Deploy 진행 중 오류 발생시

* NodeError

```
Check status of nodes...
+-------+------------------+
| NODE  | STATUS           |
+-------+------------------+
| nodeA | OK               |
| nodeB | SSH ERROR        |
| nodeC | UNKNOWN HOST     |
| nodeD | CONNECTION ERROR |
+-------+------------------+
```

UNKNOWN HOST: hostname을 통해 ip주소를 가져올 수 없는 경우입니다. `/etc/hosts` 등을 확인하세요.

CONNECTION ERROR: 해당 node에 ping이 나가지 않는 경우입니다. 해당 node의 상태를 점검하세요.

SSH ERROR: ssh 접속 오류입니다. key 교환상태 혹은 ssh client/server 상태를 점검하세요



* ClusterError

```
Check lagacy...
+-------+---------------+
| NODE  | STATUS        |
+-------+---------------+
| nodeA | OK            |
| nodeB | OK            |
| nodeC | CLUSTER EXIST |
| nodeD | CLUSTER EXIST |
+-------+---------------+
```

CLUSTER EXIST: 해당 node에 이미 deploy가 진행된 이력이 있는 경우입니다.

deploy가 진행 중 중단되는 경우에는 `CLUSTER EXIST` 가 뜨지 않습니다.

 `--force` 옵션을 통해 무시하고 진행할 수 있습니다. 이 경우 cluster 정보는 각 노드에 백업이 됩니다.



## 클러스터 생성

deploy가 완료되었다면 클러스터 생성을 진행할 수 있습니다.


#### redis 실행

```
root@flashbase:32> cluster start
update_redis_conf complete
[M] Start redis (nodeA:21200)
[S] Start redis (nodeA:21250)
[S] Start redis (nodeA:21251)

...

[S] Start redis (nodeD:21251)
start_redis_process complete.
All redis process up complete
```

클러스터를 구성하기 위해서 클러스터를 구성하기 위한 redis들을 먼저 실행시켜야 합니다.



#### 클러스터 구성하기

```
root@flashbase:32> cluster create
>>> Creating cluster
+-------+-------+--------+
| NODE  | PORT  | TYPE   |
+-------+-------+--------+
| nodeA | 21200 | MASTER |
| nodeB | 21200 | MASTER |
| nodeC | 21200 | MASTER |
| nodeD | 21200 | MASTER |
| nodeA | 21250 | SLAVE  |
| nodeA | 21251 | SLAVE  |
| nodeB | 21250 | SLAVE  |
| nodeB | 21251 | SLAVE  |
| nodeC | 21250 | SLAVE  |
| nodeC | 21251 | SLAVE  |
| nodeD | 21250 | SLAVE  |
| nodeD | 21251 | SLAVE  |
+-------+-------+--------+
Do you want to proceed with the create according to the above information? (y/n)
y
replicas: 2.00
replicate [M] nodeA 21200 - [S] nodeA 21250

...

replicate [M] nodeD 21200 - [S] nodeD 21251
1 / 8 meet complete.
2 / 8 meet complete.

...

8 / 8 meet complete.
create cluster complete.
```

 `cluster create` 명령어를 통해 클러스터를 구성합니다.

create를 시작하기 전에 구성정보를 확인하는 절차를 거칩니다.



#### 정보 확인

다음 명령어들을 통해 클러스터 상태 및 정보를 확인할 수 있습니다.

* `cli ping --all`

* `cli cluster info`

* `cli cluster nodes `



#### 클러스터 구성 중 오류 발생 시

* ClusterError

```
root@flashbase:32> cluster create
>>> Creating cluster
+-------+-------+--------+
| NODE  | PORT  | TYPE   |
+-------+-------+--------+
| nodeA | 21200 | MASTER |
| nodeB | 21200 | MASTER |
| nodeC | 21200 | MASTER |
| nodeD | 21200 | MASTER |
| nodeA | 21250 | SLAVE  |
| nodeA | 21251 | SLAVE  |
| nodeB | 21250 | SLAVE  |
| nodeB | 21251 | SLAVE  |
| nodeC | 21250 | SLAVE  |
| nodeC | 21251 | SLAVE  |
| nodeD | 21250 | SLAVE  |
| nodeD | 21251 | SLAVE  |
+-------+-------+--------+
Do you want to proceed with the create according to the above information? (y/n)
y
Node nodeA:21200 is already in a cluster
```

해당 redis가 이미 클러스터로 구성되어 있는 경우입니다. 해당 redis를 포함하는 클러스터에서 `cluster clean` 명령어를 통해 클러스터를 해제를 먼저 해야합니다.

해당 redis들을 클러스터에서 강제로 해제시킨 후 구성하려면 `cluster restart --force --reset` 을 사용하세요.



* Connection Error

```
root@flashbase:32> cluster create
>>> Creating cluster
+-------+-------+--------+
| NODE  | PORT  | TYPE   |
+-------+-------+--------+
| nodeA | 21200 | MASTER |
| nodeB | 21200 | MASTER |
| nodeC | 21200 | MASTER |
| nodeD | 21200 | MASTER |
| nodeA | 21250 | SLAVE  |
| nodeA | 21251 | SLAVE  |
| nodeB | 21250 | SLAVE  |
| nodeB | 21251 | SLAVE  |
| nodeC | 21250 | SLAVE  |
| nodeC | 21251 | SLAVE  |
| nodeD | 21250 | SLAVE  |
| nodeD | 21251 | SLAVE  |
+-------+-------+--------+
Do you want to proceed with the create according to the above information? (y/n)
y
nodeD:21200 - [Errno 111] Connection refused
```

해당 redis가 실행중이 아닌 경우 발생합니다. `cluster start` 명령어를 통해 먼저 redis를 실행시켜야 합니다.



## Version Update

flashbase version을 변경하고 싶다면 재설치를 위해 `deploy` 명령어를 사용합니다.

> 클러스터에 접속하지 않고 argument로 클러스터 번호를 주어도 됩니다.
>
> ```
> root@flashbase:-> deploy 32
> ```



#### Deploy

```
root@flashbase:-> c 32
root@flashbase:32> deploy
(Watch out) Cluster 32 is already deployed. Do you want to deploy again? (y/n) [n]
y
```



#### Installer

```
Select installer

    [ INSTALLER LIST ]
    (1) tsr2-installer.bin.flashbase_v1.1.10.centos
    (2) tsr2-installer.bin.flashbase_v1.1.09.centos
    (3) tsr2-installer.bin.flashbase_v1.1.08.centos

Please enter the number or the path of the installer you want to use
1
```



#### Restore

```
Do you want to restore conf? (y/n)
y
```

현재 설정값을 그대로 사용할 것인지 물어봅니다. `y` 를 선택합니다.

cluster와 conf 백업은 기본적으로 진행됩니다.

> cluster는 각 노드의 `<base_directory>/backup` 아래에 백업이 진행됩니다.
>
> conf는 fbcli를 실행중인 노드의 `$FBPATH/conf_backup` 아래에 백업이 진행됩니다.



#### 정보확인 및 진행

```
+-----------+---------------------------------------------+
| NAME      | VALUE                                       |
+-----------+---------------------------------------------+
| installer | tsr2-installer.bin.flashbase_v1.1.10.centos |
| nodes     | nodeA                                       |
|           | nodeB                                       |
|           | nodeC                                       |
|           | nodeD                                       |
| restore   | True                                        |
+-----------+---------------------------------------------+
Do you want to proceed with the deploy accroding to the above information? (y/n)
y
Check status of nodes...
+-----------+--------+
| NODE      | STATUS |
+-----------+--------+
| nodeA     | OK     |
| nodeB     | OK     |
| nodeC     | OK     |
| nodeD     | OK     |
+-----------+--------+
Backup conf of cluster 32...
OK, cluster_32_conf_bak_<time-stamp>
Backup info of cluster 32 at nodeA...
OK, cluster_32_bak_<time-stamp>
Backup info of cluster 32 at nodeB...
OK, cluster_32_bak_<time-stamp>
Backup info of cluster 32 at nodeC...
OK, cluster_32_bak_<time-stamp>
Backup info of cluster 32 at nodeD...
OK, cluster_32_bak_<time-stamp>
Transfer installer and execute...
Complete to deploy cluster 32
Cluster 32 selected.
root@flashbase:32>
```



## Logging in fole

`fbcli/logs` 아래에 debug 수준의 로그가 저장됩니다.

최대 1Gi만큼 저장하며 초과하는 경우 최신순으로 rolling update가 진행됩니다.