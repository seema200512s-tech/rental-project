import os
import glob

html_files = glob.glob('**/*.html', recursive=True)
for file in html_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Nested ones use ../js/db.js, root uses js/db.js
    if '\\' in file or '/' in file: 
        # Nested directory
        db_script = '<script src="../js/db.js"></script>'
        api_script = '<script src="../js/api-config.js"></script>'
    else:
        db_script = '<script src="js/db.js"></script>'
        api_script = '<script src="js/api-config.js"></script>'
        
    if api_script not in content and db_script in content:
        content = content.replace(db_script, api_script + '\n    ' + db_script)
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed {file}")
