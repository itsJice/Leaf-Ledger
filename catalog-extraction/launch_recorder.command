#!/bin/bash
# Double-clickable recorder launcher. Opening this in Terminal.app gives the
# recorder a real interactive terminal (TTY) — which is the thing that was
# missing when it "opened then closed". This starts a recording session
# directly (no fragile Record button): Chrome opens ready to record.
cd "$(dirname "$0")" || exit 1
source .venv-recorder/bin/activate
echo "==============================================================="
echo " Vickerman recorder — a Chrome window will open with a red border."
echo ""
echo " 1. Log in with your Vickerman portal credentials."
echo " 2. Open a product page, e.g.:"
echo "    https://vickerman.com/products/details?item=G160440"
echo " 3. Confirm a real price shows (not 'Sign In For Pricing')."
echo " 4. Come back to THIS window, type  c  then press Enter to save."
echo "==============================================================="
echo ""
sbase mkrec vickerman_login.py --url "https://www.vickerman.com/Users/Account/LogOn" --overwrite
echo ""
echo ">>> Recording saved to recordings/vickerman_login_rec.py"
echo ">>> You can close this window now."
