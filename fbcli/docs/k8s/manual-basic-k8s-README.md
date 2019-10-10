# Install (host)

## Prerequisite

- k8s-local-cluster-setting-README.md
- install-k8s-README.md

# Setting adduser and setting password : fb-node-0

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

# Clone cluster from 0 to 1 : fb-node-0

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

# Explore default commands

fbcli에서 사용할 수 있는 commands를 확인하도록 합니다. help를 이용하고자 할 때에는 '--help'
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

# Load data into cluster 1 : fb-node-0

이 단계에서는 tutorial을 위해 준비해 놓은 iris데이터를 cluster 1에 적재하도록 합니다.
데이터는 .flashbase/data/iris 폴더 아래에 있습니다.

```
sh> fbcli -uroot
root@flashbase:1> flashbase ready-iris
root@flashbase:1> cli info keyspace
# Keyspace
db0:keys=12,memKeys=6,flashKeys=0,expires=6,avg_ttl=0
```

# Connect to fb-one-0 and load data : fb-one-0

- sql(create, select drop 등)을 테스트하기 위해서는 thriftserver등이 설치되어 있어야 한다.
  그런데 fb-node-N에는 thriftserver등이 설치되어 있지 않다.
  fb-one-0은 flashbase, thriftserver, redis cluster등이 모두 떠있는 컨테이너인데,
  sql 테스트를 위해서는 이를 사용한다. (정석적으로 한다면 fb-node-N 만을 이용하여 sql테스트를 해야 하는데
  프로젝트 막판에 해당 이미지를 준비하고 컨피그 설정하는 등의 여건이 부족하여 조금 기형적으로 구성하여 테스트를 진행하였다.)

- 정리하면 Install, meta cluster setting, deploy, manage cluster에 관한 모든 명령은
  fb-node-N을 이용하여 테스트를 하고 sql에 관련한 테스트만 fb-one-0을 이용하여 테스트한다.

- 아래는 fb-one-0에 접속하여 cluster 1에 적재했던 것과 동일한 iris 데이터를 적재하는 명령이다.

```
host-sh> k exec -it fb-one-0 bash
# load data
sh> tsr2-tools insert -d /root/local-cli/.flashbase/data/iris/load/ -s "," -t /root/local-cli/.flashbase/data/iris/json/test.json -p 8 -c 1 -i
```

# Thriftserver edit : fb-node-0

위에서 설명한 것과 같이 sql관련한 테스트는 fb-one-0을 이용하기 때문에 이에 관한 설정을 cluster 0에
해주어야 한다. 해당 설정은 'thriftserver edit' 명령을 이용해서 할 수 있다.

```
sh> fbcli
root@flashbase:1> thriftserver edit
# check ip of fb-one-0 (using ifconfig) and set HIVE_HOST
```

- thriftserver edit을 실행하면 vim 에디터로 thriftserver.properties파일이 열리는데
  여기에 HIVE_HOST를 설정하는 곳이 있다.(14 line) 여기에 fb-one-0의 ip정보를 적어주면 sql에
  관한 커맨드는 fb-one-0을 이용하게 된다.

# Create table in fb-node-0 : fb-node-0

이 단계에서는 테이블을 생성한다. 미리 준비해 놓은 파일(create-table.sql)을 이용하여 테이블을 생성한다.
동일한 명령은 fbcli접속 후 sql<enter>로 sql모드로 간 뒤 sql문을 적어서도 동일하게 이용할 수 있다.

```
sh> cd ~/local-cli/sql
sh> fbcli -uroot -pasdf -c 1 -f ./create-table.sql
create table complete
```

# Select table in fb-node-0 : fb-node-0

이 단계에서는 테이블 조회를 할 수 있다. 미리 준비해놓은 파일(select-table.sql)을 이용하여 조회한다.
조회한 결과는 csv포멧이다.

```
sh> cd ~/local-cli/sql
sh> fbcli -uroot -pasdf -c 1 -f ./select-table.sql > output.csv
```

# Check table metadata

cluster 0에 테이블에 관련한 메타데이터를 저장하고 있다. 위에서 테이블 생성명령을 내렸기 때문에,
fbcli > sql에서 테이블에 관한 정보를 확인할 수 있다.

```

sh> fbcli
root@flashbase:1> sql
root@flashbase:sql:1> table list;
root@flashbase:sql:1> table info iris;

```
