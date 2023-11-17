#!/bin/bash

# Ping targets to check connectivity, the default is cloudflare and google DNS addresses
TARGETS=("1.1.1.1" "1.0.0.1" "8.8.8.8" "8.8.4.4")
# How many failed pings are allowed before failover
FAILOVER_LIMIT=2
# The subnets that should be tunneled through wireguard
LOCAL_RANGES=("10.13.13.0/24")
# An array of tunnel details corresponding to the tunnel conf: <tunnel-name>;<table-number>;<rule-priority>
TUNNELS=("wg1;55111;10001" "wg2;55112;10002")
# Connectivity check interval in seconds
PING_INTERVAL=20
LOG_FILE="/config/wg_failover.log"

apply_rules () {
    for LOCAL_RANGE in "${LOCAL_RANGES[@]}"
    do
        ip rule del from ${LOCAL_RANGE} lookup $1
        ip rule add pref $2 from ${LOCAL_RANGE} lookup $1
    done
}

FAILED=()
INDEX=0
while sleep $PING_INTERVAL
do
    COUNTER=1
    IFS=";" read -r -a TUNNEL <<< "${TUNNELS[INDEX]}"
    TUNNEL_NAME="${TUNNEL[0]}"
    TUNNEL_TABLE=${TUNNEL[1]}
    TUNNEL_PRIORITY=${TUNNEL[2]}
    wg-quick up "${TUNNEL_NAME}" > /dev/null 2>&1

    for TARGET in "${TARGETS[@]}"
    do
        if ! ping -c1 -w10 -I "${TUNNEL_NAME}" "${TARGET}" > /dev/null 2>&1; then
          (( COUNTER++ ))
        fi
    done
    if [[ "$COUNTER" -gt "$FAILOVER_LIMIT" ]] && [[ ! "${FAILED[*]}" =~ "${TUNNEL_NAME}" ]]; then
        echo "$(date +'%Y-%m-%d %T') - ${TUNNEL_NAME} failed ${COUNTER} pings" >> $LOG_FILE
        apply_rules "${TUNNEL_TABLE}" "$(( TUNNEL_PRIORITY+1000 ))"
        FAILED+=(${TUNNEL_NAME})
    elif [[ "$COUNTER" -le "$FAILOVER_LIMIT" ]] && [[ "${FAILED[*]}" =~ "${TUNNEL_NAME}" ]]; then
        echo "$(date +'%Y-%m-%d %T') - ${TUNNEL_NAME} restored" >> $LOG_FILE
        apply_rules "${TUNNEL_TABLE}" "$(( TUNNEL_PRIORITY ))"
        FAILED=( "${FAILED[@]/$TUNNEL_NAME}" )
    elif [[ "$COUNTER" -gt "$FAILOVER_LIMIT" ]] && [[ "${FAILED[*]}" =~ "${TUNNEL_NAME}" ]]; then
        wg-quick down "${TUNNEL_NAME}" > /dev/null 2>&1
    fi
    (( INDEX++ ))
    if [[ $INDEX+1 > ${#TUNNELS[@]} ]]; then
        INDEX=0
    fi
done
