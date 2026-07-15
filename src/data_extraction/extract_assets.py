"""
extract_assets.py - Offline Unity Asset Extractor for Life in Adventure
Extracts TextAsset JSON/XML databases from data.unity3d (base.apk).
Bypasses Google Play Protect / DRM completely by running directly on local storage.
"""

import os
import sys
import json
import UnityPy

def extract_text_assets(apk_base_dir: str, output_dir: str):
    data_unity3d_path = os.path.join(apk_base_dir, "assets", "bin", "Data", "data.unity3d")
    if not os.path.exists(data_unity3d_path):
        print(f"[ERROR] data.unity3d not found at {data_unity3d_path}")
        return False

    print(f"[*] Loading Unity asset bundle: {data_unity3d_path}")
    env = UnityPy.load(data_unity3d_path)
    
    extracted_count = 0
    os.makedirs(output_dir, exist_ok=True)
    
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            try:
                data = obj.read()
                name = data.m_Name
                script = data.m_Script
                
                # Determine extension based on content
                ext = ".json" if script.strip().startswith(("{", "[")) else ".txt"
                out_path = os.path.join(output_dir, f"{name}{ext}")
                
                if isinstance(script, bytes):
                    with open(out_path, "wb") as f:
                        f.write(script)
                else:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(script)
                        
                extracted_count += 1
                if extracted_count % 10 == 0 or "Json" in name:
                    print(f"  [+] Extracted: {name}{ext} ({len(script)} chars/bytes)")
            except Exception as e:
                print(f"  [-] Failed to extract TextAsset object: {e}")

    print(f"\n[SUCCESS] Extracted {extracted_count} TextAsset files to '{output_dir}'")
    return True

if __name__ == "__main__":
    base_dir = os.path.join("data", "apk", "extracted", "base")
    out_dir = os.path.join("data", "apk", "assets_dump")
    extract_text_assets(base_dir, out_dir)
