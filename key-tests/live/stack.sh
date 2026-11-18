#!/bin/bash
# usage: stack.sh run <name> [-e K=V ...] -- <cmd...>   (detached container r05-rq-<name>)
#        stack.sh exec <cmd...>                          (one-shot)
L=${LABDIR:-/root/johto-05r/labs/rq/redash}; NET=r05-rq
COMMON="-v /root/johto-05r/labs/rq/tools:/tools --network $NET -v $L:/app -w /app -e REDASH_REDIS_URL=redis://redis:6379/0 -e REDASH_DATABASE_URL=postgresql://postgres@postgres/${PGDB:-postgres} -e REDASH_COOKIE_SECRET=c00kie -e REDASH_SECRET_KEY=s3cret -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e REDASH_VERSION_CHECK=false -e REDASH_LOG_LEVEL=${LOGLEVEL:-INFO}"
cmd=$1; shift
case $cmd in
 run)
  name=$1; shift
  extra=""
  while [ "$1" != "--" ]; do extra="$extra $1"; shift; done; shift
  docker rm -f r05-rq-$name >/dev/null 2>&1
  docker run -d --name r05-rq-$name --network-alias $name $COMMON $extra --entrypoint "" r05-redash:pin "$@" >/dev/null && echo started r05-rq-$name;;
 exec)
  extra=""
  while [ "$1" != "--" ]; do extra="$extra $1"; shift; done; shift
  docker run --rm $COMMON $extra --entrypoint "" r05-redash:pin "$@";;
esac
