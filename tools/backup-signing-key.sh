#!/usr/bin/env bash
# Encrypted backup of the release signing key (issue #5). Android only installs updates
# signed with the same key, so if it's lost, everyone has to uninstall and reinstall.
#
#   tools/backup-signing-key.sh [file]
#
# Makes one file, encrypted with a passphrase you type twice. Keep the file in two places
# (for example iCloud Drive and a USB stick) and the passphrase in your password manager.
# Inside: the keystore, its password, and RESTORE.txt with the alias, the fingerprint and
# how to put it all back. The default file lands in .backup/, which git ignores, so
# VS Code can download it (right-click → Download).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
src=${PLEATVIEW_RELEASE_DIR:-$HOME/.pleatview-release}
out=${1:-$root/.backup/pleatview-signing-key-$(date +%Y-%m-%d).tar.gpg}
if [ ! -f "$src/pleatview-release.jks" ] || [ ! -f "$src/password.txt" ]; then
  echo "No pleatview-release.jks and password.txt in $src" >&2
  exit 1
fi
mkdir -p "$(dirname "$out")"
note=$(mktemp -d)
trap 'rm -r -- "$note"' EXIT
cat > "$note/RESTORE.txt" <<NOTE
PleatView release signing key, backed up $(date -u +%Y-%m-%d)

Keystore:  pleatview-release.jks (PKCS12)
Alias:     pleatview
Password:  password.txt (one line), for the keystore and the key alike
SHA-256:   27:7B:CC:FA:72:E6:00:CE:D2:58:EF:9B:C4:DE:43:C6:FA:2F:27:53:8A:98:59:B2:C6:F2:EC:7C:34:3A:E3:73
Valid:     28 October 2026 to 15 March 2054

To restore:
1. Decrypt it:  gpg -d pleatview-signing-key-<date>.tar.gpg | tar x
2. On the build machine, put both files in ~/.pleatview-release/ with chmod 600.
3. In GitHub, Hustlesman/pleatview → Settings → Secrets and variables → Actions:
     PLEATVIEW_KEYSTORE_BASE64    output of: base64 -w0 pleatview-release.jks
     PLEATVIEW_KEYSTORE_PASSWORD  the line in password.txt
     PLEATVIEW_KEY_ALIAS          pleatview
     PLEATVIEW_KEY_PASSWORD       the line in password.txt
4. Check: keytool -list -v -keystore pleatview-release.jks shows the SHA-256 above.
NOTE
tar -cf - -C "$src" pleatview-release.jks password.txt -C "$note" RESTORE.txt \
  | gpg --symmetric --cipher-algo AES256 --pinentry-mode loopback --output "$out"
chmod 600 "$out"
echo
echo "Encrypted backup: $out"
echo "It holds:"
gpg --quiet --pinentry-mode loopback --decrypt "$out" | tar -t | sed 's/^/  /'
