#!/bin/bash

set -euo pipefail

CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ADVID="1636212376671237"

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "Google Chrome not found: $CHROME_BIN" >&2
  exit 1
fi

WORK_DIR="$(mktemp -d /tmp/tiktok-cookie-injector.XXXXXX)"
PROFILE_DIR="$WORK_DIR/profile"
EXT_DIR="$WORK_DIR/extension"

mkdir -p "$PROFILE_DIR" "$EXT_DIR"

cat > "$EXT_DIR/manifest.json" <<'EOF'
{
  "manifest_version": 3,
  "name": "Temporary TikTok Cookie Injector",
  "version": "1.0.0",
  "permissions": ["cookies", "tabs"],
  "host_permissions": [
    "https://ads.tiktok.com/*"
  ],
  "background": {
    "service_worker": "background.js"
  }
}
EOF

cat > "$EXT_DIR/background.js" <<'EOF'
const cookieInfo = {
  name: "sid_tt_ads",
  value: "fd8fc3d9edff27b7fa5732e2a0ec10e4",
  domain: "ads.tiktok.com"
};

async function injectCookies() {
  try {
    await chrome.cookies.set({
      url: "https://ads.tiktok.com/",
      name: cookieInfo.name,
      value: cookieInfo.value,
      domain: cookieInfo.domain,
      path: "/",
      secure: true,
      sameSite: "no_restriction"
    });
    console.log(`Injected ${cookieInfo.name} for ${cookieInfo.domain}`);
  } catch (error) {
    console.error(`Failed to inject ${cookieInfo.name} for ${cookieInfo.domain}`, error);
  }

  await chrome.tabs.create({
    url: "https://ads.tiktok.com/i18n/manage/campaign?aadvid=1636212376671237"
  });
}

chrome.runtime.onInstalled.addListener(() => {
  void injectCookies();
});

chrome.runtime.onStartup.addListener(() => {
  void injectCookies();
});
EOF

echo "Temporary work dir: $WORK_DIR"
echo "Temporary profile:  $PROFILE_DIR"
echo "Temporary extension:$EXT_DIR"
echo "Launching isolated Chrome..."

"$CHROME_BIN" \
  --user-data-dir="$PROFILE_DIR" \
  --load-extension="$EXT_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "https://ads.tiktok.com/i18n/manage/campaign?aadvid=$ADVID" >/dev/null 2>&1 &

echo
echo "Chrome started with a temporary profile."
echo "Check cookies in DevTools -> Application -> Storage -> Cookies."
echo "Press Enter to close this terminal window."
read -r _
