#!/usr/bin/env python3
import zipfile
import os

apk_path = "/apks/LicenseChecker.apk"
extract_dir = "/apks/LicenseChecker_extracted"
patched_path = "/apks/LicenseChecker_patched.apk"

# Extract
with zipfile.ZipFile(apk_path, 'r') as z:
    z.extractall(extract_dir)

print("Extracted APK")

# Create network_security_config.xml
res_xml_dir = os.path.join(extract_dir, "res", "xml")
os.makedirs(res_xml_dir, exist_ok=True)

network_security_config = '''<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
'''

with open(os.path.join(res_xml_dir, "network_security_config.xml"), "w") as f:
    f.write(network_security_config)

print("Created network_security_config.xml")

# Patch manifest
manifest_path = os.path.join(extract_dir, "AndroidManifest.xml")
with open(manifest_path, "r") as f:
    manifest = f.read()

if "android:networkSecurityConfig" not in manifest:
    manifest = manifest.replace("<application", '<application android:networkSecurityConfig="@xml/network_security_config"')
    print("Added networkSecurityConfig to manifest")

with open(manifest_path, "w") as f:
    f.write(manifest)

# Repackage
with zipfile.ZipFile(patched_path, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arc_name = os.path.relpath(file_path, extract_dir)
            z.write(file_path, arc_name)

print(f"Patched APK created at {patched_path}")