# aws install

aws에 fbcli를 설치하고 구동하는 방법에 대한 가이드 문서입니다.

## 1. copy code to server

- code를 서버에 올립니다. 우선 git을 이용해서 로컬에 싱크를 맞춘 다음에 서버에 코드를 rsync를
  이용해서 올립니다.

_in local PC_

```
$ cd ~
$ git clone https://tde.sktelecom.com/stash/scm/flbscli/cli_output.git
$ ls ~/cli_output
README.md  cli  dockerfiles  scripts

# 이미 클론을 받은 경우,
$ git pull


# 로컬에 싱크를 완료했으면 서버에 올립니다. 이 때 rsync를 사용합니다.
$ cd ~/cli_output ; \
rsync -avzh \
--exclude=**/*.pyc \
--exclude=*.tar \
--exclude=.idea \
--exclude=.git \
--exclude=**/__pycache__ \
-e "ssh -i ~/.ssh/FB-GIS.pem" \
./ \
ubuntu@ec2-13-125-255-185.ap-northeast-2.compute.amazonaws.com:/home/ubuntu/cli_output
```

_check server_

```
# 서버에 ssh 접속한 뒤, 코드를 확인합니다.
$ ssh -i ~/.ssh/FB-GIS.pem ubuntu@ec2-13-125-255-185.ap-northeast-2.compute.amazonaws.com
ubuntu@ec2-13-125-255-185$ ls ~/cli_output
README.md build cli dockerfiles scripts
```

## 2. install

1과정을 통해서 최신 코드를 서버에 옮겨두었습니다. 이제는 fbcli를 설치해야 합니다.

## 2.1. install package

apt-get, pip을 이용하여 필요한 패키지를 설치합니다. 아래와 같이 실행하면 됩니다.

```
sudo apt-get install libsasl2-dev
cd /home/ubuntu/cli_output/cli
sudo ./install.sh
```

- 이 과정에서 만약 hiredis가 설치가 이미 되어 있으면 에러가 날 수 있습니다.
  만약 그렇다면 pip uninstall hiredis를 한 뒤 진행하면 됩니다.

## 2.2. copy .flashbase and setting FBPATH

.flashbase 폴더를 복사해줍니다. 여기에 클러스터에 관한 메타데이터가 존재합니다.

```
cp -r ~/cli_output/cli/.flashbase ~
echo 'export FBPATH=/home/ubuntu/.flashbase' >> ~/.bashrc
. ~/.bashrc
```

## 2.3. (optional) symbolic link for deploy folder

~/deploy 폴더에 flashbase.feature.support_release_options.0fa891.bin등의 배포파일이 있습니다.
fbcli에서 배포를 위해서 이러한 설치파일을 releases folder아래에 넣어야 합니다.
단순히 cp ~/deploy/\* ~/.flashbase/releases를 이용해서 옮겨도 좋지만 수고와 실수를 줄이기 위해서 심볼릭 링크를 이용하면 더 좋습니다.

```
ln -s ~/.flashbase/releases ~/deploy
```

이제 필요한 모든 설치를 완료했습니다.

## 3. fbcli tutorial

실행, 사용자설정, 기본적인 문법은 아래 문서를 참고합니다.

manual-basic-aws-README.md
