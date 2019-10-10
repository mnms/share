# .flashbase folder structure
.flashbase folder는 배포, 설치, 구동, 모니터링 등에 관한 필요한 정보를 가지고 있습니다. 
구조는 아래와 같습니다. 

```
.flashbase/
|-- HEAD
|-- cli_history
|-- clusters
|   |-- 0
|   |   |-- config.yaml
|   |   `-- tsr2-conf
|   |       |-- redis-master.conf.template
|   |       |-- redis-slave.conf.template
|   |       |-- redis.properties
|   |       `-- thriftserver.properties
|   |-- N
|   |   |-- config.yaml
|   |   `-- tsr2-conf
|   |       |-- redis-master.conf.template
|   |       |-- redis-slave.conf.template
|   |       |-- redis.properties
|   |       `-- thriftserver.properties
|   `-- template
|       |-- config.yaml
|       `-- tsr2-conf
|           |-- redis-master.conf.template
|           |-- redis-slave.conf.template
|           |-- redis.properties
|           `-- thriftserver.properties
|-- data
|   `-- iris
|       |-- json
|       |   `-- test.json
|       `-- load
|           `-- iris.csv
|-- releases
|   `-- tsr2-installer.bin.flashbase_v1.1.10.centos
`-- sql_history

```

- HEAD는 현재 선택한 cluster #를 담고 있습니다. 
- cli_history, sql_history에는 기존에 사용한 명령어 목록입니다. 
- clusters 폴더 아래에 cluster # 폴더에 클러스터에 관한 정보를 담고 있습니다. 
- data는 튜토리얼을 위해 존재합니다. (추후 삭제)
- releases 폴더는 인스톨 파일을 위한 폴더입니다.

