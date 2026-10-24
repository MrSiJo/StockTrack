#!/bin/sh
# Real client IP behind a reverse proxy, run by the nginx image's entrypoint.
#
# Behind an HTTPS reverse proxy every request reaches this nginx from the
# proxy's address, so $remote_addr (and the X-Forwarded-For entry nginx
# appends for the API) is the proxy for every browser, and the API's login
# and setup rate limits collapse into one shared bucket.
#
# REAL_IP_FROM lists the proxies to trust, space separated (addresses or
# CIDRs, IPv4 or IPv6). For each one nginx takes the client address from the
# right most X-Forwarded-For entry, the one that proxy appended itself.
# real_ip_recursive stays off, so nothing further left (which the client
# controls) is ever used. Unset or blank: no proxy is trusted and
# $remote_addr stays the TCP peer, as before.
#
# Trust only what can actually reach this port: a trusted address can set
# any client IP it likes. Typically that is the private (RFC 1918) ranges
# with the published UI port firewalled so only the reverse proxy reaches it.
set -eu
set -f  # no globbing when splitting REAL_IP_FROM

out="${STOCKTRACK_REAL_IP_CONF:-/etc/nginx/stocktrack/real-ip.conf}"
mkdir -p "$(dirname "$out")"
trap 'rm -f "$out.tmp"' EXIT

{
  echo "# Written at container start from REAL_IP_FROM; do not edit."
  if [ -n "$(echo "${REAL_IP_FROM:-}" | tr -d ' \t')" ]; then
    for entry in ${REAL_IP_FROM}; do
      case "$entry" in
        *[!0-9A-Fa-f.:/]* | "" | */*/* )
          echo "REAL_IP_FROM: not an address or CIDR: $entry" >&2
          exit 1
          ;;
      esac
      case "$entry" in
        *[0-9A-Fa-f]*) ;;
        *)
          echo "REAL_IP_FROM: not an address or CIDR: $entry" >&2
          exit 1
          ;;
      esac
      echo "set_real_ip_from $entry;"
    done
    echo "real_ip_header X-Forwarded-For;"
    echo "real_ip_recursive off;"
  fi
} > "$out.tmp"
mv "$out.tmp" "$out"
