# Code review

## 1. Skill set

- fire
- prompt-toolkit
- click
- redis-py-cluster
- hiredis

cli/requirements.txt에서 더 자세한 정보를 확인할 수 있습니다.

## 2. Skeleton

```
./cli/
.
├── LICENSE
├── README.md
├── docs # documents
├── fbcli # source code
├── install.sh # install script
├── pip_modules # collection of pip modules for offline install
├── requirements.txt # pip requirements
├── setup.py # setup filei for install fbcli
└── sql # sample sql scripts
```

## 3. Seq diagram

### Basic flow

```mermaid
sequenceDiagram
participant User
participant Main
participant Fire
User->Main: Insert command
Note left of Main: command text
Main->Fire: fire 'Command' class
Note left of Fire: Parse 'Command' </br> Execute Func
```

### Cli ping flow

```mermaid
sequenceDiagram
participant User
participant Cli
participant Net
participant SSHClient
participant Node
User->Cli: cli ping
Cli->Net: cli ping
Net->SSHClient: cli ping
SSHClient->Node: redis-cli ping
Node-->Net: stdout / stderr
```
