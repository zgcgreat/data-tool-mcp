#!/usr/bin/env bash
# 还原前端代码重命名：.txt -> .ts, .md -> .tsx
set -e
cd "$(dirname "$0")"
MANIFEST="${1:-rename_manifest.txt}"
[ -f "$MANIFEST" ] || { echo "找不到清单 $MANIFEST"; exit 1; }
while IFS='|' read -r new old; do
  [ -z "$new" ] && continue
  if [ -f "$new" ]; then
    mv -f "$new" "$old"
    echo "restored: $new -> $old"
  else
    echo "skip (not found): $new"
  fi
done < "$MANIFEST"
echo "还原完成"
