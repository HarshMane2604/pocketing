import os

replacements = {
    "Pocketing": "Pocketing",
    "pocketing": "pocketing",
    "pocketing": "pocketing",
}

for root, dirs, files in os.walk("."):
    if ".git" in root or "node_modules" in root or ".venv" in root or "dist" in root or "__pycache__" in root:
        continue
    for file in files:
        if file.endswith(".pyc") or file == "package-lock.json":
            continue
        path = os.path.join(root, file)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = content
            for old, new in replacements.items():
                new_content = new_content.replace(old, new)
            if "App.tsx" in file:
                new_content = new_content.replace('header-title">Inbox', 'header-title">Pocketing')
            if content != new_content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
        except Exception:
            pass

# Now rename files and directories
for root, dirs, files in os.walk(".", topdown=False):
    if ".git" in root or "node_modules" in root or ".venv" in root or "dist" in root:
        continue
    for name in files + dirs:
        new_name = name
        for old, new in replacements.items():
            new_name = new_name.replace(old, new)
        if new_name != name:
            os.rename(os.path.join(root, name), os.path.join(root, new_name))
