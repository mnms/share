# config.yaml 
config.yaml은 인스톨, 배포, 클러스터 구성에 관한 컨피그 파일입니다. 
아래와 같습니다. 
```yaml
master_ports:
  from: 18100
  to: 18102
nodes:
- fb-node-0.fb-node-svc
- fb-node-1.fb-node-svc
prefix:
  flash_db_path: /sata_ssd/ssd_
  redis_data: /sata_ssd/ssd_
  redis_db_path: /sata_ssd/ssd_
release: tsr2-installer.bin.flashbase_v1.1.10.centos
slave_ports:
  enabled: true
  from: 18150
  to: 18152
ssd:
  count: 3
tsr2_service_dir: /root/tsr2
```

- nodes에는 클러스터를 구성할 호스트주소를 적어줍니다. 호스트이름 혹은 IP로 적습니다.
- master_ports, slave_ports는 클러스터 구성할 포트정보입니다. 만약 slave를 띄우지 않고자 한다면
slave_ports.enabled = false로 설정하면 됩니다.
- release에 인스톨할 flashbase 설치파일 정보를 적어줍니다. 해당 파일은 .flashbase/releases폴더에
있어야 인스톨 및 배포가 가능합니다.
- tsr2_service_dir은 flashbase가 설치될 루트 정보입니다.
- ssd.count, prefix 등은 저장소 등에서 사용하기 위해서 적습니다. 
