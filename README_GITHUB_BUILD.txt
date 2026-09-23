PORTAL Android · Build 2026.09.23-b001
GitHub-ready package

1. Extract ALL contents of this ZIP into the root of the cloned repository:
   C:\Users\darta\Documents\PORTAL-Android

2. In PowerShell:
   cd $HOME\Documents\PORTAL-Android
   git status
   git add .
   git commit -m "Add PORTAL Android b001 and APK build workflow"
   git push origin main

3. Open GitHub repository -> Actions -> Build PORTAL Android APK.
   A push to main touching android_src or the workflow starts the build automatically.

4. When the workflow is green, open it -> Artifacts -> PORTAL_Android_2026.09.23-b001.
   Download the ZIP artifact. It contains:
   - PORTAL_Android_2026.09.23-b001.apk
   - SHA256 file

IMPORTANT:
- Do not upload portal.db or .env to GitHub.
- The APK expects the PORTAL local API server at http://127.0.0.1:8765 by default.
- The server folder in this repository is source code; the working portal.db remains on the Android phone.
