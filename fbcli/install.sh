#!/usr/bin/env bash

set -e

RED='\033[0;31m'
NO_COLOR='\033[0m'
LIGHT_BLUE='\033[1;34m'
YELLOW='\033[0;33m'
LIGHT_YELLOW='\033[1;33m'

set_print_color() {
  printf "$1"
}

# trap ctrl-c and call ctrl_c()
trap ctrl_c INT
trap_flg=0

function ctrl_c() {
  trap_flg=1
}

err_flg=0


set_print_color ${LIGHT_YELLOW}
printf "
    ________    ___   _____ __  ______  ___   _____ ______
   / ____/ /   /   | / ___// / / / __ )/   | / ___// ____/
  / /_  / /   / /| | \__ \/ /_/ / __  / /| | \__ \/ __/
 / __/ / /___/ ___ |___/ / __  / /_/ / ___ |___/ / /___
/_/   /_____/_/  |_/____/_/ /_/_____/_/  |_/____/_____/

"
set_print_color ${NO_COLOR}

set_print_color ${LIGHT_BLUE}
printf "Start to install FlashBaseCLI\n"
set_print_color ${NO_COLOR}

dir_path=$(dirname "$0")

pip install --user -e ${dir_path} || err_flg=1
if [ ${err_flg} -eq 1 ]; then
  if [ ${trap_flg} -ne 1 ]; then
    set_print_color ${RED}
    printf "[INSTALL ERROR] cannot find module: fbcli\n"
    set_print_color ${NO_COLOR}
  fi
  exit 1;
fi

pip install \
  --user \
  --no-index \
  --find-links="${dir_path}/pip_modules" \
  -r "${dir_path}/requirements.txt"|| err_flg=1
if [ ${err_flg} -eq 1 ]; then
  if [ ${trap_flg} -ne 1 ]; then
    set_print_color ${RED}
    printf "[INSTALL ERROR] check network or directory 'pip_modules'\n"
    set_print_color ${NO_COLOR}
  fi
  exit 1;
fi

set_print_color ${LIGHT_BLUE}
printf "\n"
printf "Complete to install FlashBaseCLI!\n"
printf "\n"
set_print_color ${NO_COLOR}

SCRIPT_PATH=$( cd "$(dirname "$0")" ; pwd )
printf "To start using fbcli, you should set flashbase path in env FBPATH and PATH\n"
printf "ex)"
printf "\n"
printf "export FBPATH=${SCRIPT_PATH}/.flashbase\n"
printf "export PATH=\$PATH:\$HOME/.local/lib/python2.7/site-packages/"
printf "\n"
