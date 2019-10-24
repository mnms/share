# sql manual

## 1. 사전준비
docs/k8s/install-k8s-README.md
docs/k8s/manual-basic-k8s-README.md

or

docs/native/install-aws-README.md
docs/native/install-9th-README.md
docs/native/manual-basic-aws-README.md

# Thriftserver edit

'thriftserver edit' 명령을 이용하여 HIVE_HOST를 알맞게 변경해준다. 

```
sh> fbcli
root@flashbase:1> thriftserver edit
# set HIVE_HOST
```

- thriftserver edit을 실행하면 vim 에디터로 thriftserver.properties파일이 열리는데
  여기에 HIVE_HOST를 설정하는 곳이 있다.(14 line) 여기에 fb-one-0의 ip정보를 적어주면 sql에
  관한 커맨드는 해당 호스트를 사용하게 됩니다. 

# Create table

이 단계에서는 테이블을 생성한다. 미리 준비해 놓은 파일(create-table.sql)을 이용하여 테이블을 생성한다.
동일한 명령은 fbcli접속 후 sql<enter>로 sql모드로 간 뒤 sql문을 적어서도 동일하게 이용할 수 있다.

```
sh> cd ~/local-cli/sql
sh> fbcli -uroot -pasdf -c 1 -f ./create-table.sql
create table complete
```

# Select table

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

